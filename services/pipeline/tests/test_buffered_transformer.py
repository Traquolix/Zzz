"""Tests for the REAL BufferedTransformer class.

These tests verify the actual BufferedTransformer implementation, not a mock.
We mock only the infrastructure (Kafka, schemas) but test real buffering logic.
"""

import asyncio
import time
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.message import Message
from shared.service_config import ServiceConfig
from shared.transformer import BufferedTransformer


class ConcreteBufferedTransformer(BufferedTransformer):
    """Concrete implementation for testing."""

    def __init__(self, config, buffer_size=3, buffer_key_field="fiber_id", buffer_timeout=60.0):
        self._test_buffer_size = buffer_size
        self._test_buffer_key_field = buffer_key_field
        self._test_buffer_timeout = buffer_timeout
        self._processed_buffers = []
        super().__init__("test_buffered_transformer", config)

    def get_buffer_size(self) -> int:
        return self._test_buffer_size

    def get_buffer_key(self, message) -> str:
        return message.payload.get(self._test_buffer_key_field, "default")

    def get_buffer_timeout_seconds(self) -> float:
        return self._test_buffer_timeout

    async def process_buffer(self, messages: List[Message]) -> List[Message]:
        """Test implementation: records what was processed."""
        self._processed_buffers.append(
            {
                "count": len(messages),
                "keys": [m.payload.get(self._test_buffer_key_field) for m in messages],
            }
        )
        # Return a single output message
        return [Message(id="output", payload={"processed": len(messages)})]


@pytest.fixture
def test_config():
    """Config with mocked schema files."""
    return ServiceConfig(
        kafka_bootstrap_servers="localhost:9092",
        schema_registry_url="http://localhost:8081",
        input_topic="test.input",
        output_topic="test.output",
        input_key_schema_file=None,
        input_value_schema_file=None,
        output_key_schema_file=None,
        output_value_schema_file=None,
        max_active_buffers=5,
        enable_dlq=False,
    )


async def async_passthrough(fn, *args):
    """Helper to properly await async functions in mock chains."""
    result = fn(*args)
    if asyncio.iscoroutine(result):
        return await result
    return result


@pytest.fixture
def transformer(test_config):
    """Create transformer with mocked infrastructure."""
    with patch.object(BufferedTransformer, "_load_schema", return_value=None):
        t = ConcreteBufferedTransformer(test_config, buffer_size=3)
        # Mock infrastructure with proper async handling
        t._internal_send = AsyncMock()
        t.consumer_circuit_breaker = MagicMock()
        t.consumer_circuit_breaker.call = AsyncMock(side_effect=async_passthrough)
        t.retry_handler = MagicMock()
        t.retry_handler.retry_with_backoff = AsyncMock(side_effect=async_passthrough)
        t.metrics = MagicMock()
        t._commit_message = AsyncMock()
        t.logger = MagicMock()
        # Initialize buffer state
        t._buffer_size = t.get_buffer_size()
        t._buffer_timeout = t.get_buffer_timeout_seconds()
        t._semaphore = asyncio.Semaphore(10)
        return t


class TestBufferedTransformerBuffering:
    """Test buffer accumulation - REAL BufferedTransformer class."""

    @pytest.mark.asyncio
    async def test_buffers_messages_until_full(self, transformer):
        """Messages should accumulate until buffer is full."""
        # Send 2 messages (buffer size is 3)
        for i in range(2):
            await transformer._handle_buffered_message(
                Message(id=str(i), payload={"fiber_id": "test"})
            )

        # Buffer not yet processed
        assert len(transformer._processed_buffers) == 0
        assert "test" in transformer._buffers
        assert len(transformer._buffers["test"]["messages"]) == 2

    @pytest.mark.asyncio
    async def test_processes_when_buffer_full(self, transformer):
        """Buffer should be processed when full."""
        for i in range(3):
            await transformer._handle_buffered_message(
                Message(id=str(i), payload={"fiber_id": "test"})
            )

        # Buffer was processed and removed
        assert len(transformer._processed_buffers) == 1
        assert transformer._processed_buffers[0]["count"] == 3
        assert "test" not in transformer._buffers
        # Output was sent
        transformer._internal_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_separate_buffers_per_key(self, transformer):
        """Each key should have its own buffer."""
        for i in range(2):
            await transformer._handle_buffered_message(
                Message(id=f"a{i}", payload={"fiber_id": "fiber_a"})
            )
            await transformer._handle_buffered_message(
                Message(id=f"b{i}", payload={"fiber_id": "fiber_b"})
            )

        assert len(transformer._buffers) == 2
        assert "fiber_a" in transformer._buffers
        assert "fiber_b" in transformer._buffers
        assert len(transformer._buffers["fiber_a"]["messages"]) == 2
        assert len(transformer._buffers["fiber_b"]["messages"]) == 2

    @pytest.mark.asyncio
    async def test_keys_fill_independently(self, transformer):
        """One key filling shouldn't affect other keys."""
        # Fill fiber_a (3 messages = full)
        for i in range(3):
            await transformer._handle_buffered_message(
                Message(id=f"a{i}", payload={"fiber_id": "fiber_a"})
            )
        # fiber_b has 1 message
        await transformer._handle_buffered_message(
            Message(id="b0", payload={"fiber_id": "fiber_b"})
        )

        # Only fiber_a processed
        assert len(transformer._processed_buffers) == 1
        assert transformer._processed_buffers[0]["keys"][0] == "fiber_a"
        # fiber_b still buffering
        assert "fiber_b" in transformer._buffers
        assert len(transformer._buffers["fiber_b"]["messages"]) == 1


