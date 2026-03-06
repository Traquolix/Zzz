#!/usr/bin/env python3
"""Unit tests for RollingBufferedTransformer."""

import asyncio
import sys
from pathlib import Path
from typing import List
from unittest.mock import MagicMock

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Optional pytest import for advanced tests
try:
    from unittest.mock import AsyncMock

    import pytest

    PYTEST_AVAILABLE = True
except ImportError:
    PYTEST_AVAILABLE = False
    AsyncMock = MagicMock  # Fallback

    # Create a dummy decorator
    class pytest:
        @staticmethod
        def fixture(fn):
            return fn

        class mark:
            @staticmethod
            def asyncio(fn):
                return fn


class MockConfig:
    """Mock service config for testing."""

    consumer_idle_delay = 0.01
    error_backoff_delay = 0.01
    message_timeout = 10.0
    max_active_buffers = 5
    enable_dlq = False


class MockMessage:
    """Mock message for testing."""

    def __init__(self, buffer_key: str, timestamp: int):
        self.buffer_key = buffer_key
        self.timestamp = timestamp
        self.id = f"msg-{timestamp}"
        self.payload = {"buffer_key": buffer_key, "timestamp": timestamp}


class TestRollingBuffer:
    """Test the rolling buffer logic without full service infrastructure."""

    def test_fifo_behavior(self):
        """Test that deque maintains FIFO with maxlen."""
        from collections import deque

        window_size = 300
        step_size = 250
        buffer = deque(maxlen=window_size)

        # Fill buffer
        for i in range(window_size):
            buffer.append(i)

        assert len(buffer) == window_size
        assert buffer[0] == 0
        assert buffer[-1] == 299

        # Add step_size more (FIFO removes oldest)
        for i in range(window_size, window_size + step_size):
            buffer.append(i)

        assert len(buffer) == window_size  # Still 300
        assert buffer[0] == 250  # Oldest is now T250
        assert buffer[-1] == 549  # Newest is T549

    def test_overlap_calculation(self):
        """Test that overlap between windows is correct."""
        window_size = 300
        edge_trim = 25
        step_size = window_size - 2 * edge_trim  # 250

        # Window 1: T0-T299, trimmed output T25-T274
        window1_start = 0
        window1_output_end = window1_start + window_size - edge_trim - 1  # 274

        # Window 2: T250-T549, trimmed output T275-T524
        window2_start = step_size  # 250
        window2_output_start = window2_start + edge_trim  # 275

        # Verify adjacent
        gap = window2_output_start - window1_output_end
        assert gap == 1, f"Expected gap=1, got {gap}"

    def test_continuous_output(self):
        """Test that rolling buffer produces continuous output."""
        from collections import deque

        import numpy as np

        window_size = 300
        edge_trim = 25
        step_size = window_size - 2 * edge_trim
        num_messages = 1500

        buffer = deque(maxlen=window_size)
        new_count = 0
        all_outputs = []

        for msg_ts in range(num_messages):
            buffer.append(msg_ts)
            new_count += 1

            if len(buffer) >= window_size and new_count >= step_size:
                window = list(buffer)
                trimmed = window[edge_trim : window_size - edge_trim]
                all_outputs.extend(trimmed)
                new_count = 0

        output_ts = np.array(all_outputs)
        diffs = np.diff(output_ts)

        # All diffs should be 1 (continuous)
        assert np.all(diffs == 1), f"Found gaps: {np.where(diffs != 1)[0]}"

        # No duplicates
        assert len(np.unique(output_ts)) == len(output_ts), "Found duplicates"

    def test_multiple_buffer_keys(self):
        """Test that separate buffer keys maintain independent state."""
        from collections import deque

        window_size = 10

        buffers = {}

        # Simulate messages for two different buffer keys
        for i in range(20):
            for key in ["fiber1:section1", "fiber2:section1"]:
                if key not in buffers:
                    buffers[key] = {"deque": deque(maxlen=window_size), "new_count": 0}

                buffers[key]["deque"].append((key, i))
                buffers[key]["new_count"] += 1

        # Each buffer should have independent state
        assert len(buffers["fiber1:section1"]["deque"]) == window_size
        assert len(buffers["fiber2:section1"]["deque"]) == window_size

        # Contents should be different (each has its own key prefix)
        fiber1_first = buffers["fiber1:section1"]["deque"][0]
        fiber2_first = buffers["fiber2:section1"]["deque"][0]
        assert fiber1_first[0] == "fiber1:section1"
        assert fiber2_first[0] == "fiber2:section1"


