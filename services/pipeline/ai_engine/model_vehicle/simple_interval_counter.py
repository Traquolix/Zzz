"""
=============================================================================
TEMPORARY SIMPLE INTERVAL-BASED VEHICLE COUNTING
=============================================================================

This is a TEMPORARY counting solution that counts vehicles directly from
speed detection intervals, ensuring perfect correlation with speed visualizations.

Each speed detection interval = 1 vehicle.

This replaces the 6-minute sliding window approach and provides immediate,
interpretable counts that align with what's visible in the visualizations.

TODO: Recalibrate the neural network once proper feature statistics are collected.

=============================================================================
"""

from __future__ import annotations

import logging
import numpy as np
from typing import List, Tuple

logger = logging.getLogger(__name__)


class SimpleIntervalCounter:
    """TEMPORARY: Counts vehicles directly from speed detection intervals.

    This provides immediate correlation between counts and speed detections
    by counting the same intervals used for speed analysis.

    Args:
        fiber_id: Fiber identifier for logging
    """

    def __init__(self, fiber_id: str = "unknown"):
        self.fiber_id = fiber_id
        self._first_run = True

        if self._first_run:
            logger.warning(
                "=" * 80 + "\n"
                "TEMPORARY SIMPLE INTERVAL COUNTING ACTIVE\n"
                f"Fiber: {fiber_id}\n"
                "Counting vehicles directly from speed detection intervals.\n"
                "Each valid speed interval = 1 vehicle.\n"
                "Perfect correlation with speed visualizations.\n"
                "TODO: Recalibrate neural network normalization.\n"
                + "=" * 80
            )

    def count_from_intervals(
        self,
        filtered_speed: np.ndarray,
        intervals_list: List[Tuple[List[int], List[int]]],
        timestamps_ns: List[int],
    ) -> Tuple[List, List, List]:
        """Count vehicles from speed detection intervals.

        Args:
            filtered_speed: Speed array (sections, channels, time) - already filtered
            intervals_list: Detection intervals [(starts, ends), ...] per section
            timestamps_ns: Timestamps for the window

        Returns:
            Tuple of (counts, intervals, timestamps) matching the format expected downstream
        """
        counts = []

        for section_idx, (starts, ends) in enumerate(intervals_list):
            section_counts = []

            for start, end in zip(starts, ends):
                # Get speed data for this interval
                speed_slice = filtered_speed[section_idx, :, start:end]
                median_speed = np.nanmedian(speed_slice)

                # Count as 1 vehicle if valid speed exists
                if not np.isnan(median_speed) and median_speed != 0:
                    section_counts.append(1.0)
                else:
                    section_counts.append(0.0)

            counts.append(np.array(section_counts))

        if self._first_run:
            total = sum(np.sum(c) for c in counts)
            non_zero = sum(np.count_nonzero(c) for c in counts)
            logger.info(
                f"[TEMPORARY INTERVAL COUNTING] First run: {len(counts)} sections, "
                f"{non_zero} vehicles (from {sum(len(starts) for starts, _ in intervals_list)} intervals)"
            )
            self._first_run = False

        # Return in format expected by counting pipeline
        # counts: list of arrays per section
        # intervals: same as input (already in correct format)
        # timestamps: window timestamps
        return counts, intervals_list, timestamps_ns
