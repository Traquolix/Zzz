"""Extended tests for utils.py functions that previously had no coverage.

Covers compute_speed_from_pairs, normalize_windows, and AIMetrics.
"""

from __future__ import annotations

import numpy as np

from ai_engine.model_vehicle.utils import compute_speed_from_pairs, normalize_windows


class TestComputeSpeedFromPairs:
    """Tests for GLRT-weighted and median speed computation from pairs."""

    def test_median_mode_basic(self):
        """Median mode should return median of valid speeds."""
        n_pairs, n_time = 4, 10
        glrt = np.ones((n_pairs, n_time)) * 100  # all positive
        speed = np.full((n_pairs, n_time), 60.0)  # all 60 km/h

        result = compute_speed_from_pairs(
            glrt, speed, min_speed=20, max_speed=120, positive_glrt_only=False, weighting="median"
        )

        assert result.shape == (n_time,)
        np.testing.assert_allclose(result, 60.0)

    def test_glrt_weighted_mode(self):
        """GLRT-weighted mode should weight speeds by GLRT value."""
        _n_pairs, _n_time = 2, 1
        glrt = np.array([[100.0], [300.0]])  # pair 1 has 3x weight
        speed = np.array([[40.0], [80.0]])

        result = compute_speed_from_pairs(
            glrt, speed, min_speed=20, max_speed=120, positive_glrt_only=True, weighting="glrt"
        )

        # Weighted: (40*100 + 80*300) / (100+300) = 28000/400 = 70
        assert result.shape == (1,)
        np.testing.assert_allclose(result[0], 70.0, rtol=1e-10)

    def test_nan_speeds_excluded(self):
        """NaN speed values should be excluded from computation."""
        n_pairs, n_time = 3, 5
        glrt = np.ones((n_pairs, n_time)) * 100
        speed = np.full((n_pairs, n_time), 60.0)
        speed[0, :] = np.nan  # first pair all NaN

        result = compute_speed_from_pairs(
            glrt, speed, min_speed=20, max_speed=120, positive_glrt_only=False, weighting="median"
        )

        # Should still work with 2 valid pairs
        valid = result[~np.isnan(result)]
        np.testing.assert_allclose(valid, 60.0)

    def test_out_of_range_speeds_excluded(self):
        """Speeds outside [min, max] should be excluded."""
        n_pairs, n_time = 3, 5
        glrt = np.ones((n_pairs, n_time)) * 100
        speed = np.full((n_pairs, n_time), 60.0)
        speed[0, :] = 5.0  # below min_speed=20
        speed[1, :] = 200.0  # above max_speed=120

        result = compute_speed_from_pairs(
            glrt, speed, min_speed=20, max_speed=120, positive_glrt_only=False, weighting="median"
        )

        valid = result[~np.isnan(result)]
        np.testing.assert_allclose(valid, 60.0)  # only pair 2 is valid

    def test_all_invalid_returns_nan(self):
        """If all speeds are invalid, result should be NaN."""
        n_pairs, n_time = 2, 3
        glrt = np.ones((n_pairs, n_time)) * 100
        speed = np.full((n_pairs, n_time), 200.0)  # all above max

        result = compute_speed_from_pairs(
            glrt, speed, min_speed=20, max_speed=120, positive_glrt_only=False, weighting="median"
        )

        assert np.all(np.isnan(result))

    def test_negative_glrt_excluded_when_positive_only(self):
        """With positive_glrt_only=True, negative GLRT pairs are excluded."""
        _n_pairs, _n_time = 2, 1
        glrt = np.array([[100.0], [-50.0]])  # pair 1 negative
        speed = np.array([[60.0], [80.0]])

        result = compute_speed_from_pairs(
            glrt, speed, min_speed=20, max_speed=120, positive_glrt_only=True, weighting="median"
        )

        np.testing.assert_allclose(result[0], 60.0)  # only pair 0 used

    def test_output_shape(self):
        """Output shape should be (n_time,)."""
        n_pairs, n_time = 5, 20
        glrt = np.ones((n_pairs, n_time))
        speed = np.full((n_pairs, n_time), 60.0)

        result = compute_speed_from_pairs(
            glrt, speed, min_speed=20, max_speed=120, positive_glrt_only=False, weighting="median"
        )

        assert result.shape == (n_time,)


