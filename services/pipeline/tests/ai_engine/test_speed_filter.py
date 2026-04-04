"""Tests for SpeedFilter.

Validates per-channel speed filtering, outlier rejection,
and interval-based speed validation.
"""

from __future__ import annotations

import numpy as np
import pytest

from ai_engine.model_vehicle.speed_filter import SpeedFilter
from ai_engine.model_vehicle.utils import find_ind
from tests.ai_engine.conftest import MAX_SPEED, MIN_SPEED


class TestFilteringSpeed:
    """Tests for multi-section speed filtering."""

    @pytest.fixture
    def speed_filter(self) -> SpeedFilter:
        return SpeedFilter(min_speed=MIN_SPEED, max_speed=MAX_SPEED)

    def test_valid_speeds_preserved(self, speed_filter):
        """Speeds within [min, max] range should be preserved."""
        # 2 sections, 3 pairs, 100 time samples
        speed = np.full((2, 3, 100), 60.0)
        binary = np.ones_like(speed)

        filtered, _intervals = speed_filter.filtering_speed(speed, binary)
        # Valid speed of 60 should survive
        assert not np.all(np.isnan(filtered))

    def test_invalid_speeds_nan(self, speed_filter):
        """Speeds outside [min, max] range should become NaN."""
        speed = np.full((1, 3, 100), 200.0)  # > max_speed
        binary = np.ones_like(speed)

        filtered, _ = speed_filter.filtering_speed(speed, binary)
        # All speeds are 200 > 120, so all intervals should be NaN'd
        non_zero = filtered[filtered != 0]
        assert np.all(np.isnan(non_zero)), "Out-of-range speeds should be NaN"

    def test_masked_regions_zero(self, speed_filter):
        """Regions where binary filter is 0 should be zero in output."""
        speed = np.full((1, 3, 100), 60.0)
        binary = np.zeros_like(speed)  # everything masked

        filtered, _ = speed_filter.filtering_speed(speed, binary)
        np.testing.assert_array_equal(filtered, 0.0)

    def test_output_shape(self, speed_filter):
        """Output shape must match input shape."""
        speed = np.random.default_rng(0).standard_normal((3, 5, 200)) * 30 + 60
        binary = (np.random.default_rng(1).random((3, 5, 200)) > 0.5).astype(float)

        filtered, intervals = speed_filter.filtering_speed(speed, binary)
        assert filtered.shape == speed.shape
        assert len(intervals) == speed.shape[0]

    def test_deterministic(self, speed_filter):
        """Same input must produce identical output."""
        rng = np.random.default_rng(42)
        speed = rng.standard_normal((2, 4, 150)) * 20 + 60
        binary = (rng.random((2, 4, 150)) > 0.3).astype(float)

        f1, _i1 = speed_filter.filtering_speed(speed, binary)
        f2, _i2 = speed_filter.filtering_speed(speed, binary)
        np.testing.assert_array_equal(f1, f2)


class TestFilteringSpeedPerChannel:
    """Tests for single-section per-channel speed filtering."""

    @pytest.fixture
    def speed_filter(self) -> SpeedFilter:
        return SpeedFilter(min_speed=MIN_SPEED, max_speed=MAX_SPEED)

    def test_single_valid_interval(self, speed_filter):
        """A single interval with valid speed should be preserved."""
        speed = np.zeros((3, 100))
        speed[:, 20:50] = 60.0
        binary = np.zeros_like(speed)
        binary[:, 20:50] = 1.0
        intervals = find_ind(binary)

        result = speed_filter.filtering_speed_per_channel(speed, binary, intervals)
        # The interval [20:50] has speed 60 which is valid
        assert np.nanmedian(result[:, 20:50]) == pytest.approx(60.0, abs=1e-10)

    def test_invalid_interval_becomes_nan(self, speed_filter):
        """An interval with speed > max_speed should become NaN."""
        speed = np.zeros((3, 100))
        speed[:, 20:50] = 200.0  # above max
        binary = np.zeros_like(speed)
        binary[:, 20:50] = 1.0
        intervals = find_ind(binary)

        result = speed_filter.filtering_speed_per_channel(speed, binary, intervals)
        # Invalid interval should be NaN
        assert np.all(np.isnan(result[:, 20:50]))


