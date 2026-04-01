"""Speed post-processing: per-channel median filtering and outlier rejection.

Handles:
- filtering_speed: per-section speed filtering
- filtering_speed_per_channel: per-channel interval-based speed validation
"""

from __future__ import annotations

import numpy as np

from .utils import find_ind


class SpeedFilter:
    """Filters unrealistic vehicle speeds based on interval analysis."""

    def __init__(self, min_speed: float, max_speed: float):
        self.min_speed = min_speed
        self.max_speed = max_speed

    def filtering_speed_per_channel(
        self, speed: np.ndarray, binary_filter: np.ndarray, intervals: list
    ) -> np.ndarray:
        """Filters unrealistic speeds from a single section, per channel/pair.

        Args:
            speed: Speed values (channels/pairs, time) for one section
            binary_filter: Binary mask (channels/pairs, time) for one section
            intervals: List of (start_list, end_list) tuples, one per channel

        Returns:
            Filtered speed data with invalid values as NaN
        """
        filtered_data = speed * binary_filter

        for ch_idx in range(speed.shape[0]):
            starts, ends = intervals[ch_idx]

            if len(starts) == 0:
                continue

            starts_arr = np.asarray(starts)
            ends_arr = np.asarray(ends)

            # Compute median speed per interval in one vectorized pass
            vehicle_speeds = np.array(
                [np.nanmedian(filtered_data[ch_idx, s:e]) for s, e in zip(starts_arr, ends_arr)]
            )

            invalid = (vehicle_speeds > self.max_speed) | (vehicle_speeds < self.min_speed)
            invalid_idx = np.where(invalid)[0]

            if len(invalid_idx) > 0:
                # Build a boolean mask for all invalid time samples at once
                nan_mask = np.zeros(filtered_data.shape[1], dtype=bool)
                for idx in invalid_idx:
                    nan_mask[starts_arr[idx] : ends_arr[idx]] = True
                filtered_data[ch_idx, nan_mask] = np.nan

        return filtered_data

    def filtering_speed(self, speed: np.ndarray, binary_filter: np.ndarray) -> tuple:
        """Filters unrealistic speeds from all sections.

        Args:
            speed: 3D array of speed values (sections, channels/pairs, time)
            binary_filter: 3D binary mask for valid intervals

        Returns:
            Tuple of (filtered_speed, intervals_list)
        """
        filtered_data_list = []
        intervals_list = []

        for i in range(speed.shape[0]):
            section_intervals = find_ind(binary_filter[i])
            intervals_list.append(section_intervals)

            filtered_data_per_channel = self.filtering_speed_per_channel(
                speed[i], binary_filter[i], section_intervals
            )
            filtered_data_list.append(filtered_data_per_channel)

        return np.array(filtered_data_list), intervals_list
