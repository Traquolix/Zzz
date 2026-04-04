"""GLRT-based vehicle detection: correlation computation and peak extraction.

Handles:
- apply_glrt: F.conv1d sliding window GLRT
- extract_detections: thresholding + peak counting + car/truck classification
"""

from __future__ import annotations

import logging

import numpy as np

try:
    import torch
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    import numba
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False

from .constants import GLRT_EDGE_SAFETY_SAMPLES
from .utils import correlation_threshold, count_peaks_in_segment, find_ind

_logger = logging.getLogger(__name__)


def _build_speed_kernel():
    """Build numba-JIT kernel for per-detection speed computation.

    Returns a pure-Python fallback if numba is not available.
    """

    def _speed_for_detection_py(sec_speeds, v_start, v_end):
        """Pure-Python: per-pair median over interval, median across pairs."""
        n_pairs = sec_speeds.shape[0]
        pair_medians = []
        for ch in range(n_pairs):
            spd = sec_speeds[ch, v_start:v_end]
            valid = spd[~np.isnan(spd) & (spd > 0)]
            if len(valid) > 0:
                pair_medians.append(float(np.median(valid)))
        if not pair_medians:
            return np.nan
        return float(np.median(pair_medians))

    if not NUMBA_AVAILABLE:
        return _speed_for_detection_py

    @numba.njit(cache=True)
    def _speed_for_detection_nb(sec_speeds, v_start, v_end):
        """Numba-JIT: per-pair median over interval, median across pairs."""
        n_pairs = sec_speeds.shape[0]
        pair_medians = np.empty(n_pairs, dtype=np.float64)
        n_valid_pairs = 0

        for ch in range(n_pairs):
            # Collect valid (non-NaN, positive) speeds for this pair
            count = 0
            for t in range(v_start, v_end):
                v = sec_speeds[ch, t]
                if v == v and v > 0:  # NaN check: v != v when NaN
                    count += 1

            if count == 0:
                continue

            valid = np.empty(count, dtype=np.float64)
            idx = 0
            for t in range(v_start, v_end):
                v = sec_speeds[ch, t]
                if v == v and v > 0:
                    valid[idx] = v
                    idx += 1

            pair_medians[n_valid_pairs] = np.median(valid)
            n_valid_pairs += 1

        if n_valid_pairs == 0:
            return np.nan
        return np.median(pair_medians[:n_valid_pairs])

    return _speed_for_detection_nb


# Module-level singleton — JIT compiles on first call, cached thereafter
_speed_for_detection = _build_speed_kernel()