class TestBufferedTransformerLRU:
    """Test LRU eviction when buffer limit is reached."""

    @pytest.mark.asyncio
    async def test_evicts_lru_when_limit_reached(self, test_config):
        """Should evict least recently used buffer when limit exceeded."""
        test_config.max_active_buffers = 2

        with patch.object(BufferedTransformer, "_load_schema", return_value=None):
            transformer = ConcreteBufferedTransformer(test_config, buffer_size=10)
            transformer._internal_send = AsyncMock()
            transformer.consumer_circuit_breaker = MagicMock()
            transformer.consumer_circuit_breaker.call = AsyncMock(side_effect=async_passthrough)
            transformer.retry_handler = MagicMock()
            transformer.retry_handler.retry_with_backoff = AsyncMock(side_effect=async_passthrough)
            transformer.metrics = MagicMock()
            transformer._commit_message = AsyncMock()
            transformer.logger = MagicMock()
            transformer._buffer_size = transformer.get_buffer_size()
            transformer._buffer_timeout = transformer.get_buffer_timeout_seconds()
            transformer._semaphore = asyncio.Semaphore(10)

        # Fill two buffers
        await transformer._handle_buffered_message(Message(id="1", payload={"fiber_id": "first"}))
        await transformer._handle_buffered_message(Message(id="2", payload={"fiber_id": "second"}))

        assert len(transformer._buffers) == 2

        # Adding third key should evict "first" (LRU)
        await transformer._handle_buffered_message(Message(id="3", payload={"fiber_id": "third"}))

        assert len(transformer._buffers) == 2
        assert "first" not in transformer._buffers
        assert "second" in transformer._buffers
        assert "third" in transformer._buffers

    @pytest.mark.asyncio
    async def test_evicted_buffer_is_processed_as_partial(self, test_config):
        """Evicted buffer should be processed with its messages."""
        test_config.max_active_buffers = 1

        with patch.object(BufferedTransformer, "_load_schema", return_value=None):
            transformer = ConcreteBufferedTransformer(test_config, buffer_size=10)
            transformer._internal_send = AsyncMock()
            transformer.consumer_circuit_breaker = MagicMock()
            transformer.consumer_circuit_breaker.call = AsyncMock(side_effect=async_passthrough)
            transformer.retry_handler = MagicMock()
            transformer.retry_handler.retry_with_backoff = AsyncMock(side_effect=async_passthrough)
            transformer.metrics = MagicMock()
            transformer._commit_message = AsyncMock()
            transformer.logger = MagicMock()
            transformer._buffer_size = transformer.get_buffer_size()
            transformer._buffer_timeout = transformer.get_buffer_timeout_seconds()
            transformer._semaphore = asyncio.Semaphore(10)

        # Add 2 messages to first buffer
        await transformer._handle_buffered_message(Message(id="1", payload={"fiber_id": "first"}))
        await transformer._handle_buffered_message(Message(id="2", payload={"fiber_id": "first"}))

        # Adding new key evicts first
        await transformer._handle_buffered_message(Message(id="3", payload={"fiber_id": "second"}))

        # First buffer was processed with 2 messages
        assert len(transformer._processed_buffers) == 1
        assert transformer._processed_buffers[0]["count"] == 2

    @pytest.mark.asyncio
    async def test_access_moves_to_end(self, test_config):
        """Accessing a buffer should make it most recently used."""
        test_config.max_active_buffers = 2

        with patch.object(BufferedTransformer, "_load_schema", return_value=None):
            transformer = ConcreteBufferedTransformer(test_config, buffer_size=10)
            transformer._internal_send = AsyncMock()
            transformer.consumer_circuit_breaker = MagicMock()
            transformer.consumer_circuit_breaker.call = AsyncMock(side_effect=async_passthrough)
            transformer.retry_handler = MagicMock()
            transformer.retry_handler.retry_with_backoff = AsyncMock(side_effect=async_passthrough)
            transformer.metrics = MagicMock()
            transformer._commit_message = AsyncMock()
            transformer.logger = MagicMock()
            transformer._buffer_size = transformer.get_buffer_size()
            transformer._buffer_timeout = transformer.get_buffer_timeout_seconds()
            transformer._semaphore = asyncio.Semaphore(10)

        # Create two buffers
        await transformer._handle_buffered_message(Message(id="1", payload={"fiber_id": "first"}))
        await transformer._handle_buffered_message(Message(id="2", payload={"fiber_id": "second"}))

        # Access first again (makes it most recent)
        await transformer._handle_buffered_message(Message(id="3", payload={"fiber_id": "first"}))

        # Now adding third should evict "second" (now LRU)
        await transformer._handle_buffered_message(Message(id="4", payload={"fiber_id": "third"}))

        assert "first" in transformer._buffers
        assert "second" not in transformer._buffers
        assert "third" in transformer._buffers


