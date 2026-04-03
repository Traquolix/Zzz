"""Tests using production parameter values instead of function defaults.

Some function defaults differ from fibers.yaml production values.
These tests ensure behavior is correct with the actual production config.
"""

from __future__ import annotations

import numpy as np

from ai_engine.model_vehicle.utils import count_peaks_in_segment, find_ind_optimised
from tests.ai_engine.conftest import SAMPLING_RATE_HZ

# Production values from fibers.yaml
PRODUCTION_MIN_PEAK_DISTANCE_S = 1.2
PRODUCTION_CORR_THRESHOLD = 500.0
PRODUCTION_CLASSIFY_FACTOR = 2.0


class TestCountPeaksProductionParams:
    """Peak counting tests with production min_peak_distance_s=1.2."""

    def test_single_peak_production_headway(self):
        """Single peak should be counted with production 1.2s headway."""
        segment = np.zeros(100)
        segment[50] = 1000
        n_v, _n_c, _n_t = count_peaks_in_segment(
            segment,
            detect_threshold=500,
            classify_threshold=2000,
            sampling_rate_hz=SAMPLING_RATE_HZ,
            min_peak_distance_s=PRODUCTION_MIN_PEAK_DISTANCE_S,
        )
        assert n_v >= 1

    def test_two_peaks_within_headway_merged(self):
        """Two peaks closer than 1.2s should be counted as one vehicle.

        At 10.4167 Hz, 1.2s = ~12.5 samples. Peaks at 5 samples apart
        should be merged.
        """
        segment = np.zeros(100)
        segment[40] = 1000
        segment[45] = 1200  # 5 samples apart << 12.5 sample headway
        n_v, _n_c, _n_t = count_peaks_in_segment(
            segment,
            detect_threshold=500,
            classify_threshold=2000,
            sampling_rate_hz=SAMPLING_RATE_HZ,
            min_peak_distance_s=PRODUCTION_MIN_PEAK_DISTANCE_S,
        )
        assert n_v == 1, f"Expected 1 vehicle (peaks within headway), got {n_v}"

    def test_two_peaks_beyond_headway_separated(self):
        """Two peaks further than 1.2s apart should be counted separately.

        At 10.4167 Hz, 1.2s ≈ 12.5 samples. Peaks 20 samples apart are beyond.
        """
        segment = np.zeros(100)
        segment[30] = 1000
        segment[55] = 1100  # 25 samples apart >> 12.5 sample headway
        n_v, _n_c, _n_t = count_peaks_in_segment(
            segment,
            detect_threshold=500,
            classify_threshold=2000,
            sampling_rate_hz=SAMPLING_RATE_HZ,
            min_peak_distance_s=PRODUCTION_MIN_PEAK_DISTANCE_S,
        )
        assert n_v == 2, f"Expected 2 vehicles (peaks beyond headway), got {n_v}"

    def test_truck_classification_with_production_threshold(self):
        """With production classify_threshold_factor=2.0, peaks at 2x detect are trucks."""
        detect_thr = 500
        classify_thr = detect_thr * PRODUCTION_CLASSIFY_FACTOR
        segment = np.zeros(100)
        segment[30] = detect_thr * 3  # well above classify threshold → truck
        segment[70] = detect_thr * 1.5  # above detect but below classify → car

        n_v, n_c, n_t = count_peaks_in_segment(
            segment,
            detect_threshold=detect_thr,
            classify_threshold=classify_thr,
            sampling_rate_hz=SAMPLING_RATE_HZ,
            min_peak_distance_s=PRODUCTION_MIN_PEAK_DISTANCE_S,
        )
        assert n_v == 2
        assert n_t >= 1, f"Expected at least 1 truck, got {n_t}"
        assert n_c >= 1, f"Expected at least 1 car, got {n_c}"

    def test_three_vehicles_with_production_spacing(self):
        """Three well-separated peaks should produce 3 vehicles."""
        # At 10.4167 Hz, need peaks > 12.5 samples apart
        segment = np.zeros(200)
        segment[20] = 1000
        segment[60] = 1200  # 40 samples apart (3.8s) ✓
        segment[120] = 900  # 60 samples apart (5.8s) ✓

        n_v, _n_c, _n_t = count_peaks_in_segment(
            segment,
            detect_threshold=500,
            classify_threshold=2000,
            sampling_rate_hz=SAMPLING_RATE_HZ,
            min_peak_distance_s=PRODUCTION_MIN_PEAK_DISTANCE_S,
        )
        assert n_v == 3, f"Expected 3 vehicles, got {n_v}"

    def test_below_threshold_no_peaks(self):
        """All peaks below detect_threshold should produce 0 vehicles."""
        segment = np.full(100, 200.0)  # all below 500 threshold
        n_v, _n_c, _n_t = count_peaks_in_segment(
            segment,
            detect_threshold=500,
            classify_threshold=1000,
            sampling_rate_hz=SAMPLING_RATE_HZ,
            min_peak_distance_s=PRODUCTION_MIN_PEAK_DISTANCE_S,
        )
        assert n_v == 0

    def test_plateau_above_threshold_counted(self):
        """A flat plateau above threshold (no clear peak) should still count."""
        segment = np.zeros(100)
        segment[30:60] = 800  # flat plateau above 500 threshold
        n_v, _n_c, _n_t = count_peaks_in_segment(
            segment,
            detect_threshold=500,
            classify_threshold=1000,
            sampling_rate_hz=SAMPLING_RATE_HZ,
            min_peak_distance_s=PRODUCTION_MIN_PEAK_DISTANCE_S,
        )
        # find_peaks may not find a peak in flat data, but the fallback
        # (checking nanmax >= threshold) should still count 1
        assert n_v >= 1, "Plateau above threshold should count as at least 1 vehicle"


