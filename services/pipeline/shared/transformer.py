import asyncio
import time
from abc import abstractmethod
from collections import OrderedDict, deque
from typing import Generic, List, Optional, TypeVar

from shared.message import KafkaMessage, Message

from .service_base import ServiceBase

T = TypeVar("T")
U = TypeVar("U")


class Transformer(ServiceBase, Generic[T, U]):
    """1:1 message transformation pattern."""

    @abstractmethod
    async def transform(self, message: T) -> Optional[U]:
        """Transform message. Return result to send or None to skip."""
        pass

    async def _start_service_loops(self):
        self._tasks.append(asyncio.create_task(self._poll_loop("transformer")))

    async def _dispatch(self, message: Message) -> None:
        result = await self._execute_with_protection(self.transform, message, message)
        if result is not None:
            await self._internal_send(result)


class MultiTransformer(ServiceBase, Generic[T, U]):
    """1:N message transformation pattern."""

    @abstractmethod
    async def transform(self, message: T) -> List[U]:
        """Transform message to multiple outputs."""
        pass

    async def _start_service_loops(self):
        self._tasks.append(asyncio.create_task(self._poll_loop("multi_transformer")))

    async def _dispatch(self, message: Message) -> None:
        results = await self._execute_with_protection(self.transform, message, message)
        if results is not None:
            for result in results:
                await self._internal_send(result)


