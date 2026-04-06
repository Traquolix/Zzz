"""Common mode removal processing step for DAS fiber signals.

Removes spatial noise that is common across all fiber channels by subtracting
the spatial median or mean. Maintains per-fiber state with warmup period.
"""

import logging
from typing import Any

import numpy as np

from processor.processing_tools.processing_steps.base_step import (
    ProcessingStep,
)

logger = logging.getLogger(__name__)


class CommonModeRemoval(ProcessingStep):
    """Removes common mode noise from DAS fiber signals.

    Common mode noise is spatial noise that appears consistently across
    all channels. This step computes the spatial median (or mean) across
    all channels and subtracts it from each channel.

    Maintains per-fiber state with a warmup period during which messages
    are dropped to establish stable processing.

    Args:
        warmup_seconds: Duration of warmup period in seconds. Messages
            received during warmup are dropped (return None).
        method: Method for computing common mode. Options:
            - "median": Robust to outliers (default)
            - "mean": Faster but sensitive to outliers
    """

    def __init__(self, warmup_seconds: float = 5.0, method: str = "median"):
        super().__init__("common_mode_removal")
        self.warmup_seconds = warmup_seconds
        self.method = method
        self._fiber_states: dict[str, dict[str, int]] = {}

        if method not in ("median", "mean"):
            raise ValueError(f"Invalid method '{method}'. Must be 'median' or 'mean'.")

        logger.info(f"CommonModeRemoval initialized: warmup={warmup_seconds}s, method={method}")

    async def process(self, measurement_data: dict[str, Any]) -> dict[str, Any] | None:
        """Process a single measurement by removing common mode.

        Args:
            measurement_data: Dict containing:
                - fiber_id: Fiber identifier
                - values: numpy array or list of channel values
                - sampling_rate_hz: Sampling rate
                - ... (other metadata preserved)

        Returns:
            Measurement with common mode removed, or None during warmup period.
        """
        if measurement_data is None:
            return None

        fiber_id = measurement_data.get("fiber_id", "unknown")
        values = measurement_data.get("values", [])

        if not isinstance(values, np.ndarray):
            values = np.asarray(values, dtype=np.float64)

        if values.size == 0:
            return measurement_data

        # Initialize fiber state if first time seeing this fiber
        if fiber_id not in self._fiber_states:
            sampling_rate_hz = measurement_data.get("sampling_rate_hz", 50.0)
            warmup_samples = int(self.warmup_seconds * sampling_rate_hz)
            self._fiber_states[fiber_id] = {
                "count": 0,
                "warmup_samples": warmup_samples,
                "warmup_logged": False,
            }
            logger.info(
                f"Initialized CMR state for fiber '{fiber_id}': warmup_samples={warmup_samples}"
            )

        fiber_state = self._fiber_states[fiber_id]

        # Count actual samples, not messages (batch mode sends multiple samples)
        n_samples = values.shape[0] if values.ndim == 2 else 1

        # During warmup period, drop messages
        if fiber_state["count"] < fiber_state["warmup_samples"]:
            fiber_state["count"] += n_samples
            return None

        # Warmup complete - log once at transition
        if not fiber_state["warmup_logged"]:
            fiber_state["warmup_logged"] = True
            logger.info(
                f"CMR warmup complete for fiber '{fiber_id}' after {fiber_state['count']} samples"
            )

        # Apply common mode removal
        # Use nanmedian/nanmean to prevent a single NaN channel from wiping
        # the entire time sample. With plain median, one NaN makes the median
        # NaN, which then subtracts NaN from all channels in that row.
        is_batch = values.ndim == 2
        if is_batch:
            # 2D (samples, channels): compute median across channels per sample
            if self.method == "median":
                common_mode = np.nanmedian(values, axis=1, keepdims=True)
            else:
                common_mode = np.nanmean(values, axis=1, keepdims=True)
        else:
            # 1D (channels,): compute median across all channels
            common_mode = np.nanmedian(values) if self.method == "median" else np.nanmean(values)

        corrected_values = values - common_mode

        fiber_state["count"] += n_samples

        result = measurement_data.copy()
        result["values"] = corrected_values
        return result

    def estimate_memory_usage(self, num_channels: int = 0, buffer_size: int = 0) -> float:
        """Estimate memory usage for this step.

        Args:
            num_channels: Number of channels being processed
            buffer_size: Number of samples buffered

        Returns:
            Estimated memory in MB
        """
        # State per fiber: ~100 bytes
        # Temporary arrays during processing: 2 * num_channels * 8 bytes (float64)
        state_memory = len(self._fiber_states) * 0.0001  # MB
        temp_memory = 2 * num_channels * 8 / (1024 * 1024)  # MB
        return state_memory + temp_memory
