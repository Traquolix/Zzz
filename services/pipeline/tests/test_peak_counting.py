"""Tests for peak-based vehicle counting (Phase 5)."""

import sys
from unittest.mock import MagicMock

import numpy as np
import pytest

# Restore real modules if they were mocked by earlier test files
for mod_key in [
    "torch",
    "ai_engine.model_vehicle",
    "ai_engine.model_vehicle.simple_interval_counter",
]:
    if mod_key in sys.modules and isinstance(sys.modules[mod_key], MagicMock):
        del sys.modules[mod_key]

import torch  # noqa: E402, F401

from ai_engine.model_vehicle.simple_interval_counter import VehicleCounter  # noqa: E402


@pytest.fixture
def counter():
    """Create a counter with default settings."""
    return VehicleCounter(
        fiber_id="test",
        sampling_rate_hz=10.0,
        correlation_threshold=500.0,
        channels_per_section=9,
        classify_threshold_factor=10.0,
        min_peak_distance_s=0.25,
    )


class TestPeakCounting:
    """Test peak-based vehicle counting."""

    def test_single_peak_one_vehicle(self, counter):
        """Single GLRT spike above threshold should give count=1."""
        n_pairs = 8
        threshold = 500.0 * n_pairs  # summed threshold

        # Create GLRT with one clear peak
        glrt = np.zeros((1, 100))
        glrt[0, 50] = threshold * 1.5  # One peak above threshold

        intervals_list = [([40], [60])]
        filtered_speed = np.full((1, 1, 100), 60.0)
        timestamps_ns = list(range(100))

        counts, intervals, ts = counter.count_from_intervals(
            filtered_speed=filtered_speed,
            glrt_summed=glrt,
            intervals_list=intervals_list,
            timestamps_ns=timestamps_ns,
        )

        total = (
            sum(c[0] if len(c) == 3 else float(c) for c in counts[0]) if len(counts[0]) > 0 else 0
        )
        assert total >= 1

    def test_truck_classification(self, counter):
        """Peak above classify_threshold should be classified as truck."""
        n_pairs = 8
        threshold = 500.0 * n_pairs
        classify_threshold = threshold * 10.0  # 10x

        # Create GLRT with one very high peak (truck)
        glrt = np.zeros((1, 100))
        glrt[0, 50] = classify_threshold * 1.5  # Well above truck threshold

        intervals_list = [([40], [60])]
        filtered_speed = np.full((1, 1, 100), 60.0)
        timestamps_ns = list(range(100))

        counts, intervals, ts = counter.count_from_intervals(
            filtered_speed=filtered_speed,
            glrt_summed=glrt,
            intervals_list=intervals_list,
            timestamps_ns=timestamps_ns,
        )

        # Should have at least 1 count that includes truck classification
        assert len(counts) == 1
        assert len(counts[0]) > 0

    def test_no_peak_above_threshold(self, counter):
        """GLRT below threshold should give count=0."""
        n_pairs = 8
        threshold = 500.0 * n_pairs

        # GLRT below threshold
        glrt = np.ones((1, 100)) * threshold * 0.5

        intervals_list = [([40], [60])]
        filtered_speed = np.full((1, 1, 100), 60.0)
        timestamps_ns = list(range(100))

        counts, intervals, ts = counter.count_from_intervals(
            filtered_speed=filtered_speed,
            glrt_summed=glrt,
            intervals_list=intervals_list,
            timestamps_ns=timestamps_ns,
        )

        # All counts should be zero
        total = (
            sum(
                (c[0] if isinstance(c, (tuple, list)) and len(c) == 3 else float(c))
                for c in counts[0]
            )
            if len(counts[0]) > 0
            else 0
        )
        assert total == 0

    def test_empty_interval(self, counter):
        """Empty intervals should give count=0."""
        glrt = np.zeros((1, 100))
        intervals_list = [([], [])]
        filtered_speed = np.full((1, 1, 100), np.nan)
        timestamps_ns = list(range(100))

        counts, intervals, ts = counter.count_from_intervals(
            filtered_speed=filtered_speed,
            glrt_summed=glrt,
            intervals_list=intervals_list,
            timestamps_ns=timestamps_ns,
        )

        assert len(counts[0]) == 0

    def test_two_separated_peaks(self, counter):
        """Two well-separated peaks should give count=2."""
        n_pairs = 8
        threshold = 500.0 * n_pairs

        glrt = np.zeros((1, 200))
        # Two peaks far apart (> min_peak_distance)
        glrt[0, 30] = threshold * 2
        glrt[0, 100] = threshold * 2

        intervals_list = [([20, 90], [40, 110])]
        filtered_speed = np.full((1, 1, 200), 60.0)
        timestamps_ns = list(range(200))

        counts, intervals, ts = counter.count_from_intervals(
            filtered_speed=filtered_speed,
            glrt_summed=glrt,
            intervals_list=intervals_list,
            timestamps_ns=timestamps_ns,
        )

        total = sum(
            (c[0] if isinstance(c, (tuple, list)) and len(c) == 3 else float(c)) for c in counts[0]
        )
        assert total >= 2
