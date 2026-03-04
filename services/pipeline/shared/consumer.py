import asyncio
from abc import abstractmethod

from shared.message import Message

from .service_base import ServiceBase


class Consumer(ServiceBase):
    # Pattern for pure consumption (no producer infrastructure)
    # Implement consume() to process messages, infrastructure handles Kafka/commit/retry

    @abstractmethod
    async def consume(self, message: Message) -> None:
        # Process message without producing output
        pass

    async def _start_service_loops(self):
        self._tasks.append(asyncio.create_task(self._poll_loop("consumer")))

    async def _dispatch(self, message: Message) -> None:
        await self._execute_with_protection(self.consume, message, message)