class TestBufferedTransformerTimeout:
    """Test buffer timeout behavior."""

    @pytest.mark.asyncio
    async def test_timeout_processes_partial_buffer(self, test_config):
        """Timed out buffer should be processed."""
        with patch.object(BufferedTransformer, "_load_schema", return_value=None):
            transformer = ConcreteBufferedTransformer(
                test_config, buffer_size=10, buffer_timeout=1.0
            )
            transformer._internal_send = AsyncMock()
            transformer.consumer_circuit_breaker = MagicMock()
            transformer.consumer_circuit_breaker.call = AsyncMock(side_effect=async_passthrough)
            transformer.retry_handler = MagicMock()
            transformer.retry_handler.retry_with_backoff = AsyncMock(side_effect=async_passthrough)
            transformer.metrics = MagicMock()
            transformer._commit_message = AsyncMock()
            transformer.logger = MagicMock()
            transformer._running = True
            transformer._buffer_size = transformer.get_buffer_size()
            transformer._buffer_timeout = transformer.get_buffer_timeout_seconds()
            transformer._semaphore = asyncio.Semaphore(10)

        # Add message with old timestamp
        transformer._buffers["test"] = {
            "messages": [Message(id="1", payload={"fiber_id": "test"})],
            "created_at": time.time() - 10.0,  # 10 seconds ago, timeout is 1s
        }

        # Run one iteration of timeout loop
        transformer._running = False  # Will exit after one check
        current_time = time.time()
        timed_out_keys = []
        for key, buffer_info in transformer._buffers.items():
            if current_time - buffer_info["created_at"] >= transformer._buffer_timeout:
                timed_out_keys.append(key)

        for key in timed_out_keys:
            buffer_info = transformer._buffers.pop(key)
            messages = buffer_info["messages"]
            if messages:
                await transformer._process_complete_buffer(messages, key, partial=True)

        assert "test" not in transformer._buffers
        assert len(transformer._processed_buffers) == 1

    @pytest.mark.asyncio
    async def test_fresh_buffers_not_timed_out(self, test_config):
        """Buffers within timeout should not be processed."""
        with patch.object(BufferedTransformer, "_load_schema", return_value=None):
            transformer = ConcreteBufferedTransformer(
                test_config, buffer_size=10, buffer_timeout=60.0
            )
            transformer.logger = MagicMock()
            transformer.metrics = MagicMock()
            transformer._buffer_size = transformer.get_buffer_size()
            transformer._buffer_timeout = transformer.get_buffer_timeout_seconds()

        # Add message with recent timestamp
        transformer._buffers["test"] = {
            "messages": [Message(id="1", payload={"fiber_id": "test"})],
            "created_at": time.time(),  # Just now
        }

        # Check for timeouts
        current_time = time.time()
        timed_out_keys = []
        for key, buffer_info in transformer._buffers.items():
            if current_time - buffer_info["created_at"] >= transformer._buffer_timeout:
                timed_out_keys.append(key)

        # No timeouts
        assert len(timed_out_keys) == 0
        assert "test" in transformer._buffers


