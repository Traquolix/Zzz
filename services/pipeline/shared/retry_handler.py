import asyncio
import random
from collections.abc import Callable
from typing import Any

from .service_config import ServiceConfig


class RetryHandler:
    def __init__(self, config: ServiceConfig):
        self.max_retries = config.max_retries
        self.initial_delay = config.initial_retry_delay
        self.max_delay = config.max_retry_delay
        self.backoff_multiplier = config.retry_backoff_multiplier

    async def retry_with_backoff(self, func: Callable, *args, **kwargs) -> Any:
        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_exception = e

                if attempt == self.max_retries:
                    raise e

                delay = min(self.initial_delay * (self.backoff_multiplier**attempt), self.max_delay)

                # Add jitter to prevent thundering herd
                jitter = delay * 0.1 * random.random()
                total_delay = delay + jitter

                await asyncio.sleep(total_delay)

        if last_exception is not None:
            raise last_exception
        raise RuntimeError("retry_with_backoff exhausted without exception")