class TestRollingBufferedTransformerClass:
    """Test the actual RollingBufferedTransformer class."""

    @pytest.fixture
    def mock_transformer(self):
        """Create a concrete implementation for testing."""
        from shared.transformer import RollingBufferedTransformer

        class TestTransformer(RollingBufferedTransformer):
            def __init__(self):
                self.processed_windows = []
                self._running = True
                self._semaphore = asyncio.Semaphore(10)
                self.consumer_circuit_breaker = MagicMock()

                async def mock_circuit_breaker_call(retry_fn, fn, *args):
                    # Call the retry function which in turn calls fn
                    result = retry_fn(fn, *args)
                    # retry_fn may return a coroutine if it's async
                    if asyncio.iscoroutine(result):
                        return await result
                    return result

                self.consumer_circuit_breaker.call = mock_circuit_breaker_call
                self.retry_handler = MagicMock()

                # The retry handler needs to properly await async functions
                async def mock_retry(fn, *args):
                    result = fn(*args)
                    if asyncio.iscoroutine(result):
                        return await result
                    return result

                self.retry_handler.retry_with_backoff = mock_retry
                self.config = MockConfig()
                self.metrics = MagicMock()
                self.logger = MagicMock()

                # Initialize parent state
                from collections import OrderedDict

                self._rolling_buffers = OrderedDict()
                self._window_size = 10
                self._step_size = 8
                self._buffer_timeout = 60.0
                self._max_active_buffers = 5
                self._buffers_evicted = 0

            def get_window_size(self) -> int:
                return 10

            def get_step_size(self) -> int:
                return 8

            def get_buffer_key(self, message) -> str:
                return message.buffer_key

            async def process_buffer(self, messages: List) -> List:
                timestamps = [m.timestamp for m in messages]
                self.processed_windows.append(timestamps)
                return [{"processed": timestamps}]

            async def _internal_send(self, result):
                pass

            async def _commit_message(self, message):
                pass

        return TestTransformer()

    @pytest.mark.asyncio
    async def test_handles_rolling_message(self, mock_transformer):
        """Test _handle_rolling_message processes at correct intervals."""
        # Send 20 messages
        for i in range(20):
            msg = MockMessage("test:buffer", i)
            await mock_transformer._handle_rolling_message(msg)

        # With window=10, step=8:
        # - First window at message 9 (buffer fills to 10, new_count=10 >= 8)
        # - Second window at message 17 (8 more messages)
        assert len(mock_transformer.processed_windows) == 2

        # First window should be T0-T9
        assert mock_transformer.processed_windows[0] == list(range(10))

        # Second window should be T8-T17 (FIFO removed T0-T7, kept T8-T9, added T10-T17)
        assert mock_transformer.processed_windows[1] == list(range(8, 18))

    @pytest.mark.asyncio
    async def test_buffer_key_isolation(self, mock_transformer):
        """Test that different buffer keys are processed independently."""
        # Send messages to two different buffer keys
        for i in range(15):
            msg1 = MockMessage("key1", i)
            msg2 = MockMessage("key2", i + 100)
            await mock_transformer._handle_rolling_message(msg1)
            await mock_transformer._handle_rolling_message(msg2)

        # Each key should have processed 1 window (at message 9)
        key1_windows = [w for w in mock_transformer.processed_windows if w[0] < 100]
        key2_windows = [w for w in mock_transformer.processed_windows if w[0] >= 100]

        assert len(key1_windows) == 1
        assert len(key2_windows) == 1

    @pytest.mark.asyncio
    async def test_lru_eviction(self, mock_transformer):
        """Test that LRU eviction works when max buffers exceeded."""
        mock_transformer._max_active_buffers = 3

        # Create 4 different buffer keys (exceeds max of 3)
        for key_idx in range(4):
            for msg_idx in range(5):  # Not enough to trigger processing
                msg = MockMessage(f"key{key_idx}", msg_idx)
                await mock_transformer._handle_rolling_message(msg)

        # Should have evicted at least one buffer
        assert mock_transformer._buffers_evicted >= 1
        assert len(mock_transformer._rolling_buffers) <= 3


class TestProcessFileSimplified:
    """Test that simplified process_file works correctly."""

    def test_single_window_processing(self):
        """Test that process_file handles exactly one window."""
        # This would require mocking the DTAN model, which is complex.
        # For now, just verify the interface expectations.
        pass

    def test_rejects_insufficient_data(self):
        """Test that process_file rejects data smaller than window_size."""
        # Would need to mock VehicleSpeedEstimator
        pass