class TestBufferedTransformerEdgeCases:
    """Test edge cases."""

    @pytest.mark.asyncio
    async def test_buffer_size_1_processes_immediately(self, test_config):
        """Buffer size of 1 should process each message immediately."""
        with patch.object(BufferedTransformer, "_load_schema", return_value=None):
            transformer = ConcreteBufferedTransformer(test_config, buffer_size=1)
            transformer._internal_send = AsyncMock()
            transformer.consumer_circuit_breaker = MagicMock()
            transformer.consumer_circuit_breaker.call = AsyncMock(side_effect=async_passthrough)
            transformer.retry_handler = MagicMock()
            transformer.retry_handler.retry_with_backoff = AsyncMock(side_effect=async_passthrough)
            transformer.metrics = MagicMock()
            transformer._commit_message = AsyncMock()
            transformer.logger = MagicMock()
            transformer._buffer_size = transformer.get_buffer_size()
            transformer._buffer_timeout = transformer.get_buffer_timeout_seconds()
            transformer._semaphore = asyncio.Semaphore(10)

        await transformer._handle_buffered_message(Message(id="1", payload={"fiber_id": "test"}))

        assert len(transformer._processed_buffers) == 1
        assert transformer._processed_buffers[0]["count"] == 1

    @pytest.mark.asyncio
    async def test_exception_in_handle_message_propagates(self, transformer):
        """Exceptions in _handle_buffered_message should propagate."""

        # Make get_buffer_key raise
        def raise_error(msg):
            raise ValueError("test error")

        transformer.get_buffer_key = raise_error

        with pytest.raises(ValueError, match="test error"):
            await transformer._handle_buffered_message(
                Message(id="1", payload={"fiber_id": "test"})
            )

    @pytest.mark.asyncio
    async def test_process_complete_buffer_handles_timeout(self, test_config):
        """Timeout during buffer processing should be handled."""
        with patch.object(BufferedTransformer, "_load_schema", return_value=None):
            transformer = ConcreteBufferedTransformer(test_config, buffer_size=3)
            transformer._internal_send = AsyncMock()
            transformer.metrics = MagicMock()
            transformer._commit_message = AsyncMock()
            transformer.logger = MagicMock()
            transformer.handle_dead_letter = AsyncMock()
            transformer._buffer_size = transformer.get_buffer_size()
            transformer._buffer_timeout = transformer.get_buffer_timeout_seconds()
            transformer._semaphore = asyncio.Semaphore(10)
            transformer.config.message_timeout = 0.001
            transformer.config.enable_dlq = True
            transformer.consumer_circuit_breaker = MagicMock()

            async def slow_process(*args):
                await asyncio.sleep(1.0)

            transformer.consumer_circuit_breaker.call = AsyncMock(side_effect=slow_process)

        messages = [Message(id="1", payload={"fiber_id": "test"})]
        await transformer._process_complete_buffer(messages, "test", partial=False)

        # Should have recorded error
        transformer.metrics.record_error.assert_called_with("buffer_timeout")

    @pytest.mark.asyncio
    async def test_metrics_recorded_correctly(self, transformer):
        """Metrics should be recorded for processed buffers."""
        for i in range(3):
            await transformer._handle_buffered_message(
                Message(id=str(i), payload={"fiber_id": "test"})
            )

        transformer.metrics.record_message_processed.assert_called_once()
        transformer.metrics.record_buffer_processed.assert_called_once_with(3, "test", False)


class TestBufferedTransformerIntegration:
    """Integration tests with circuit breaker and retry handler."""

    @pytest.mark.asyncio
    async def test_uses_circuit_breaker_for_processing(self, transformer):
        """Processing should go through circuit breaker."""
        for i in range(3):
            await transformer._handle_buffered_message(
                Message(id=str(i), payload={"fiber_id": "test"})
            )

        # Circuit breaker was used
        transformer.consumer_circuit_breaker.call.assert_called()

    @pytest.mark.asyncio
    async def test_uses_retry_handler(self, transformer):
        """Processing should use retry handler."""
        for i in range(3):
            await transformer._handle_buffered_message(
                Message(id=str(i), payload={"fiber_id": "test"})
            )

        # Retry handler was used
        transformer.retry_handler.retry_with_backoff.assert_called()
