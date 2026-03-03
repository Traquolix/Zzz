"""Peak-based vehicle counting with car/truck classification.

Counts vehicles by finding peaks in the summed GLRT signal within each
detection interval, matching the approach from notebook experiment 12.

Each interval may contain multiple vehicles (peaks). Peak height
determines car vs truck classification.
"""

from __future__ import annotations

import logging
from typing import List, Tuple

import numpy as np
from scipy.signal import find_peaks

logger = logging.getLogger(__name__)


def count_peaks_in_segment(
    glrt_segment: np.ndarray,
    threshold: float,
    fs: float,
    classify_threshold: float,
    min_peak_distance_s: float = 0.25,
) -> Tuple[int, int, int]:
    """Count vehicle peaks within a GLRT segment.

    Args:
        glrt_segment: 1D array of GLRT values
        threshold: Detection threshold (summed across pairs)
        fs: Sample rate (Hz)
        classify_threshold: Threshold for truck classification
        min_peak_distance_s: Min seconds between peaks

    Returns:
        (n_vehicles, n_cars, n_trucks)
    """
    if len(glrt_segment) == 0:
        return 0, 0, 0

    min_peak_distance = max(1, int(min_peak_distance_s * fs))
    min_prominence = max(1.0, 0.1 * threshold)

    peaks, props = find_peaks(
        glrt_segment,
        height=threshold,
        distance=min_peak_distance,
        prominence=min_prominence,
    )

    if len(peaks) == 0:
        # No distinct peaks - check if signal exceeds threshold at all
        if len(glrt_segment) > 0 and np.nanmax(glrt_segment) >= threshold:
            if np.nanmax(glrt_segment) >= classify_threshold:
                return 1, 0, 1  # 1 truck
            else:
                return 1, 1, 0  # 1 car
        return 0, 0, 0

    n_vehicles = len(peaks)
    peak_heights = props.get("peak_heights", np.array([]))
    n_trucks = int(np.sum(peak_heights >= classify_threshold))
    n_cars = n_vehicles - n_trucks

    return n_vehicles, n_cars, n_trucks


class SimpleIntervalCounter:
    """Counts vehicles using peak detection in GLRT signal.

    For each detection interval, finds peaks in the summed GLRT and
    classifies them as car or truck based on peak height.

    Args:
        fiber_id: Fiber identifier for logging
        sampling_rate_hz: Sampling rate (Hz)
        correlation_threshold: Per-pair GLRT threshold
        channels_per_section: Number of channels per section (Nch)
        classify_threshold_factor: Peak height > threshold * factor = truck
        min_peak_distance_s: Min seconds between peaks
    """

    def __init__(
        self,
        fiber_id: str = "unknown",
        sampling_rate_hz: float = 10.0,
        correlation_threshold: float = 500.0,
        channels_per_section: int = 9,
        classify_threshold_factor: float = 10.0,
        min_peak_distance_s: float = 0.25,
    ):
        self.fiber_id = fiber_id
        self.fs = sampling_rate_hz
        self.n_pairs = channels_per_section - 1
        self.summed_threshold = correlation_threshold * self.n_pairs
        self.classify_threshold = self.summed_threshold * classify_threshold_factor
        self.min_peak_distance_s = min_peak_distance_s

        logger.info(
            f"Peak counter initialized for '{fiber_id}': "
            f"threshold={self.summed_threshold:.0f}, "
            f"classify={self.classify_threshold:.0f}, "
            f"min_peak_dist={min_peak_distance_s}s"
        )

    def count_from_intervals(
        self,
        filtered_speed: np.ndarray,
        glrt_summed: np.ndarray,
        intervals_list: List[Tuple[List[int], List[int]]],
        timestamps_ns: List[int],
    ) -> Tuple[List, List, List]:
        """Count vehicles from detection intervals using peak detection.

        Args:
            filtered_speed: Speed array (sections, channels, time) - already filtered
            glrt_summed: Summed GLRT array (sections, time)
            intervals_list: Detection intervals [(starts, ends), ...] per section
            timestamps_ns: Timestamps for the window

        Returns:
            Tuple of (counts, intervals, timestamps) matching the format expected downstream.
            Each count entry is a tuple (n_vehicles, n_cars, n_trucks).
        """
        counts = []

        for section_idx, (starts, ends) in enumerate(intervals_list):
            section_counts = []

            for start, end in zip(starts, ends):
                glrt_segment = glrt_summed[section_idx, start:end]
                n_vehicles, n_cars, n_trucks = count_peaks_in_segment(
                    glrt_segment,
                    self.summed_threshold,
                    self.fs,
                    self.classify_threshold,
                    self.min_peak_distance_s,
                )
                section_counts.append((n_vehicles, n_cars, n_trucks))

            counts.append(section_counts)

        return counts, intervals_list, timestamps_ns
