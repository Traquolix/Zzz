"""GLRT-based vehicle detection: correlation computation and peak extraction.

Handles:
- apply_glrt: F.conv1d sliding window GLRT
- extract_detections: thresholding + peak counting + car/truck classification
"""

from __future__ import annotations

import numpy as np

try:
    import torch
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

from .constants import GLRT_EDGE_SAFETY_SAMPLES
from .utils import correlation_threshold, count_peaks_in_segment, find_ind


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
    ) -> list[dict]:
        """Extract vehicle detections from a single direction's output.

        Args:
            glrt_summed: (sections, trimmed_time) summed GLRT
            aligned_speed_pairs: (sections, Nch-1, trimmed_time) per-pair speeds
            direction: 0 for forward, 1 for reverse
            timestamps_ns: nanosecond timestamps for trimmed window, or None
            min_vehicle_duration_s: minimum detection duration in seconds
            classify_threshold_factor: peaks above detect_thr * this factor are trucks

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
        for section_idx, (starts, ends) in enumerate(intervals_per_section):
            for v_start, v_end in zip(starts, ends):
                if v_end - v_start < min_vehicle_samples:
                    continue

                interval_speeds = []
                for ch_pair in range(aligned_speed_pairs.shape[1]):
                    spd = aligned_speed_pairs[section_idx, ch_pair, v_start:v_end]
                    valid = spd[~np.isnan(spd) & (spd > 0)]
                    if len(valid) > 0:
                        interval_speeds.append(float(np.median(valid)))
                if not interval_speeds:
                    continue

                vehicle_speed = float(np.median(interval_speeds))
                if vehicle_speed < self.min_speed or vehicle_speed > self.max_speed:
                    continue

                t_mid = (v_start + v_end) // 2
                if timestamps_ns is not None and t_mid < len(timestamps_ns):
                    ts_ns = int(timestamps_ns[t_mid])
                else:
                    ts_ns = None

                seg = glrt_summed[section_idx, v_start:v_end]
                n_vehicles, n_cars, n_trucks = count_peaks_in_segment(
                    seg, detect_thr, classify_thr, self.fs,
                )
                n_vehicles = float(max(1, n_vehicles))
                n_cars = float(n_cars)
                n_trucks = float(n_trucks)

                detections.append({
                    "section_idx": section_idx,
                    "speed_kmh": vehicle_speed,
                    "direction": direction,
                    "timestamp_ns": ts_ns,
                    "glrt_max": float(np.max(seg)),
                    "vehicle_count": n_vehicles,
                    "n_cars": n_cars,
                    "n_trucks": n_trucks,
                    "_t_mid_sample": t_mid,
                })

        return detections