class GLRTDetector:
    """GLRT computation and vehicle detection extraction."""

    def __init__(
        self,
        glrt_win: int,
        Nch: int,
        fs: float,
        corr_threshold: float,
        min_speed: float,
        max_speed: float,
    ):
        self.glrt_win = glrt_win
        self.Nch = Nch
        self.fs = fs
        self.corr_threshold = corr_threshold
        self.min_speed = min_speed
        self.max_speed = max_speed

    def apply_glrt(self, aligned, safety: int = GLRT_EDGE_SAFETY_SAMPLES):
        """Applies GLRT using F.conv1d for vectorized sliding window sum.

        Args:
            aligned: 3D tensor of aligned sensor data (sections, Nch, time)
            safety: Samples to exclude at edges

        Returns:
            3D tensor of per-pair GLRT results (sections, Nch-1, time)
        """
        dim = aligned.shape
        l = self.glrt_win
        n_pairs = dim[1] - 1
        N = dim[0]
        T = dim[2]

        # Per-pair product: adjacent channel correlation
        values = aligned[:, :-1, :] * aligned[:, 1:, :]  # (N, n_pairs, T)

        # Vectorized sliding sum via F.conv1d (matches notebook Cell 28)
        values_flat = values.reshape(N * n_pairs, 1, T)  # (N*n_pairs, 1, T)
        kernel = torch.ones(1, 1, l, device=values.device)  # box kernel
        conv_out = F.conv1d(values_flat, kernel)  # (N*n_pairs, 1, T-l+1)
        conv_out = conv_out.squeeze(1).reshape(N, n_pairs, T - l + 1)

        # Place result with safety margins (matches notebook)
        out = torch.zeros((N, n_pairs, T), device=values.device)
        left = safety + l // 2
        right = T - safety - l // 2
        valid_len = right - left
        if valid_len > 0 and conv_out.shape[2] > 2 * safety:
            out[:, :, left:right] = conv_out[:, :, safety:safety + valid_len]

        return out

    def extract_detections(
        self,
        glrt_summed: np.ndarray,
        aligned_speed_pairs: np.ndarray,
        direction: int,
        timestamps_ns: np.ndarray | None,
        min_vehicle_duration_s: float = 0.3,
        classify_threshold_factor: float = 2.0,
        aligned_data: np.ndarray | None = None,
    ) -> list[dict]:
        """Extract vehicle detections from a single direction's output.

        Args:
            glrt_summed: (sections, trimmed_time) summed GLRT
            aligned_speed_pairs: (sections, Nch-1, trimmed_time) per-pair speeds
            direction: 0 for forward, 1 for reverse
            timestamps_ns: nanosecond timestamps for trimmed window, or None
            min_vehicle_duration_s: minimum detection duration in seconds
            classify_threshold_factor: GLRT multiplier for truck classification
            aligned_data: (sections, Nch, trimmed_time) aligned sensor data for
                strain extraction. If None, strain fields default to 0.

        Returns:
            List of detection dicts
        """
        summed_threshold = self.corr_threshold * (self.Nch - 1)
        min_vehicle_samples = max(3, int(min_vehicle_duration_s * self.fs))

        detect_thr = summed_threshold
        classify_thr = detect_thr * classify_threshold_factor

        binary_mask = correlation_threshold(glrt_summed, corr_threshold=summed_threshold)
        intervals_per_section = find_ind(binary_mask)

        detections = []
        speed_fn = _speed_for_detection

        for section_idx, (starts, ends) in enumerate(intervals_per_section):
            sec_speeds = aligned_speed_pairs[section_idx]  # (Nch-1, time)
            sec_glrt = glrt_summed[section_idx]
            sec_aligned = aligned_data[section_idx] if aligned_data is not None else None
            min_spd = self.min_speed
            max_spd = self.max_speed

            for v_start, v_end in zip(starts, ends):
                if v_end - v_start < min_vehicle_samples:
                    continue

                vehicle_speed = speed_fn(sec_speeds, v_start, v_end)
                if vehicle_speed != vehicle_speed:  # NaN
                    continue
                if vehicle_speed < min_spd or vehicle_speed > max_spd:
                    continue

                t_mid = (v_start + v_end) // 2
                ts_ns = (
                    int(timestamps_ns[t_mid])
                    if timestamps_ns is not None and t_mid < len(timestamps_ns)
                    else None
                )

                seg = sec_glrt[v_start:v_end]
                glrt_max = float(np.max(seg))
                n_vehicles, n_cars, n_trucks = count_peaks_in_segment(
                    seg, detect_thr, classify_thr, self.fs,
                )

                # Strain metrics from aligned sensor data
                strain_peak = 0.0
                strain_rms = 0.0
                if sec_aligned is not None:
                    interval_data = sec_aligned[:, v_start:v_end]
                    strain_peak = float(np.mean(np.max(np.abs(interval_data), axis=1)))
                    strain_rms = float(np.mean(np.sqrt(np.mean(interval_data ** 2, axis=1))))

                detections.append({
                    "section_idx": section_idx,
                    "speed_kmh": vehicle_speed,
                    "direction": direction,
                    "timestamp_ns": ts_ns,
                    "glrt_max": glrt_max,
                    "vehicle_count": float(max(1, n_vehicles)),
                    "n_cars": float(n_cars),
                    "n_trucks": float(n_trucks),
                    "strain_peak": strain_peak,
                    "strain_rms": strain_rms,
                    "_t_mid_sample": t_mid,
                })

        return detections
