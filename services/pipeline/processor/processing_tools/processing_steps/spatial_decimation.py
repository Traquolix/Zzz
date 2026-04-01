"""Spatial decimation - reduce channel count by keeping every Nth channel.

This step reduces the spatial resolution of the signal by selecting
a subset of channels at regular intervals.

Example:
    factor=2: Keep channels 0, 2, 4, 6... (50% reduction)
    factor=4: Keep channels 0, 4, 8, 12... (75% reduction)
"""

from typing import Any

import numpy as np

from processor.processing_tools.processing_steps.base_step import ProcessingStep


class SpatialDecimation(ProcessingStep):
    """Reduce channel count by keeping every Nth channel.

    Args:
        factor: Decimation factor (keep every Nth channel)
        channel_start: Starting channel for selection (default: from config)
        channel_stop: Ending channel for selection (default: from config)
    """

    def __init__(
        self,
        factor: int = 1,
        channel_start: int | None = None,
        channel_stop: int | None = None,
    ):
        super().__init__("spatial_decimation")
        if factor < 1:
            raise ValueError(f"factor must be >= 1, got {factor}")
        self.factor = factor
        self.channel_start = channel_start
        self.channel_stop = channel_stop

    async def process(self, measurement_data: dict[str, Any]) -> dict[str, Any] | None:
        if measurement_data is None:
            return None

        # Support both 1D (channels,) and 2D (samples, channels) input
        values = measurement_data.get("values", [])
        if not isinstance(values, np.ndarray):
            values = np.asarray(values, dtype=np.float64)

        is_batch = values.ndim == 2
        n_channels = values.shape[1] if is_batch else values.shape[0]

        if n_channels == 0:
            return measurement_data

        msg_channel_start = measurement_data.get("channel_start", 0)

        local_start = (
            max(0, self.channel_start - msg_channel_start) if self.channel_start is not None else 0
        )
        local_stop = (
            min(n_channels, self.channel_stop - msg_channel_start)
            if self.channel_stop is not None
            else n_channels
        )

        if is_batch:
            selected_values = values[:, local_start : local_stop : self.factor]
        else:
            selected_values = values[local_start : local_stop : self.factor]

        out_channels = selected_values.shape[1] if is_batch else selected_values.shape[0]
        if out_channels == 0:
            return None

        result = measurement_data.copy()
        result["values"] = selected_values
        result["channel_count"] = out_channels

        if self.channel_start is not None:
            result["channel_start"] = max(msg_channel_start, self.channel_start)
        else:
            result["channel_start"] = msg_channel_start

        result["spatial_decimation_factor"] = self.factor

        return result