class BufferedTransformer(ServiceBase, Generic[T, U]):
    """Buffered N:M transformation pattern for batch processing."""

    @abstractmethod
    def get_buffer_size(self) -> int:
        """Number of messages to buffer before processing."""
        pass

    @abstractmethod
    def get_buffer_key(self, message: T) -> str:
        """Key for grouping messages into separate buffers."""
        pass

    @abstractmethod
    async def process_buffer(self, messages: List[T]) -> List[U]:
        """Process complete buffer. Return messages to send."""
        pass

    def get_buffer_timeout_seconds(self) -> float:
        """Timeout in seconds for partial buffers. Default 60s."""
        return 60.0

    def __init__(self, service_name: str, config):
        super().__init__(service_name, config)
        self._buffers = OrderedDict()
        self._buffer_size = None
        self._buffer_timeout = None
        self._max_active_buffers = config.max_active_buffers
        self._buffers_evicted = 0

    async def _start_service_loops(self):
        self._buffer_size = self.get_buffer_size()
        self._buffer_timeout = self.get_buffer_timeout_seconds()

        self._tasks.append(asyncio.create_task(self._buffered_transformer_loop()))
        self._tasks.append(asyncio.create_task(self._buffer_timeout_loop()))

    async def _buffered_transformer_loop(self):
        """Poll, buffer by key, process when full, auto-send results."""
        self.logger.info("Buffered transformer loop starting")
        message_count = 0
        while self._running:
            try:
                message = await self._get_next_message()
                if message:
                    message_count += 1
                    if message_count % 100 == 0:
                        self.logger.debug(f"Processed {message_count} messages")
                    await self._handle_buffered_message(message)
                else:
                    await asyncio.sleep(self.config.consumer_idle_delay)

            except Exception as e:
                self.logger.error(f"Error in buffered-transformer loop: {e}")
                self.metrics.record_error("buffered_transformer_loop")
                await asyncio.sleep(self.config.error_backoff_delay)

    async def _buffer_timeout_loop(self):
        while self._running:
            try:
                current_time = time.time()
                timed_out_keys = []

                for key, buffer_info in self._buffers.items():
                    if current_time - buffer_info["created_at"] >= self._buffer_timeout:
                        timed_out_keys.append(key)

                for key in timed_out_keys:
                    buffer_info = self._buffers.pop(key)
                    messages = buffer_info["messages"]
                    self.metrics.update_buffer_count(len(self._buffers))

                    if messages:
                        self.logger.info(
                            f"Processing partial buffer for key '{key}': {len(messages)}/{self._buffer_size} messages"
                        )
                        await self._process_complete_buffer(messages, key, partial=True)

                await asyncio.sleep(10.0)  # Buffer timeout check interval.

            except Exception as e:
                self.logger.error(f"Error in buffer timeout loop: {e}")
                await asyncio.sleep(10.0)  # Retry delay after error.

    async def _handle_buffered_message(self, message: Message) -> None:
        try:
            buffer_key = self.get_buffer_key(message)

            if buffer_key not in self._buffers and len(self._buffers) >= self._max_active_buffers:
                lru_key, lru_buffer = self._buffers.popitem(last=False)
                self._buffers_evicted += 1
                self.metrics.record_buffer_eviction(lru_key)

                messages = lru_buffer["messages"]
                if messages:
                    self.logger.warning(
                        f"Buffer limit ({self._max_active_buffers}) reached, evicting LRU buffer '{lru_key}' "
                        f"with {len(messages)}/{self._buffer_size} messages"
                    )
                    await self._process_complete_buffer(messages, lru_key, partial=True)

            is_new_buffer = buffer_key not in self._buffers
            if is_new_buffer:
                self._buffers[buffer_key] = {"messages": [], "created_at": time.time()}
                self.metrics.update_buffer_count(len(self._buffers))
            else:
                self._buffers.move_to_end(buffer_key)

            self._buffers[buffer_key]["messages"].append(message)
            buffer_size = len(self._buffers[buffer_key]["messages"])
            self.logger.debug(
                f"Buffered message for key '{buffer_key}': {buffer_size}/{self._buffer_size}"
            )

            if buffer_size >= self._buffer_size:
                buffer_info = self._buffers.pop(buffer_key)
                messages = buffer_info["messages"]
                self.metrics.update_buffer_count(len(self._buffers))
                await self._process_complete_buffer(messages, buffer_key, partial=False)

        except Exception as e:
            self.logger.error(f"Error handling buffered message {message.id}: {e}")
            self.metrics.record_error("buffer_management")
            raise

    async def _process_complete_buffer(
        self, messages: List[Message], buffer_key: str, partial: bool
    ) -> None:
        async with self._semaphore:
            start_time = time.time()

            try:
                results = await asyncio.wait_for(
                    self.consumer_circuit_breaker.call(
                        self.retry_handler.retry_with_backoff, self.process_buffer, messages
                    ),
                    timeout=self.config.message_timeout,
                )

                for result in results:
                    await self._internal_send(result)

                processing_time = time.time() - start_time
                self.metrics.record_message_processed(processing_time)
                self.metrics.record_buffer_processed(len(messages), buffer_key, partial)

                buffer_type = "partial" if partial else "full"
                self.logger.info(
                    f"Processed {buffer_type} buffer for key '{buffer_key}': "
                    f"{len(messages)} messages → {len(results)} outputs in {processing_time:.3f}s"
                )

                for message in messages:
                    if isinstance(message, KafkaMessage):
                        await self._commit_message(message)

            except asyncio.TimeoutError:
                self.logger.error(
                    f"Buffer processing timed out for key '{buffer_key}' after {self.config.message_timeout}s"
                )
                self.metrics.record_error("buffer_timeout")

                if self.config.enable_dlq:
                    for message in messages:
                        await self.handle_dead_letter(
                            message,
                            f"Buffer processing timeout after {self.config.message_timeout}s",
                        )

            except Exception as e:
                self.logger.error(
                    f"Failed to process buffer for key '{buffer_key}' after all retries: {e}"
                )
                self.metrics.record_error("buffer_processing")

                if self.config.enable_dlq:
                    for message in messages:
                        await self.handle_dead_letter(message, str(e))


