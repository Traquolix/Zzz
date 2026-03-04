from typing import Any, Dict, Optional

import numpy as np

from processor.processing_tools.math import VectorizedBiquadFilter
from processor.processing_tools.processing_steps.base_step import ProcessingStep


class BandpassFilter(ProcessingStep):

    def __init__(
        self,
        low_freq: float,
        high_freq: float,
        sampling_rate: float = 50.0,
    ):
        super().__init__("bandpass_filter")

        nyquist = sampling_rate / 2.0
        if high_freq >= nyquist:
            raise ValueError(
                f"high_freq ({high_freq} Hz) must be less than Nyquist frequency "
                f"({nyquist} Hz = sampling_rate {sampling_rate} Hz / 2)"
            )
        if low_freq >= high_freq:
            raise ValueError(
                f"low_freq ({low_freq} Hz) must be less than high_freq ({high_freq} Hz)"
            )

        self.filter = VectorizedBiquadFilter(low_freq, high_freq, sampling_rate)
        self._fiber_states = {}

    async def process(self, measurement_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if measurement_data is None:
            return None

        fiber_id = measurement_data.get("fiber_id", "unknown")
        values = measurement_data.get("values", [])
        channel_count = len(values)

        if channel_count == 0:
            return measurement_data

        if fiber_id not in self._fiber_states:
            self._fiber_states[fiber_id] = {
                "state": self.filter.create_state(channel_count),
                "channels": channel_count,
            }

        fiber_state = self._fiber_states[fiber_id]

        if fiber_state["channels"] != channel_count:
            fiber_state["state"] = self.filter.create_state(channel_count)
            fiber_state["channels"] = channel_count

        values_array = np.array(values, dtype=np.float64)
        filtered_values = self.filter.filter(values_array, fiber_state["state"])

        result = measurement_data.copy()
        result["values"] = filtered_values.tolist()
        return result

    def cleanup_fiber_states(self, max_fibers: int = 1000):
        if len(self._fiber_states) > max_fibers:
            excess = len(self._fiber_states) - max_fibers
            for _ in range(excess):
                self._fiber_states.pop(next(iter(self._fiber_states)))

    def get_active_fiber_count(self) -> int:
        return len(self._fiber_states)
