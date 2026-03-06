"""
SHM Intelligence — baseline computation, frequency shift detection, trend analysis.

Structural Health Monitoring uses resonant frequency tracking to detect
damage. A healthy structure has stable natural frequencies. Damage causes
frequency drops. This module provides the analytical layer on top of the
spectral data pipeline.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SHMBaseline:
    """Reference frequency profile from a known-good period."""

    mean_freq: float
    std_freq: float
    sample_count: int


@dataclass
class FrequencyShift:
    """Result of comparing current readings to a baseline."""

    current_mean: float
    baseline_mean: float
    deviation_sigma: float
    direction: str  # 'increase', 'decrease', 'stable'
    is_anomalous: bool
    severity: str  # 'normal', 'warning', 'alert', 'critical'


@dataclass
class TrendAnalysis:
    """Result of linear trend fitting over a sliding window."""

    slope_hz_per_hour: float
    direction: str  # 'increasing', 'decreasing', 'stable'
    r_squared: float
    window_size: int


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

ANOMALY_SIGMA = 2.0  # sigma above which a shift is considered anomalous
WARNING_SIGMA = 2.0
ALERT_SIGMA = 3.0
CRITICAL_SIGMA = 4.0
MIN_BASELINE_SAMPLES = 10
TREND_STABILITY_THRESHOLD = 0.01  # Hz/hr — slopes smaller than this are "stable"


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------


def compute_baseline(
    peak_freqs: np.ndarray,
    robust: bool = False,
) -> Optional[SHMBaseline]:
    """
    Compute a baseline frequency profile from reference measurements.

    Args:
        peak_freqs: 1D array of peak frequency values.
        robust: If True, use median + MAD instead of mean + std.

    Returns:
        SHMBaseline or None if insufficient data.
    """
    if len(peak_freqs) < MIN_BASELINE_SAMPLES:
        return None

    if robust:
        # Median Absolute Deviation — robust to outliers
        median = float(np.median(peak_freqs))
        mad = float(np.median(np.abs(peak_freqs - median)))
        # MAD → std approximation for normal distribution
        std_approx = mad * 1.4826
        return SHMBaseline(
            mean_freq=median,
            std_freq=std_approx,
            sample_count=len(peak_freqs),
        )

    return SHMBaseline(
        mean_freq=float(np.mean(peak_freqs)),
        std_freq=float(np.std(peak_freqs, ddof=1)),
        sample_count=len(peak_freqs),
    )


# ---------------------------------------------------------------------------
# Frequency shift detection
# ---------------------------------------------------------------------------


def detect_frequency_shift(
    baseline: SHMBaseline,
    current_freqs: np.ndarray,
    sigma_threshold: float = ANOMALY_SIGMA,
) -> FrequencyShift:
    """
    Compare current frequency readings against a baseline.

    The deviation is measured in units of the baseline's standard deviation.
    """
    current_mean = float(np.mean(current_freqs))
    delta = current_mean - baseline.mean_freq

    if baseline.std_freq > 0:
        deviation_sigma = abs(delta) / baseline.std_freq
    else:
        deviation_sigma = 0.0 if abs(delta) < 1e-6 else float("inf")

    if abs(delta) < 1e-6:
        direction = "stable"
    elif delta > 0:
        direction = "increase"
    else:
        direction = "decrease"

    is_anomalous = deviation_sigma >= sigma_threshold
    severity = classify_deviation(deviation_sigma)

    return FrequencyShift(
        current_mean=current_mean,
        baseline_mean=baseline.mean_freq,
        deviation_sigma=deviation_sigma,
        direction=direction,
        is_anomalous=is_anomalous,
        severity=severity,
    )


# ---------------------------------------------------------------------------
# Severity classification
# ---------------------------------------------------------------------------


def classify_deviation(sigma: float) -> str:
    """
    Map deviation magnitude (in standard deviations) to a severity label.

    Thresholds:
    - < 2σ: normal
    - 2σ–3σ: warning
    - 3σ–4σ: alert
    - > 4σ: critical
    """
    if sigma < WARNING_SIGMA:
        return "normal"
    elif sigma < ALERT_SIGMA:
        return "warning"
    elif sigma < CRITICAL_SIGMA:
        return "alert"
    return "critical"


# ---------------------------------------------------------------------------
# Trend analysis
# ---------------------------------------------------------------------------


def analyze_trend(
    window: np.ndarray,
    sample_interval_seconds: float = 1.0,
) -> TrendAnalysis:
    """
    Fit a linear trend to a sliding window of frequency values.

    Returns slope in Hz/hour and a classification of the trend direction.
    """
    n = len(window)
    if n < 2:
        return TrendAnalysis(
            slope_hz_per_hour=0.0,
            direction="stable",
            r_squared=0.0,
            window_size=n,
        )

    x = np.arange(n, dtype=float) * sample_interval_seconds  # seconds
    y = window.astype(float)

    # Linear regression
    x_mean = np.mean(x)
    y_mean = np.mean(y)
    ss_xx = np.sum((x - x_mean) ** 2)
    ss_xy = np.sum((x - x_mean) * (y - y_mean))

    if ss_xx == 0:
        return TrendAnalysis(
            slope_hz_per_hour=0.0,
            direction="stable",
            r_squared=0.0,
            window_size=n,
        )

    slope = ss_xy / ss_xx  # Hz per second
    slope_hz_per_hour = float(slope * 3600)

    # R²
    y_pred = slope * (x - x_mean) + y_mean
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y_mean) ** 2)
    r_squared = float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0

    if abs(slope_hz_per_hour) < TREND_STABILITY_THRESHOLD:
        direction = "stable"
    elif slope_hz_per_hour > 0:
        direction = "increasing"
    else:
        direction = "decreasing"

    return TrendAnalysis(
        slope_hz_per_hour=slope_hz_per_hour,
        direction=direction,
        r_squared=r_squared,
        window_size=n,
    )