class RollingBufferedTransformer(ServiceBase, Generic[T, U]):
    """Rolling FIFO buffer for overlapping window processing.

    Unlike BufferedTransformer which clears buffers after processing,
    this maintains a constant-size rolling window per buffer key.

    Design:
        - Each buffer is a deque(maxlen=window_size) - FIFO, constant memory
        - Messages are appended; oldest auto-removed when full
        - Processing triggers every step_size new messages
        - Window naturally maintains (window_size - step_size) overlap

    Example with window=300, step=250:
        - Messages 0-299: buffer fills to 300, process window 0
        - Messages 300-549: 250 new, oldest 250 auto-removed
          Buffer now [250-549], process window 1
        - Natural 50-sample overlap between windows
    """

    @abstractmethod
    def get_window_size(self) -> int:
        """Size of processing window (e.g., 300 samples)."""
        pass

    @abstractmethod
    def get_step_size(self) -> int:
        """How often to process (e.g., every 250 new messages)."""
        pass

    @abstractmethod
    def get_buffer_key(self, message: T) -> str:
        """Key for grouping messages into separate buffers."""
        pass

    @abstractmethod
    async def process_buffer(self, messages: List[T]) -> List[U]:
        """Process window snapshot. Return messages to send."""
        pass

    def get_buffer_timeout_seconds(self) -> float:
        """Timeout in seconds for stale buffers. Default 60s."""
        return 60.0

    def __init__(self, service_name: str, config):
        super().__init__(service_name, config)
        # Rolling buffers: key -> {"deque": deque, "new_count": int, "last_update": float}
        self._rolling_buffers = OrderedDict()
        self._window_size = None
        self._step_size = None
        self._buffer_timeout = None
        self._max_active_buffers = config.max_active_buffers
        self._buffers_evicted = 0

    async def _start_service_loops(self):
        self._window_size = self.get_window_size()
        self._step_size = self.get_step_size()
        self._buffer_timeout = self.get_buffer_timeout_seconds()

        self.logger.info(
            f"RollingBufferedTransformer: window={self._window_size}, "
            f"step={self._step_size}, overlap={self._window_size - self._step_size}"
        )

        self._tasks.append(asyncio.create_task(self._rolling_transformer_loop()))
        self._tasks.append(asyncio.create_task(self._rolling_buffer_timeout_loop()))

    async def _rolling_transformer_loop(self):
        """Poll, buffer by key with rolling FIFO, process at step intervals."""
        self.logger.info("Rolling buffered transformer loop starting")
        message_count = 0

        while self._running:
            try:
                message = await self._get_next_message()
                if message:
                    message_count += 1
                    if message_count % 100 == 0:
                        self.logger.debug(f"Processed {message_count} messages")
                    await self._handle_rolling_message(message)
                else:
                    await asyncio.sleep(self.config.consumer_idle_delay)

            except Exception as e:
                self.logger.error(f"Error in rolling-transformer loop: {e}")
                self.metrics.record_error("rolling_transformer_loop")
                await asyncio.sleep(self.config.error_backoff_delay)

    async def _rolling_buffer_timeout_loop(self):
        """Process stale buffers that haven't received messages."""
        while self._running:
            try:
                current_time = time.time()
                timed_out_keys = []

                for key, buffer_info in self._rolling_buffers.items():
                    if current_time - buffer_info["last_update"] >= self._buffer_timeout:
                        timed_out_keys.append(key)

                for key in timed_out_keys:
                    buffer_info = self._rolling_buffers.pop(key)
                    messages = list(buffer_info["deque"])
                    self.metrics.update_buffer_count(len(self._rolling_buffers))

                    if messages:
                        self.logger.info(
                            f"Processing stale rolling buffer for key '{key}': "
                            f"{len(messages)}/{self._window_size} messages"
                        )
                        await self._process_rolling_buffer(messages, key, partial=True)

                await asyncio.sleep(10.0)

            except Exception as e:
                self.logger.error(f"Error in rolling buffer timeout loop: {e}")
                await asyncio.sleep(10.0)

    async def _handle_rolling_message(self, message: Message) -> None:
        """Add message to rolling buffer, process when step_size reached."""
        try:
            buffer_key = self.get_buffer_key(message)

            # Evict LRU buffer if at capacity
            if (
                buffer_key not in self._rolling_buffers
                and len(self._rolling_buffers) >= self._max_active_buffers
            ):
                lru_key, lru_buffer = self._rolling_buffers.popitem(last=False)
                self._buffers_evicted += 1
                self.metrics.record_buffer_eviction(lru_key)

                messages = list(lru_buffer["deque"])
                if messages:
                    self.logger.warning(
                        f"Buffer limit ({self._max_active_buffers}) reached, evicting LRU buffer '{lru_key}' "
                        f"with {len(messages)} messages"
                    )
                    await self._process_rolling_buffer(messages, lru_key, partial=True)

            # Create new buffer if needed
            is_new_buffer = buffer_key not in self._rolling_buffers
            if is_new_buffer:
                self._rolling_buffers[buffer_key] = {
                    "deque": deque(maxlen=self._window_size),
                    "new_count": 0,
                    "last_update": time.time(),
                }
                self.metrics.update_buffer_count(len(self._rolling_buffers))
            else:
                self._rolling_buffers.move_to_end(buffer_key)

            # Append message (deque auto-removes oldest if at maxlen)
            buffer_info = self._rolling_buffers[buffer_key]
            buffer_info["deque"].append(message)
            buffer_info["new_count"] += 1
            buffer_info["last_update"] = time.time()

            buffer_len = len(buffer_info["deque"])

            # Process when: buffer is full AND we've received step_size new messages
            if buffer_len >= self._window_size and buffer_info["new_count"] >= self._step_size:
                # Snapshot current window (don't pop - keep for overlap)
                messages = list(buffer_info["deque"])
                buffer_info["new_count"] = 0  # Reset counter

                self.logger.debug(
                    f"Rolling buffer '{buffer_key}' ready: {buffer_len} messages, "
                    f"processing window"
                )
                await self._process_rolling_buffer(messages, buffer_key, partial=False)

        except Exception as e:
            self.logger.error(f"Error handling rolling message {message.id}: {e}")
            self.metrics.record_error("rolling_buffer_management")
            raise

    async def _process_rolling_buffer(
        self, messages: List[Message], buffer_key: str, partial: bool
    ) -> None:
        """Process a snapshot of the rolling buffer."""
        async with self._semaphore:
            start_time = time.time()

            try:
                results = await asyncio.wait_for(
                    self.consumer_circuit_breaker.call(
                        self.retry_handler.retry_with_backoff, self.process_buffer, messages
                    ),
                    timeout=self.config.message_timeout,
                )

                for result in results:
                    await self._internal_send(result)

                processing_time = time.time() - start_time
                self.metrics.record_message_processed(processing_time)
                self.metrics.record_buffer_processed(len(messages), buffer_key, partial)

                buffer_type = "partial" if partial else "full"
                self.logger.info(
                    f"Processed {buffer_type} rolling window for key '{buffer_key}': "
                    f"{len(messages)} messages → {len(results)} outputs in {processing_time:.3f}s"
                )

                # Commit all messages in the window
                # Note: For rolling buffers, some messages may be committed multiple times
                # across overlapping windows - Kafka handles this gracefully
                for message in messages:
                    if isinstance(message, KafkaMessage):
                        await self._commit_message(message)

            except asyncio.TimeoutError:
                self.logger.error(
                    f"Rolling buffer processing timed out for key '{buffer_key}' "
                    f"after {self.config.message_timeout}s"
                )
                self.metrics.record_error("rolling_buffer_timeout")

                if self.config.enable_dlq:
                    for message in messages:
                        await self.handle_dead_letter(
                            message,
                            f"Rolling buffer processing timeout after {self.config.message_timeout}s",
                        )

            except Exception as e:
                self.logger.error(
                    f"Failed to process rolling buffer for key '{buffer_key}' after all retries: {e}"
                )
                self.metrics.record_error("rolling_buffer_processing")

                if self.config.enable_dlq:
                    for message in messages:
                        await self.handle_dead_letter(message, str(e))
