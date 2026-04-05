import logging
from typing import Any

import numpy as np

from processor.processing_tools.math import VectorizedBiquadFilter
from processor.processing_tools.processing_steps.base_step import ProcessingStep

logger = logging.getLogger(__name__)


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
        self._fiber_states: dict[str, dict[str, Any]] = {}

    async def process(self, measurement_data: dict[str, Any]) -> dict[str, Any] | None:
        if measurement_data is None:
            return None

        fiber_id = measurement_data.get("fiber_id", "unknown")
        values = measurement_data.get("values", [])

        if not isinstance(values, np.ndarray):
            values = np.asarray(values, dtype=np.float64)

        # Handle both 1D (channels,) and 2D (samples, channels) input
        channel_count = values.shape[1] if values.ndim == 2 else values.shape[0]

        if channel_count == 0:
            return measurement_data

        # Sanitize non-finite values to prevent permanent filter state contamination.
        # A single NaN/Inf sample would corrupt the IIR filter state for this fiber
        # permanently (sosfilt propagates NaN through its internal delay elements).
        # Replace with 0.0 — neutral for a bandpass filter (DC is rejected).
        non_finite_mask = ~np.isfinite(values)
        if np.any(non_finite_mask):
            n_bad = int(np.sum(non_finite_mask))
            logger.warning(
                "Bandpass filter: %d non-finite values in fiber '%s', replacing with 0.0",
                n_bad,
                fiber_id,
            )
            values = values.copy()
            values[non_finite_mask] = 0.0

        if fiber_id not in self._fiber_states:
            self._fiber_states[fiber_id] = {
                "state": self.filter.create_state(channel_count),
                "channels": channel_count,
            }

        fiber_state = self._fiber_states[fiber_id]

        if fiber_state["channels"] != channel_count:
            fiber_state["state"] = self.filter.create_state(channel_count)
            fiber_state["channels"] = channel_count

        filtered_values = self.filter.filter(values, fiber_state["state"])

        # Bound filter state growth (each fiber_id gets its own state)
        self.cleanup_fiber_states()

        result = measurement_data.copy()
        result["values"] = filtered_values  # Keep as numpy array
        return result

    def cleanup_fiber_states(self, max_fibers: int = 1000):
        if len(self._fiber_states) > max_fibers:
            excess = len(self._fiber_states) - max_fibers
            for _ in range(excess):
                self._fiber_states.pop(next(iter(self._fiber_states)))

    def get_active_fiber_count(self) -> int:
        return len(self._fiber_states)