class TestSpeedSampling:
    """Tests for midpoint vs median speed sampling modes."""

    def test_midpoint_and_median_agree_on_constant_speed(self):
        """Both modes should produce identical results when speed is constant."""
        speed = np.zeros((3, 100))
        speed[:, 20:50] = 60.0
        binary = np.zeros_like(speed)
        binary[:, 20:50] = 1.0
        intervals = find_ind(binary)

        midpoint_filter = SpeedFilter(
            min_speed=MIN_SPEED, max_speed=MAX_SPEED, speed_sampling="midpoint"
        )
        median_filter = SpeedFilter(
            min_speed=MIN_SPEED, max_speed=MAX_SPEED, speed_sampling="median"
        )

        r_mid = midpoint_filter.filtering_speed_per_channel(speed.copy(), binary, intervals)
        r_med = median_filter.filtering_speed_per_channel(speed.copy(), binary, intervals)

        np.testing.assert_array_equal(r_mid, r_med)

    def test_median_uses_full_interval(self):
        """Median mode should use all values in the interval, not just midpoint."""
        speed = np.zeros((1, 100))
        # Ramp from 30 to 90 across the interval — midpoint is 60, median is ~60
        speed[0, 20:50] = np.linspace(30, 90, 30)
        binary = np.zeros_like(speed)
        binary[0, 20:50] = 1.0
        intervals = find_ind(binary)

        median_filter = SpeedFilter(
            min_speed=MIN_SPEED, max_speed=MAX_SPEED, speed_sampling="median"
        )
        result = median_filter.filtering_speed_per_channel(speed.copy(), binary, intervals)

        # Median of linspace(30,90,30) = 60, which is valid — interval should be preserved
        assert not np.all(np.isnan(result[0, 20:50]))

    def test_midpoint_samples_center(self):
        """Midpoint mode should use only the center value of the interval."""
        speed = np.zeros((1, 100))
        # Most of interval is valid (60), but midpoint is invalid (200)
        speed[0, 20:50] = 60.0
        mid = (20 + 50) // 2  # = 35
        speed[0, mid] = 200.0  # only midpoint is invalid
        binary = np.zeros_like(speed)
        binary[0, 20:50] = 1.0
        intervals = find_ind(binary)

        midpoint_filter = SpeedFilter(
            min_speed=MIN_SPEED, max_speed=MAX_SPEED, speed_sampling="midpoint"
        )
        result = midpoint_filter.filtering_speed_per_channel(speed.copy(), binary, intervals)

        # Midpoint sees 200 → invalid → NaN the whole interval
        assert np.all(np.isnan(result[0, 20:50]))

    def test_median_survives_bad_midpoint(self):
        """Median mode should survive a bad midpoint if most values are valid."""
        speed = np.zeros((1, 100))
        speed[0, 20:50] = 60.0
        mid = (20 + 50) // 2
        speed[0, mid] = 200.0  # one bad sample at midpoint
        binary = np.zeros_like(speed)
        binary[0, 20:50] = 1.0
        intervals = find_ind(binary)

        median_filter = SpeedFilter(
            min_speed=MIN_SPEED, max_speed=MAX_SPEED, speed_sampling="median"
        )
        result = median_filter.filtering_speed_per_channel(speed.copy(), binary, intervals)

        # Median of 29 values of 60 + 1 value of 200 = 60 → valid → preserved
        assert not np.all(np.isnan(result[0, 20:50]))

    def test_default_is_midpoint(self):
        """Default speed_sampling should be midpoint."""
        sf = SpeedFilter(min_speed=20, max_speed=120)
        assert sf.speed_sampling == "midpoint"
