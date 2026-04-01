"""Temporal decimation - reduce sampling rate by keeping every Nth sample.

This step reduces the temporal resolution of the signal by selecting
samples at regular intervals.

Example:
    factor=5: 50Hz -> 10Hz (keep every 5th sample)
    factor=10: 100Hz -> 10Hz (keep every 10th sample)
"""

from typing import Any

import numpy as np

from processor.processing_tools.processing_steps.base_step import ProcessingStep


class TemporalDecimation(ProcessingStep):
    """Reduce sampling rate by keeping every Nth sample.

    Supports both single-sample (1D values) and batch (2D values) input.
    For batch input, selects the subset of samples where the global counter
    is divisible by the decimation factor.

    Anti-alias filtering note: This step performs naive decimation (sample selection)
    without its own anti-alias filter. It relies on the bandpass filter being applied
    *before* this step in the pipeline ordering. The bandpass filter's high-frequency
    cutoff must be below the post-decimation Nyquist frequency to prevent aliasing.

    Args:
        factor: Decimation factor (keep every Nth sample)
    """

    def __init__(self, factor: int = 5):
        super().__init__("temporal_decimation")
        if factor < 1:
            raise ValueError(f"factor must be >= 1, got {factor}")
        self.factor = factor
        self._counts: dict[str, int] = {}

    async def process(self, measurement_data: dict[str, Any]) -> dict[str, Any] | None:
        if measurement_data is None:
            return None

        fiber_id = measurement_data.get("fiber_id", "unknown")
        values = measurement_data.get("values")

        if fiber_id not in self._counts:
            self._counts[fiber_id] = 0

        original_rate = measurement_data.get("sampling_rate_hz")
        if original_rate is None:
            raise ValueError(
                f"Message from {fiber_id} missing required field 'sampling_rate_hz'. "
                f"Generator must provide sampling rate."
            )

        if isinstance(values, np.ndarray) and values.ndim == 2:
            # Batch mode: values is (samples, channels)
            n_samples = values.shape[0]
            global_count = self._counts[fiber_id]

            # Find which samples in this batch to keep
            sample_indices = np.arange(global_count + 1, global_count + 1 + n_samples)
            keep_mask = sample_indices % self.factor == 0
            self._counts[fiber_id] = global_count + n_samples

            if not np.any(keep_mask):
                return None

            kept_values = values[keep_mask]

            # Also select corresponding timestamps
            timestamps_ns = measurement_data.get("timestamps_ns")
            kept_timestamps = None
            if timestamps_ns is not None:
                kept_timestamps = np.asarray(timestamps_ns)[keep_mask]

            result = measurement_data.copy()
            result["values"] = kept_values
            result["sampling_rate_hz"] = original_rate / self.factor
            result["temporal_decimation_factor"] = self.factor
            if kept_timestamps is not None:
                result["timestamps_ns"] = kept_timestamps.tolist()
            return result
        else:
            # Single-sample mode (original behavior)
            self._counts[fiber_id] += 1

            if self._counts[fiber_id] % self.factor == 0:
                result = measurement_data.copy()
                result["sampling_rate_hz"] = original_rate / self.factor
                result["temporal_decimation_factor"] = self.factor
                return result

            return None
