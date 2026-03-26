import asyncio
import time
from collections.abc import Callable
from enum import Enum


class CircuitBreakerState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        on_state_change: Callable | None = None,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitBreakerState.CLOSED
        self._lock = asyncio.Lock()
        self._half_open_trial_active = False
        self._on_state_change = on_state_change

    async def call(self, func: Callable, *args, **kwargs):
        async with self._lock:
            if self.state == CircuitBreakerState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitBreakerState.HALF_OPEN
                else:
                    raise Exception("Circuit breaker is OPEN")

            if self.state == CircuitBreakerState.HALF_OPEN:
                if self._half_open_trial_active:
                    raise Exception("Circuit breaker is HALF_OPEN (trial in progress)")
                self._half_open_trial_active = True

        try:
            result = await func(*args, **kwargs)
            async with self._lock:
                self._half_open_trial_active = False
                self._on_success()
            return result
        except Exception:
            async with self._lock:
                self._half_open_trial_active = False
                self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        return (
            self.last_failure_time and time.time() - self.last_failure_time >= self.recovery_timeout
        )

    def _on_success(self):
        old_state = self.state
        self.failure_count = 0
        self.state = CircuitBreakerState.CLOSED
        if old_state != self.state and self._on_state_change:
            self._on_state_change(old_state.value, self.state.value)

    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        old_state = self.state
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN
        if old_state != self.state and self._on_state_change:
            self._on_state_change(old_state.value, self.state.value)
