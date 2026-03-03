"""Tests for compute_speed_from_pairs (Phase 3.2)."""

import sys
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.modules.setdefault("matplotlib", MagicMock())
sys.modules.setdefault("matplotlib.pyplot", MagicMock())

from ai_engine.model_vehicle.utils import compute_speed_from_pairs


class TestComputeSpeedFromPairs:
    """Test per-pair speed aggregation."""

    def test_median_weighting(self):
        """Median weighting returns median of valid speeds."""
        glrt = np.array([[100.0, 100.0], [100.0, 100.0], [100.0, 100.0]])
        speed = np.array([[50.0, 60.0], [55.0, 65.0], [60.0, 70.0]])
        result = compute_speed_from_pairs(glrt, speed, weighting="median")
        # At t=0: median of [50, 55, 60] = 55
        assert result[0] == pytest.approx(55.0)

    def test_glrt_weighting(self):
        """GLRT-weighted average uses GLRT as weights."""
        glrt = np.array([[100.0], [200.0]])
        speed = np.array([[60.0], [90.0]])
        result = compute_speed_from_pairs(glrt, speed, weighting="glrt")
        # Weighted average: (60*100 + 90*200) / (100 + 200) = 24000/300 = 80
        assert result[0] == pytest.approx(80.0)

    def test_filters_out_of_range_speeds(self):
        """Speeds outside [min_speed, max_speed] should be excluded."""
        glrt = np.array([[100.0], [100.0], [100.0]])
        speed = np.array([[10.0], [60.0], [150.0]])  # 10 too low, 150 too high
        result = compute_speed_from_pairs(glrt, speed, min_speed=20, max_speed=120)
        assert result[0] == pytest.approx(60.0)

    def test_positive_glrt_only(self):
        """Only pairs with positive GLRT should be used."""
        glrt = np.array([[-50.0], [100.0], [200.0]])
        speed = np.array([[60.0], [80.0], [90.0]])
        result = compute_speed_from_pairs(glrt, speed, positive_glrt_only=True, weighting="median")
        # Should only use pairs with GLRT > 0: [80, 90] -> median = 85
        assert result[0] == pytest.approx(85.0)

    def test_all_nan_returns_nan(self):
        """No valid speeds should return NaN."""
        glrt = np.array([[100.0]])
        speed = np.array([[np.nan]])
        result = compute_speed_from_pairs(glrt, speed)
        assert np.isnan(result[0])

    def test_single_valid_pair(self):
        """One pair in range returns that speed."""
        glrt = np.array([[100.0], [-10.0], [-20.0]])
        speed = np.array([[75.0], [80.0], [85.0]])
        result = compute_speed_from_pairs(glrt, speed, positive_glrt_only=True)
        assert result[0] == pytest.approx(75.0)

    def test_handles_mixed_nan_and_valid(self):
        """Partial NaN data should use only valid entries."""
        glrt = np.array([[100.0], [200.0], [300.0]])
        speed = np.array([[np.nan], [70.0], [80.0]])
        result = compute_speed_from_pairs(glrt, speed, weighting="median")
        # Only valid: [70, 80] -> median = 75
        assert result[0] == pytest.approx(75.0)

    def test_output_shape(self):
        """Output should have shape (n_time,)."""
        glrt = np.random.default_rng(42).standard_normal((8, 250))
        speed = np.abs(np.random.default_rng(42).standard_normal((8, 250))) * 60 + 30
        result = compute_speed_from_pairs(glrt, speed)
        assert result.shape == (250,)