class TestFindIndEdgeCases:
    """Edge cases for find_ind_optimised / find_ind."""

    def test_single_element_one(self):
        """[1] → one interval from 0 to 1."""
        starts, ends = find_ind_optimised(np.array([1.0]))
        assert starts == [0]
        assert ends == [1]

    def test_single_element_zero(self):
        """[0] → no intervals."""
        starts, ends = find_ind_optimised(np.array([0.0]))
        assert starts == []
        assert ends == []

    def test_alternating_01(self):
        """[0,1,0,1,0] → two single-sample intervals."""
        starts, ends = find_ind_optimised(np.array([0, 1, 0, 1, 0]))
        assert starts == [1, 3]
        assert ends == [2, 4]

    def test_alternating_10(self):
        """[1,0,1,0,1] → three single-sample intervals."""
        starts, ends = find_ind_optimised(np.array([1, 0, 1, 0, 1]))
        assert starts == [0, 2, 4]
        assert ends == [1, 3, 5]

    def test_starts_with_one(self):
        """[1,1,0,0] → one interval from 0 to 2."""
        starts, ends = find_ind_optimised(np.array([1, 1, 0, 0]))
        assert starts == [0]
        assert ends == [2]

    def test_ends_with_one(self):
        """[0,0,1,1] → one interval from 2 to 4."""
        starts, ends = find_ind_optimised(np.array([0, 0, 1, 1]))
        assert starts == [2]
        assert ends == [4]

    def test_two_elements_01(self):
        """[0,1] → one interval from 1 to 2."""
        starts, ends = find_ind_optimised(np.array([0, 1]))
        assert starts == [1]
        assert ends == [2]

    def test_two_elements_10(self):
        """[1,0] → one interval from 0 to 1."""
        starts, ends = find_ind_optimised(np.array([1, 0]))
        assert starts == [0]
        assert ends == [1]

    def test_two_elements_11(self):
        """[1,1] → one interval from 0 to 2."""
        starts, ends = find_ind_optimised(np.array([1, 1]))
        assert starts == [0]
        assert ends == [2]

    def test_long_all_ones(self):
        """Long array of all ones → single interval."""
        arr = np.ones(1000)
        starts, ends = find_ind_optimised(arr)
        assert starts == [0]
        assert ends == [1000]

    def test_long_all_zeros(self):
        """Long array of all zeros → no intervals."""
        arr = np.zeros(1000)
        starts, ends = find_ind_optimised(arr)
        assert starts == []
        assert ends == []
