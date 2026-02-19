import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from opentelemetry import trace

from shared.otel_setup import get_correlation_id


class ProcessingStep(ABC):

    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        self.name = name
        self.config = config or {}
        self.logger = logging.getLogger(f"processing.{name}")
        self.tracer = trace.get_tracer(__name__)
        self._call_count = 0
        self._total_processing_time_ms = 0.0

    @abstractmethod
    async def process(self, measurement_data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    def estimate_memory_usage(self) -> float:
        return 10.0  # Conservative default.

    def get_stats(self) -> Dict[str, Any]:
        """Return step statistics for monitoring."""
        return {
            "call_count": self._call_count,
            "total_processing_time_ms": self._total_processing_time_ms,
        }

    def reset_stats(self) -> None:
        """Reset step statistics."""
        self._call_count = 0
        self._total_processing_time_ms = 0.0

    async def process_with_stats(self, measurement_data: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()
        self._call_count += 1

        with self.tracer.start_as_current_span(f"processing.{self.name}") as span:
            try:
                correlation_id = get_correlation_id()
                if correlation_id:
                    span.set_attribute("correlation_id", correlation_id)

                span.set_attribute("processing_step", self.name)

                if isinstance(measurement_data, dict):
                    fiber_id = measurement_data.get("fiber_id")
                    if fiber_id:
                        span.set_attribute("fiber_id", fiber_id)

                result = await self.process(measurement_data)
                span.set_attribute("processing.success", True)

                elapsed_ms = (time.time() - start_time) * 1000
                self._total_processing_time_ms += elapsed_ms

                return result

            except Exception as e:
                span.record_exception(e)
                span.set_attribute("processing.success", False)
                self.logger.error(f"Processing error in {self.name}: {e}")
                raise
