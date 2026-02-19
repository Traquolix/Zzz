"""Tests for RetryHandler backoff logic."""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from shared.retry_handler import RetryHandler
from shared.service_config import ServiceConfig


@pytest.fixture
def retry_config():
    """Config with fast retries for testing."""
    return ServiceConfig(
        kafka_bootstrap_servers="localhost:9092",
        max_retries=3,
        initial_retry_delay=0.01,
        max_retry_delay=0.1,
        retry_backoff_multiplier=2.0,
    )


class TestRetryHandlerBasics:
    """Test basic retry behavior."""

    @pytest.mark.asyncio
    async def test_returns_on_first_success(self, retry_config):
        """Should return immediately on success."""
        handler = RetryHandler(retry_config)

        async def success():
            return "ok"

        result = await handler.retry_with_backoff(success)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_retries_on_failure(self, retry_config):
        """Should retry until success."""
        handler = RetryHandler(retry_config)
        call_count = 0

        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("not yet")
            return "ok"

        result = await handler.retry_with_backoff(fail_then_succeed)
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self, retry_config):
        """Should raise after exhausting retries."""
        handler = RetryHandler(retry_config)
        call_count = 0

        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise ValueError("always fails")

        with pytest.raises(ValueError, match="always fails"):
            await handler.retry_with_backoff(always_fail)

        assert call_count == 4  # Initial + 3 retries


class TestBackoffCalculation:
    """Test exponential backoff timing."""

    @pytest.mark.asyncio
    async def test_exponential_backoff(self, retry_config):
        """Delay should increase exponentially."""
        handler = RetryHandler(retry_config)
        delays = []

        original_sleep = asyncio.sleep

        async def track_delay(delay):
            delays.append(delay)
            await original_sleep(0.001)

        async def always_fail():
            raise ValueError("fail")

        with patch("asyncio.sleep", side_effect=track_delay):
            with pytest.raises(ValueError):
                await handler.retry_with_backoff(always_fail)

        assert len(delays) == 3

        # Check exponential increase (accounting for jitter).
        for i, delay in enumerate(delays):
            expected_base = 0.01 * (2.0 ** i)
            max_jitter = expected_base * 0.1
            assert delay >= expected_base
            assert delay <= expected_base + max_jitter

    @pytest.mark.asyncio
    async def test_max_delay_cap(self):
        """Delay should not exceed max_delay."""
        config = ServiceConfig(
            kafka_bootstrap_servers="localhost:9092",
            max_retries=5,
            initial_retry_delay=1.0,
            max_retry_delay=2.0,
            retry_backoff_multiplier=10.0,
        )
        handler = RetryHandler(config)
        delays = []

        original_sleep = asyncio.sleep

        async def track_delay(delay):
            delays.append(delay)
            await original_sleep(0.001)

        async def always_fail():
            raise ValueError("fail")

        with patch("asyncio.sleep", side_effect=track_delay):
            with pytest.raises(ValueError):
                await handler.retry_with_backoff(always_fail)

        for delay in delays:
            assert delay <= 2.0 + 0.2  # max_delay + max_jitter


class TestRetryHandlerEdgeCases:
    """Test edge cases."""

    @pytest.mark.asyncio
    async def test_zero_retries(self):
        """With zero retries, should fail immediately."""
        config = ServiceConfig(
            kafka_bootstrap_servers="localhost:9092",
            max_retries=0,
            initial_retry_delay=0.01,
            max_retry_delay=0.1,
        )
        handler = RetryHandler(config)
        call_count = 0

        async def fail():
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")

        with pytest.raises(ValueError):
            await handler.retry_with_backoff(fail)

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_preserves_exception_type(self, retry_config):
        """Should preserve the original exception type."""
        handler = RetryHandler(retry_config)

        async def raise_type_error():
            raise TypeError("type error")

        with pytest.raises(TypeError, match="type error"):
            await handler.retry_with_backoff(raise_type_error)

    @pytest.mark.asyncio
    async def test_passes_args_to_function(self, retry_config):
        """Should pass args and kwargs to the function."""
        handler = RetryHandler(retry_config)

        async def add(a, b, c=0):
            return a + b + c

        result = await handler.retry_with_backoff(add, 1, 2, c=3)
        assert result == 6
