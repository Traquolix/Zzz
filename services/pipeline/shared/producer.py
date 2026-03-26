import asyncio
import time
from abc import abstractmethod

from shared.message import Message

from .service_base import ServiceBase


class Producer(ServiceBase):
    # Pattern for continuous message generation (no consumer infrastructure)
    # Implement generate() to create messages, infrastructure handles Kafka/retry/batching

    @abstractmethod
    async def generate(self) -> Message | None:
        # Called continuously - return Message to send or None to skip
        pass

    async def _start_service_loops(self):
        # Start producer loop only
        self.logger.info("Starting Producer loop...")
        self._tasks.append(asyncio.create_task(self._producer_loop()))
        self.logger.info(f"Producer loop task added, total tasks: {len(self._tasks)}")

    async def _producer_loop(self):
        # Generate -> send -> batched flush loop
        last_flush = time.time()
        messages_pending = 0

        while self._running:
            try:
                # Ask service to generate next message
                message = await self.generate()

                if message:
                    success = await self._internal_send(message)
                    if success:
                        messages_pending += 1
                else:
                    # No message to send, brief pause
                    await asyncio.sleep(self.config.producer_idle_delay)

                # Batched flushing - only flush when threshold is met (like V1)
                now = time.time()
                if (
                    messages_pending >= self.config.producer_flush_threshold
                    or (now - last_flush) >= self.config.producer_flush_interval
                ) and messages_pending > 0:
                    # Flush in thread pool to avoid blocking event loop
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(
                        None, self.producer.flush, self.config.kafka_health_check_timeout
                    )
                    messages_pending = 0
                    last_flush = now

            except Exception as e:
                self.logger.error(f"Error in producer loop: {e}")
                self.metrics.record_error("producer_loop")
                await asyncio.sleep(self.config.error_backoff_delay)
