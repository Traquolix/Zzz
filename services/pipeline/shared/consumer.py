import asyncio
import time
from abc import abstractmethod

from shared.message import KafkaMessage, Message

from .service_base import ServiceBase


class Consumer(ServiceBase):
    # Pattern for pure consumption (no producer infrastructure)
    # Implement consume() to process messages, infrastructure handles Kafka/commit/retry

    @abstractmethod
    async def consume(self, message: Message) -> None:
        # Process message without producing output
        pass

    async def _start_service_loops(self):
        # Start consumer loop only
        self._tasks.append(asyncio.create_task(self._consumer_loop()))

    async def _consumer_loop(self):
        # Poll -> consume -> commit loop
        while self._running:
            try:
                message = await self._get_next_message()
                if message:
                    await self._process_consumer_message(message)
                else:
                    await asyncio.sleep(self.config.consumer_idle_delay)

            except Exception as e:
                self.logger.error(f"Error in consumer loop: {e}")
                self.metrics.record_error("consumer_loop")
                await asyncio.sleep(self.config.error_backoff_delay)

    async def _process_consumer_message(self, message: Message) -> None:
        # Process through consumer pattern with timeout and DLQ
        async with self._semaphore:
            start_time = time.time()

            try:
                # Apply message timeout to the entire processing chain
                await asyncio.wait_for(
                    self.consumer_circuit_breaker.call(
                        self.retry_handler.retry_with_backoff, self.consume, message
                    ),
                    timeout=self.config.message_timeout,
                )

                processing_time = time.time() - start_time
                self.metrics.record_message_processed(processing_time)
                self.logger.debug(f"Message {message.id} consumed in {processing_time:.3f}s")

                # Commit message after successful processing
                if isinstance(message, KafkaMessage):
                    await self._commit_message(message)

            except asyncio.TimeoutError:
                self.logger.error(
                    f"Message {message.id} consumption timed out after {self.config.message_timeout}s"
                )
                self.metrics.record_error("message_timeout")

                if self.config.enable_dlq:
                    await self.handle_dead_letter(
                        message, f"Consumption timeout after {self.config.message_timeout}s"
                    )

            except Exception as e:
                self.logger.error(f"Failed to consume message {message.id} after all retries: {e}")
                self.metrics.record_error("message_processing")

                if self.config.enable_dlq:
                    await self.handle_dead_letter(message, str(e))
