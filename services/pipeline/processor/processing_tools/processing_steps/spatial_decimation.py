"""Spatial decimation - reduce channel count by keeping every Nth channel.

This step reduces the spatial resolution of the signal by selecting
a subset of channels at regular intervals.

Example:
    factor=2: Keep channels 0, 2, 4, 6... (50% reduction)
    factor=4: Keep channels 0, 4, 8, 12... (75% reduction)
"""

from typing import Any, Dict, Optional

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
        channel_start: Optional[int] = None,
        channel_stop: Optional[int] = None,
    ):
        super().__init__("spatial_decimation")
        if factor < 1:
            raise ValueError(f"factor must be >= 1, got {factor}")
        self.factor = factor
        self.channel_start = channel_start
        self.channel_stop = channel_stop

    async def process(self, measurement_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if measurement_data is None:
            return None

        values = measurement_data.get("values", [])
        msg_channel_start = measurement_data.get("channel_start", 0)

        if len(values) == 0:
            return measurement_data

        # Determine slice bounds
        start = self.channel_start
        stop = self.channel_stop

        # Convert absolute channel numbers to local indices
        if start is not None:
            local_start = max(0, start - msg_channel_start)
        else:
            local_start = 0

        if stop is not None:
            local_stop = min(len(values), stop - msg_channel_start)
        else:
            local_stop = len(values)

        # Apply spatial decimation (select every Nth channel)
        selected_values = values[local_start : local_stop : self.factor]

        if len(selected_values) == 0:
            return None

        result = measurement_data.copy()
        result["values"] = selected_values
        result["channel_count"] = len(selected_values)

        # Update channel_start to reflect the first selected channel
        if start is not None:
            result["channel_start"] = max(msg_channel_start, start)
        else:
            result["channel_start"] = msg_channel_start

        # Store decimation factor for downstream processing
        result["spatial_decimation_factor"] = self.factor

        return result
