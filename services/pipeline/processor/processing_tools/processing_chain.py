from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from processor.processing_tools.processing_steps.base_step import ProcessingStep

if TYPE_CHECKING:
    from shared.processor_metrics import ProcessorMetrics


class ProcessingChain:
    def __init__(
        self,
        steps: list[ProcessingStep],
        processor_metrics: ProcessorMetrics | None = None,
    ):
        self.steps = steps
        self._metrics = processor_metrics

    async def process(
        self,
        measurement_data: dict[str, Any],
        fiber_id: str = "",
        section: str = "",
    ) -> dict[str, Any] | None:
        current_data: dict[str, Any] | None = measurement_data
        for step in self.steps:
            if current_data is None:
                break
            if self._metrics is not None:
                t0 = time.perf_counter()
                current_data = await step.process(current_data)
                self._metrics.record_step(step.name, time.perf_counter() - t0, fiber_id, section)
            else:
                current_data = await step.process(current_data)
        return current_data

    def get_chain_stats(self) -> dict[str, Any]:
        return {step.name: step.get_stats() for step in self.steps}

    def reset_all_stats(self):
        for step in self.steps:
            step.reset_stats()
