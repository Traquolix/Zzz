"""Tests for CircuitBreaker state machine."""

import asyncio

import pytest

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


class TestHalfOpenRacePrevention:
    """Test that only one trial call is allowed in HALF_OPEN state."""

    @pytest.mark.asyncio
    async def test_only_one_trial_call_allowed(self):
        """Second concurrent call in HALF_OPEN should be rejected."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.05)

        async def fail():
            raise ValueError("boom")

        with pytest.raises(ValueError):
            await cb.call(fail)

        assert cb.state == CircuitBreakerState.OPEN
        await asyncio.sleep(0.1)

        trial_started = asyncio.Event()
        trial_continue = asyncio.Event()

        async def slow_trial():
            trial_started.set()
            await trial_continue.wait()
            return "ok"

        task1 = asyncio.create_task(cb.call(slow_trial))
        await trial_started.wait()

        with pytest.raises(Exception, match="trial in progress"):
            await cb.call(slow_trial)

        trial_continue.set()
        result = await task1
        assert result == "ok"
        assert cb.state == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_trial_flag_cleared_on_failure(self):
        """Trial flag should clear even if the trial call fails."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.05)

        async def fail():
            raise ValueError("boom")

        with pytest.raises(ValueError):
            await cb.call(fail)

        await asyncio.sleep(0.1)

        # Trial fails — flag should be cleared
        with pytest.raises(ValueError):
            await cb.call(fail)

        assert not cb._half_open_trial_active


class TestStateChangeCallback:
    """Test on_state_change callback firing."""

    @pytest.mark.asyncio
    async def test_callback_on_open(self):
        transitions = []
        cb = CircuitBreaker(
            failure_threshold=2,
            recovery_timeout=0.1,
            on_state_change=lambda old, new: transitions.append((old, new)),
        )

        async def fail():
            raise ValueError("boom")

        for _ in range(2):
            with pytest.raises(ValueError):
                await cb.call(fail)

        assert transitions == [("closed", "open")]

    @pytest.mark.asyncio
    async def test_callback_on_recovery(self):
        transitions = []
        cb = CircuitBreaker(
            failure_threshold=1,
            recovery_timeout=0.05,
            on_state_change=lambda old, new: transitions.append((old, new)),
        )

        async def fail():
            raise ValueError("boom")

        async def ok():
            return True

        with pytest.raises(ValueError):
            await cb.call(fail)

        await asyncio.sleep(0.1)
        await cb.call(ok)

        assert ("closed", "open") in transitions
        assert ("half_open", "closed") in transitions

    @pytest.mark.asyncio
    async def test_no_callback_when_state_unchanged(self):
        transitions = []
        cb = CircuitBreaker(
            failure_threshold=3,
            on_state_change=lambda old, new: transitions.append((old, new)),
        )

        async def fail():
            raise ValueError("boom")

        with pytest.raises(ValueError):
            await cb.call(fail)

        assert transitions == []
