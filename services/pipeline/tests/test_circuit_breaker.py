"""Tests for CircuitBreaker state machine."""

import pytest
import asyncio
from unittest.mock import patch

from shared.circuit_breaker import CircuitBreaker, CircuitBreakerState


class TestCircuitBreakerStates:
    """Test circuit breaker state transitions."""

    def test_starts_closed(self):
        """Circuit breaker should start in CLOSED state."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10.0)
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_stays_closed_on_success(self):
        """Successful calls should keep circuit closed."""
        cb = CircuitBreaker(failure_threshold=3)

        async def success():
            return "ok"

        result = await cb.call(success)
        assert result == "ok"
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_opens_after_threshold_failures(self):
        """Circuit should open after reaching failure threshold."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10.0)

        async def fail():
            raise ValueError("test error")

        for _ in range(3):
            with pytest.raises(ValueError):
                await cb.call(fail)

        assert cb.state == CircuitBreakerState.OPEN
        assert cb.failure_count == 3

    @pytest.mark.asyncio
    async def test_rejects_calls_when_open(self):
        """Open circuit should reject calls immediately."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=10.0)

        async def fail():
            raise ValueError("test error")

        with pytest.raises(ValueError):
            await cb.call(fail)

        assert cb.state == CircuitBreakerState.OPEN

        async def success():
            return "ok"

        with pytest.raises(Exception, match="Circuit breaker is OPEN"):
            await cb.call(success)

    @pytest.mark.asyncio
    async def test_half_open_after_recovery_timeout(self):
        """Circuit should transition to HALF_OPEN after recovery timeout."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)

        async def fail():
            raise ValueError("test error")

        with pytest.raises(ValueError):
            await cb.call(fail)

        assert cb.state == CircuitBreakerState.OPEN

        await asyncio.sleep(0.02)

        async def success():
            return "ok"

        result = await cb.call(success)
        assert result == "ok"
        assert cb.state == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_closes_on_successful_half_open_call(self):
        """Successful call in HALF_OPEN state should close circuit."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)

        async def fail():
            raise ValueError("test error")

        with pytest.raises(ValueError):
            await cb.call(fail)

        await asyncio.sleep(0.02)

        async def success():
            return "ok"

        result = await cb.call(success)
        assert result == "ok"
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_reopens_on_failed_half_open_call(self):
        """Failed call in HALF_OPEN state should reopen circuit."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)

        async def fail():
            raise ValueError("test error")

        with pytest.raises(ValueError):
            await cb.call(fail)

        await asyncio.sleep(0.02)

        with pytest.raises(ValueError):
            await cb.call(fail)

        assert cb.state == CircuitBreakerState.OPEN


class TestCircuitBreakerConfiguration:
    """Test circuit breaker configuration options."""

    @pytest.mark.asyncio
    async def test_failure_count_increments(self):
        """Failure count should increment on each failure."""
        cb = CircuitBreaker(failure_threshold=5)

        async def fail():
            raise ValueError("test error")

        for i in range(3):
            with pytest.raises(ValueError):
                await cb.call(fail)
            assert cb.failure_count == i + 1

    @pytest.mark.asyncio
    async def test_failure_count_resets_on_success(self):
        """Failure count should reset to 0 on success."""
        cb = CircuitBreaker(failure_threshold=5)

        async def fail():
            raise ValueError("test error")

        async def success():
            return "ok"

        with pytest.raises(ValueError):
            await cb.call(fail)

        with pytest.raises(ValueError):
            await cb.call(fail)

        assert cb.failure_count == 2

        await cb.call(success)
        assert cb.failure_count == 0
