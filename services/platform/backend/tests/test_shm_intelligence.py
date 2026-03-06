"""
TDD tests for SHM intelligence — baselines, thresholds, trend detection.

The SHM intelligence module should:
1. Compute a baseline frequency profile from a reference window
2. Detect when current frequencies deviate beyond a threshold
3. Classify deviations by severity (warning, alert, critical)
4. Track trends over sliding windows for gradual drift detection
5. Return structured analysis results for the frontend
"""

import numpy as np

from apps.monitoring.shm_intelligence import (
    FrequencyShift,
    SHMBaseline,
    TrendAnalysis,
    analyze_trend,
    classify_deviation,
    compute_baseline,
    detect_frequency_shift,
)


class TestComputeBaseline:
    """Baseline is mean ± std of peak frequencies over a reference window."""

    def test_baseline_from_stable_frequencies(self):
        # 100 samples all near 4.5 Hz
        peak_freqs = np.random.normal(4.5, 0.05, 100)
        baseline = compute_baseline(peak_freqs)
        assert isinstance(baseline, SHMBaseline)
        assert abs(baseline.mean_freq - 4.5) < 0.1
        assert baseline.std_freq < 0.15
        assert baseline.sample_count == 100

    def test_baseline_from_noisy_data(self):
        peak_freqs = np.random.normal(3.2, 0.5, 200)
        baseline = compute_baseline(peak_freqs)
        assert abs(baseline.mean_freq - 3.2) < 0.2
        assert baseline.std_freq > 0.2

    def test_baseline_rejects_insufficient_data(self):
        # Need at least 10 samples
        peak_freqs = np.array([4.5, 4.6])
        baseline = compute_baseline(peak_freqs)
        assert baseline is None

    def test_baseline_ignores_outliers(self):
        """Median-based baseline should be robust to outliers."""
        peak_freqs = np.concatenate(
            [
                np.full(95, 4.5),
                np.full(5, 100.0),  # outliers
            ]
        )
        baseline = compute_baseline(peak_freqs, robust=True)
        assert abs(baseline.mean_freq - 4.5) < 0.5


class TestDetectFrequencyShift:
    """Detect when current readings deviate from baseline."""

    def test_no_shift_within_tolerance(self):
        baseline = SHMBaseline(mean_freq=4.5, std_freq=0.1, sample_count=100)
        current_freqs = np.random.normal(4.5, 0.08, 20)
        shift = detect_frequency_shift(baseline, current_freqs)
        assert isinstance(shift, FrequencyShift)
        assert shift.deviation_sigma < 2.0
        assert not shift.is_anomalous

    def test_significant_shift_detected(self):
        baseline = SHMBaseline(mean_freq=4.5, std_freq=0.1, sample_count=100)
        # Current readings shifted down by 0.5 Hz = 5 sigma
        current_freqs = np.full(20, 4.0)
        shift = detect_frequency_shift(baseline, current_freqs)
        assert shift.deviation_sigma > 3.0
        assert shift.is_anomalous
        assert shift.direction == "decrease"

    def test_upward_shift(self):
        baseline = SHMBaseline(mean_freq=4.5, std_freq=0.1, sample_count=100)
        current_freqs = np.full(20, 5.2)
        shift = detect_frequency_shift(baseline, current_freqs)
        assert shift.direction == "increase"
        assert shift.is_anomalous


class TestClassifyDeviation:
    """Map deviation magnitude to severity levels."""

    def test_normal_range(self):
        assert classify_deviation(1.5) == "normal"

    def test_warning_range(self):
        assert classify_deviation(2.5) == "warning"

    def test_alert_range(self):
        assert classify_deviation(3.5) == "alert"

    def test_critical_range(self):
        assert classify_deviation(5.0) == "critical"


class TestAnalyzeTrend:
    """Sliding window trend detection for gradual drift."""

    def test_stable_trend(self):
        # Flat line — no drift
        window = np.full(50, 4.5)
        trend = analyze_trend(window)
        assert isinstance(trend, TrendAnalysis)
        assert abs(trend.slope_hz_per_hour) < 0.01
        assert trend.direction == "stable"

    def test_downward_drift(self):
        # Linear decrease from 4.5 to 4.0 over 50 samples
        window = np.linspace(4.5, 4.0, 50)
        trend = analyze_trend(window, sample_interval_seconds=60)
        assert trend.slope_hz_per_hour < -0.1
        assert trend.direction == "decreasing"

    def test_upward_drift(self):
        window = np.linspace(4.0, 4.5, 50)
        trend = analyze_trend(window, sample_interval_seconds=60)
        assert trend.slope_hz_per_hour > 0.1
        assert trend.direction == "increasing"

    def test_insufficient_data_returns_stable(self):
        window = np.array([4.5])
        trend = analyze_trend(window)
        assert trend.direction == "stable"