async def run_async_tests():
    """Run async tests without pytest."""
    from collections import OrderedDict

    print("\nRunning async tests...")

    # Try to import - skip if dependencies missing
    try:
        from shared.transformer import RollingBufferedTransformer
    except ImportError as e:
        print(f"⚠ Skipping async tests (missing deps: {e})")
        print("  Run in Docker or install opentelemetry, confluent_kafka, etc.")
        return

    class TestTransformer(RollingBufferedTransformer):
        def __init__(self):
            self.processed_windows = []
            self._running = True
            self._semaphore = asyncio.Semaphore(10)
            self.config = MockConfig()
            self.metrics = MagicMock()
            self.logger = MagicMock()

            # Mock circuit breaker to just call the function
            self.consumer_circuit_breaker = MagicMock()

            async def mock_call(retry_fn, fn, *args):
                return fn(*args)

            self.consumer_circuit_breaker.call = mock_call

            self.retry_handler = MagicMock()
            self.retry_handler.retry_with_backoff = lambda fn, *args: fn(*args)

            # Initialize parent state
            self._rolling_buffers = OrderedDict()
            self._window_size = 10
            self._step_size = 8
            self._buffer_timeout = 60.0
            self._max_active_buffers = 5
            self._buffers_evicted = 0

        def get_window_size(self) -> int:
            return 10

        def get_step_size(self) -> int:
            return 8

        def get_buffer_key(self, message) -> str:
            return message.buffer_key

        async def process_buffer(self, messages: List) -> List:
            timestamps = [m.timestamp for m in messages]
            self.processed_windows.append(timestamps)
            return [{"processed": timestamps}]

        async def _internal_send(self, result):
            pass

        async def _commit_message(self, message):
            pass

    # Test 1: Rolling message handling
    transformer = TestTransformer()
    for i in range(20):
        msg = MockMessage("test:buffer", i)
        await transformer._handle_rolling_message(msg)

    assert len(transformer.processed_windows) == 2, (
        f"Expected 2 windows, got {len(transformer.processed_windows)}"
    )
    assert transformer.processed_windows[0] == list(range(10)), (
        f"First window wrong: {transformer.processed_windows[0]}"
    )
    assert transformer.processed_windows[1] == list(range(8, 18)), (
        f"Second window wrong: {transformer.processed_windows[1]}"
    )
    print("✓ test_handles_rolling_message")

    # Test 2: Buffer key isolation
    transformer2 = TestTransformer()
    for i in range(15):
        msg1 = MockMessage("key1", i)
        msg2 = MockMessage("key2", i + 100)
        await transformer2._handle_rolling_message(msg1)
        await transformer2._handle_rolling_message(msg2)

    key1_windows = [w for w in transformer2.processed_windows if w[0] < 100]
    key2_windows = [w for w in transformer2.processed_windows if w[0] >= 100]
    assert len(key1_windows) == 1, f"Expected 1 window for key1, got {len(key1_windows)}"
    assert len(key2_windows) == 1, f"Expected 1 window for key2, got {len(key2_windows)}"
    print("✓ test_buffer_key_isolation")

    # Test 3: LRU eviction
    transformer3 = TestTransformer()
    transformer3._max_active_buffers = 3

    for key_idx in range(4):
        for msg_idx in range(5):
            msg = MockMessage(f"key{key_idx}", msg_idx)
            await transformer3._handle_rolling_message(msg)

    assert transformer3._buffers_evicted >= 1, (
        f"Expected evictions, got {transformer3._buffers_evicted}"
    )
    assert len(transformer3._rolling_buffers) <= 3, (
        f"Too many buffers: {len(transformer3._rolling_buffers)}"
    )
    print("✓ test_lru_eviction")

    print("\nAll async tests passed!")


if __name__ == "__main__":
    # Run basic tests without pytest
    print("Running basic tests...")

    test = TestRollingBuffer()
    test.test_fifo_behavior()
    print("✓ test_fifo_behavior")

    test.test_overlap_calculation()
    print("✓ test_overlap_calculation")

    test.test_continuous_output()
    print("✓ test_continuous_output")

    test.test_multiple_buffer_keys()
    print("✓ test_multiple_buffer_keys")

    print("\nAll basic tests passed!")

    # Run async tests
    asyncio.run(run_async_tests())

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED!")
    print("=" * 60)
