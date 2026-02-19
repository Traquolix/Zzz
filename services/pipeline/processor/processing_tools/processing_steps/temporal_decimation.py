"""Temporal decimation - reduce sampling rate by keeping every Nth sample.

This step reduces the temporal resolution of the signal by selecting
samples at regular intervals.

Example:
    factor=5: 50Hz -> 10Hz (keep every 5th sample)
    factor=10: 100Hz -> 10Hz (keep every 10th sample)
"""

from typing import Any, Dict, Optional

from processor.processing_tools.processing_steps.base_step import ProcessingStep


class TemporalDecimation(ProcessingStep):
    """Reduce sampling rate by keeping every Nth sample.

    Anti-alias filtering note: This step performs naive decimation (sample selection)
    without its own anti-alias filter. It relies on the bandpass filter being applied
    *before* this step in the pipeline ordering. The bandpass filter's high-frequency
    cutoff must be below the post-decimation Nyquist frequency to prevent aliasing.
    For example, with factor=5 and 50 Hz input, the output is 10 Hz, so the bandpass
    high_freq must be < 5 Hz.

    Args:
        factor: Decimation factor (keep every Nth sample)
    """

    def __init__(self, factor: int = 5):
        super().__init__("temporal_decimation")
        if factor < 1:
            raise ValueError(f"factor must be >= 1, got {factor}")
        self.factor = factor
        self._counts = {}

    async def process(self, measurement_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if measurement_data is None:
            return None

        fiber_id = measurement_data.get("fiber_id", "unknown")

        if fiber_id not in self._counts:
            self._counts[fiber_id] = 0

        self._counts[fiber_id] += 1

        if self._counts[fiber_id] % self.factor == 0:
            result = measurement_data.copy()
            original_rate = result.get("sampling_rate_hz")
            if original_rate is None:
                raise ValueError(
                    f"Message from {fiber_id} missing required field 'sampling_rate_hz'. "
                    f"Generator must provide sampling rate."
                )

            result["sampling_rate_hz"] = original_rate / self.factor
            result["temporal_decimation_factor"] = self.factor
            return result

        return None
