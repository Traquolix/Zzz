"""Health check server and monitoring for service patterns."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from aiohttp import web

if TYPE_CHECKING:
    from .service_base import ServiceBase

logger = logging.getLogger(__name__)


class HealthMixin:
    """Mixin providing health check endpoints and monitoring."""

    async def _start_health_server(self: "ServiceBase") -> None:
        """Start HTTP server for health check endpoints."""
        self._health_app = web.Application()
        self._health_app.router.add_get("/healthz", self._liveness_check)
        self._health_app.router.add_get("/readyz", self._readiness_check)
        self._health_app.router.add_get("/metrics", self._metrics_endpoint)

        self._health_runner = web.AppRunner(self._health_app)
        await self._health_runner.setup()

        site = web.TCPSite(self._health_runner, "0.0.0.0", 8080)
        await site.start()
        self.logger.info("Health check server started on port 8080")

    async def _liveness_check(self: "ServiceBase", request: web.Request) -> web.Response:
        """Liveness probe - is process alive and not deadlocked?"""
        return web.json_response(
            {"status": "ok", "service": self.service_name, "type": self.service_type.value}
        )

    async def _readiness_check(self: "ServiceBase", request: web.Request) -> web.Response:
        """Readiness probe - ready to accept traffic?"""
        checks = {
            "service_running": self._running,
            "kafka_consumer_ready": (
                self.consumer is not None if hasattr(self, "consumer") else True
            ),
            "kafka_producer_ready": (
                self.producer is not None if hasattr(self, "producer") else True
            ),
        }

        if hasattr(self, "consumer_circuit_breaker"):
            from shared.circuit_breaker import CircuitState

            checks["consumer_circuit_breaker"] = (
                self.consumer_circuit_breaker.state != CircuitState.OPEN
            )

        if hasattr(self, "producer_circuit_breaker"):
            from shared.circuit_breaker import CircuitState

            checks["producer_circuit_breaker"] = (
                self.producer_circuit_breaker.state != CircuitState.OPEN
            )

        is_ready = all(checks.values())
        status_code = 200 if is_ready else 503

        return web.json_response(
            {
                "status": "ready" if is_ready else "not_ready",
                "service": self.service_name,
                "checks": checks,
            },
            status=status_code,
        )

    async def _metrics_endpoint(self: "ServiceBase", request: web.Request) -> web.Response:
        """Expose metrics in Prometheus-compatible format."""
        metrics_summary = self.metrics.get_summary()
        return web.json_response(
            {
                "service": self.service_name,
                "metrics": metrics_summary,
                "dlq_stats": self.dead_letter_queue.get_stats() if self.dead_letter_queue else None,
            }
        )

    async def _health_check_loop(self: "ServiceBase") -> None:
        """Periodic health logging with metrics and circuit breaker status."""
        while self._running:
            await asyncio.sleep(self.config.health_check_interval)

            health_info = [
                f"Metrics: {self.metrics.get_summary()}",
                f"Type: {self.service_type.value}",
            ]

            if hasattr(self, "consumer_circuit_breaker"):
                health_info.append(f"Consumer CB: {self.consumer_circuit_breaker.state.value}")
            if hasattr(self, "producer_circuit_breaker"):
                health_info.append(f"Producer CB: {self.producer_circuit_breaker.state.value}")

            if self.dead_letter_queue:
                dlq_stats = self.dead_letter_queue.get_stats()
                health_info.append(f"DLQ: {dlq_stats.get('total_messages', 0)} messages")

            self.logger.info(" | ".join(health_info))

    async def _monitor_consumer_lag(self: "ServiceBase") -> None:
        """Monitor Kafka consumer lag periodically."""
        while self._running:
            await asyncio.sleep(30.0)

            try:
                partitions = self.consumer.assignment()

                for partition in partitions:
                    committed = self.consumer.committed([partition])[0]
                    if committed is None:
                        continue

                    low, high = self.consumer.get_watermark_offsets(partition)
                    lag = high - committed.offset

                    self.metrics.record_consumer_lag(partition.topic, partition.partition, lag)

                    if lag > 1000:
                        self.logger.warning(
                            f"High consumer lag: {partition.topic}[{partition.partition}] "
                            f"lag={lag} messages"
                        )

            except Exception as e:
                self.logger.debug(f"Error monitoring lag: {e}")

    async def _log_final_metrics(self: "ServiceBase") -> None:
        """Log final stats on shutdown."""
        summary = self.metrics.get_summary()

        final_info = [f"Final metrics for {self.service_name}: {summary}"]

        if hasattr(self, "consumer_circuit_breaker"):
            final_info.append(
                f"Consumer CB final state: {self.consumer_circuit_breaker.state.value}"
            )
        if hasattr(self, "producer_circuit_breaker"):
            final_info.append(
                f"Producer CB final state: {self.producer_circuit_breaker.state.value}"
            )

        if self.dead_letter_queue:
            dlq_stats = self.dead_letter_queue.get_stats()
            final_info.append(f"DLQ final stats: {dlq_stats}")

        for info in final_info:
            self.logger.info(info)