class TestNormalizeWindows:
    """Tests for z-score window normalization."""

    def test_output_zero_mean(self):
        """After normalization, each window should have approximately zero mean."""
        space_split = np.random.default_rng(42).standard_normal((5, 9, 312)) + 10.0
        result = normalize_windows(space_split.copy())

        for i in range(result.shape[0]):
            window_mean = result[i].mean()
            assert abs(window_mean) < 1e-6, f"Window {i} mean={window_mean}"

    def test_output_unit_std(self):
        """After normalization, each window should have approximately unit std."""
        space_split = np.random.default_rng(42).standard_normal((5, 9, 312)) * 10.0
        result = normalize_windows(space_split.copy())

        for i in range(result.shape[0]):
            window_std = result[i].std()
            assert abs(window_std - 1.0) < 0.01, f"Window {i} std={window_std}"

    def test_output_shape_preserved(self):
        """Output shape must match input shape."""
        space_split = np.random.default_rng(42).standard_normal((3, 9, 312))
        result = normalize_windows(space_split.copy())
        assert result.shape == space_split.shape

    def test_zero_window_no_crash(self):
        """All-zero window should not crash (epsilon prevents division by zero)."""
        space_split = np.zeros((1, 9, 312))
        result = normalize_windows(space_split.copy())
        assert np.all(np.isfinite(result))

    def test_known_values(self):
        """Test with known input for manual verification."""
        # Single window: 2 channels, 3 samples, constant value 6.0
        space_split = np.full((1, 2, 3), 6.0)
        result = normalize_windows(space_split.copy())

        # mean=6.0, std≈epsilon → (6-6)/(eps) ≈ 0
        np.testing.assert_allclose(result, 0.0, atol=1e-4)


class TestAIMetrics:
    """Tests for AIMetrics observability plumbing."""

    def test_metrics_instantiate(self):
        """AIMetrics should instantiate without error."""
        from shared.ai_metrics import AIMetrics

        metrics = AIMetrics(service_name="test-engine")
        assert metrics.service_name == "test-engine"

    def test_record_inference(self):
        """record_inference should not raise."""
        from shared.ai_metrics import AIMetrics

        metrics = AIMetrics(service_name="test-engine")
        # Should not raise (OTel may be a no-op in test context)
        metrics.record_inference(
            duration_seconds=0.5,
            fiber_id="carros",
            section="default",
            num_detections=3,
        )

    def test_record_vehicle(self):
        """record_vehicle should not raise."""
        from shared.ai_metrics import AIMetrics

        metrics = AIMetrics(service_name="test-engine")
        metrics.record_vehicle(
            fiber_id="carros",
            section="default",
            direction=0,
            speed_kmh=65.0,
        )

    def test_record_glrt_peak(self):
        """record_glrt_peak should not raise."""
        from shared.ai_metrics import AIMetrics

        metrics = AIMetrics(service_name="test-engine")
        metrics.record_glrt_peak(
            fiber_id="carros",
            section="default",
            peak_value=5000.0,
        )

    def test_cache_metrics(self):
        """Cache hit/miss/eviction recording should not raise."""
        from shared.ai_metrics import AIMetrics

        metrics = AIMetrics(service_name="test-engine")
        metrics.record_cache_hit("dtan_unified")
        metrics.record_cache_miss("dtan_v2")
        metrics.record_cache_eviction("old_model")

    def test_calibration_status(self):
        """set_calibration_status should not raise."""
        from shared.ai_metrics import AIMetrics

        metrics = AIMetrics(service_name="test-engine")
        metrics.set_calibration_status("carros", enabled=True)
        metrics.set_calibration_status("mathis", enabled=False)
