"""NN-based vehicle counting with accumulation and lambda fallback.

Ports the notebook's CountVehicules class for production use.
Accumulates data across calls, fires when time_window_duration is reached,
then slides the window forward by `step` samples.

Supports two modes:
1) NN mode: uses a trained MLP model + feature normalization + sanity caps.
2) Lambda mode: no model; counts vehicles from GLRT peaks (fallback).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Tuple

import numpy as np
from scipy.signal import find_peaks

from .constants import COUNTING_STEP_SAMPLES
from .utils import correlation_threshold, find_ind

logger = logging.getLogger(__name__)

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None


class SimpleIntervalCounter:
    """Counts vehicles using NN inference on accumulated data windows.

    Accumulates aligned_speed, correlations, and aligned_data across calls.
    When accumulated time >= time_window_duration * fs, fires a counting
    window and trims the first `step` samples from buffers.

    Args:
        fiber_id: Fiber identifier for logging
        sampling_rate_hz: Sampling rate after decimation (Hz)
        correlation_threshold: Per-pair GLRT threshold (for speed filtering)
        channels_per_section: Number of channels per section (Nch)
        classify_threshold_factor: Not used directly; thresholds come from CSV
        min_peak_distance_s: Min headway for NN sanity cap (seconds)
        vehicle_counting_model: Pre-loaded PyTorch MLP model (or None for lambda mode)
        detection_thresholds: (N_sections, 2) array [detect_thr, classify_thr] per section
        mean_std_features: (2, 5) array [means row, stds row] for z-score normalization
        time_window_duration: Accumulation window in seconds (default 360 = 6 min)
        truck_ratio_for_split: Multiplier for truck classification threshold
        corr_threshold: Threshold on summed GLRT for counting intervals (default 500)
    """

    def __init__(
        self,
        fiber_id: str = "unknown",
        sampling_rate_hz: float = 10.4167,
        correlation_threshold: float = 1100.0,
        channels_per_section: int = 9,
        classify_threshold_factor: float = 50.0,
        min_peak_distance_s: float = 1.2,
        vehicle_counting_model=None,
        detection_thresholds=None,
        mean_std_features=None,
        time_window_duration: float = 360.0,
        truck_ratio_for_split: float = 2.0,
        corr_threshold: float = 500.0,
    ):
        self.fiber_id = fiber_id
        self.fs = sampling_rate_hz
        self.Nch = channels_per_section
        self.n_pairs = channels_per_section - 1

        # Counting-specific threshold on summed GLRT (distinct from per-pair speed threshold)
        self.corr_threshold = corr_threshold

        # Accumulation parameters
        self.time_window_duration = time_window_duration
        self.step = COUNTING_STEP_SAMPLES  # 250 samples
        self.features_duration = self.fs * self.time_window_duration

        # NN model (small MLP)
        self.NN_model = vehicle_counting_model

        # Per-section thresholds: (N_sections, 2) — [detect_thr, classify_thr]
        self.detection_thresholds = detection_thresholds

        # Feature normalization defaults (overridden from mean_std_features)
        self.mean_duration = 0.0
        self.mean_GLRT_sum = 0.0
        self.mean_speeds = 0.0
        self.mean_occupancy_rate = 0.0
        self.mean_energy = 0.0

        self.std_duration = 1.0
        self.std_GLRT_sum = 1.0
        self.std_speeds = 1.0
        self.std_occupancy_rate = 1.0
        self.std_energy = 1.0

        if mean_std_features is not None:
            if isinstance(mean_std_features, (str, Path)):
                loaded = np.genfromtxt(mean_std_features, delimiter=",")
            else:
                loaded = np.asarray(mean_std_features)
            (
                self.mean_duration,
                self.mean_GLRT_sum,
                self.mean_speeds,
                self.mean_occupancy_rate,
                self.mean_energy,
            ) = loaded[0]
            (
                self.std_duration,
                self.std_GLRT_sum,
                self.std_speeds,
                self.std_occupancy_rate,
                self.std_energy,
            ) = loaded[1]

        if detection_thresholds is not None:
            if isinstance(detection_thresholds, (str, Path)):
                self.detection_thresholds = np.genfromtxt(detection_thresholds, delimiter=",")
            else:
                self.detection_thresholds = np.asarray(detection_thresholds)

        # NN output safeguards
        self.enable_nn_sanity_cap = True
        self.min_headway_seconds = min_peak_distance_s  # 1.2s
        self.max_count_over_lambda_factor = 3.0
        self.max_count_over_lambda_bias = 2.0

        # Truck classification ratio (for set_section_thresholds fallback)
        self.truck_ratio_for_split = truck_ratio_for_split

        mode = "NN" if self.NN_model is not None else "lambda"
        logger.info(
            f"Counter initialized for '{fiber_id}' ({mode} mode): "
            f"corr_threshold={self.corr_threshold:.0f}, "
            f"time_window={time_window_duration}s, "
            f"step={self.step} samples"
        )

    # ------------------------------------------------------------------
    # Accumulation buffers (initialized lazily on first call)
    # ------------------------------------------------------------------

    def _has_buffers(self) -> bool:
        return hasattr(self, "acc_correlations")

    def _reset_buffers(self):
        if hasattr(self, "acc_correlations"):
            del self.acc_aligned_speed
            del self.acc_correlations
            del self.acc_aligned_data
        self.acc_start_timestamp_ns = None

    # ------------------------------------------------------------------
    # Public API: process_data_chunk (matches notebook)
    # ------------------------------------------------------------------

    def process_data_chunk(self, aligned_speed, correlations, aligned_data, timestamp_ns=None):
        """Accumulate data and yield counts when window is full.

        Args:
            aligned_speed: (sections, Nch-1, time) per-pair aligned speeds
            correlations: (sections, time) summed GLRT per section
            aligned_data: (sections, Nch, time) aligned sensor data
            timestamp_ns: timestamp (ns) of the first sample in this chunk

        Yields:
            (counts_per_section, intervals_per_section, window_start_timestamp_ns)
        """
        time_window_samples = int(self.time_window_duration * self.fs)

        if not self._has_buffers():
            self.acc_aligned_speed = aligned_speed
            self.acc_correlations = correlations
            self.acc_aligned_data = aligned_data
            self.acc_start_timestamp_ns = timestamp_ns
        else:
            self.acc_aligned_speed = np.concatenate(
                (self.acc_aligned_speed, aligned_speed), axis=2
            )
            self.acc_correlations = np.concatenate(
                (self.acc_correlations, correlations), axis=1
            )
            self.acc_aligned_data = np.concatenate(
                (self.acc_aligned_data, aligned_data), axis=2
            )

        if self.acc_correlations.shape[1] >= time_window_samples:
            speed_w = self.acc_aligned_speed[:, :, :time_window_samples]
            corr_w = self.acc_correlations[:, :time_window_samples]
            data_w = self.acc_aligned_data[:, :, :time_window_samples]

            counts, intervals = self.process_window_data(speed_w, corr_w, data_w)

            window_start_ts = self.acc_start_timestamp_ns

            # Slide window forward
            self.acc_aligned_speed = self.acc_aligned_speed[:, :, self.step :]
            self.acc_correlations = self.acc_correlations[:, self.step :]
            self.acc_aligned_data = self.acc_aligned_data[:, :, self.step :]

            # Update start timestamp for next window
            if self.acc_start_timestamp_ns is not None:
                sample_duration_ns = int(1e9 / self.fs)
                self.acc_start_timestamp_ns += self.step * sample_duration_ns

            yield counts, intervals, window_start_ts

    # ------------------------------------------------------------------
    # Legacy API (kept for backwards compatibility with existing callers)
    # ------------------------------------------------------------------

    def count_from_intervals(
        self,
        filtered_speed: np.ndarray,
        glrt_summed: np.ndarray,
        intervals_list: List[Tuple[List[int], List[int]]],
        timestamps_ns: List[int],
    ) -> Tuple[List, List, List]:
        """Legacy peak-based counting (fallback when not using accumulation).

        This method provides backwards compatibility for callers that
        haven't been updated to use process_data_chunk yet.
        """
        counts = []
        for section_idx, (starts, ends) in enumerate(intervals_list):
            section_counts = []
            for start, end in zip(starts, ends):
                glrt_segment = glrt_summed[section_idx, start:end]
                n_vehicles, n_cars, n_trucks = self._count_peaks_in_segment(
                    glrt_segment,
                    self.corr_threshold * self.n_pairs,
                    self.fs,
                )
                section_counts.append((n_vehicles, n_cars, n_trucks))
            counts.append(section_counts)
        return counts, intervals_list, timestamps_ns

    def _count_peaks_in_segment(
        self, glrt_segment: np.ndarray, threshold: float, fs: float
    ) -> Tuple[int, int, int]:
        if len(glrt_segment) == 0:
            return 0, 0, 0
        min_peak_distance = max(1, int(0.25 * fs))
        min_prominence = max(1.0, 0.1 * threshold)
        classify_threshold = threshold * 2.0
        peaks, props = find_peaks(
            glrt_segment, height=threshold, distance=min_peak_distance, prominence=min_prominence
        )
        if len(peaks) == 0:
            if len(glrt_segment) > 0 and np.nanmax(glrt_segment) >= threshold:
                if np.nanmax(glrt_segment) >= classify_threshold:
                    return 1, 0, 1
                return 1, 1, 0
            return 0, 0, 0
        n_vehicles = len(peaks)
        peak_heights = props.get("peak_heights", np.array([]))
        n_trucks = int(np.sum(peak_heights >= classify_threshold))
        n_cars = n_vehicles - n_trucks
        return n_vehicles, n_cars, n_trucks

    # ------------------------------------------------------------------
    # Core: process_window_data (matches notebook)
    # ------------------------------------------------------------------

    def process_window_data(self, aligned_speed_window, correlations_window, aligned_data_window):
        """Process a full accumulation window.

        Args:
            aligned_speed_window: (sections, Nch-1, time_window_samples)
            correlations_window: (sections, time_window_samples) — summed GLRT
            aligned_data_window: (sections, Nch, time_window_samples)

        Returns:
            (counts, intervals) where counts[i] is an array of per-interval vehicle counts
        """
        binary_mask = correlation_threshold(
            correlations_window, corr_threshold=self.corr_threshold
        )
        intervals = find_ind(binary_mask)

        n_sections = correlations_window.shape[0]
        if self.detection_thresholds is None or self.detection_thresholds.shape[0] != n_sections:
            # Thresholds not loaded or shape mismatch — create uniform thresholds
            self.set_section_thresholds(
                n_sections,
                detect_threshold=self.corr_threshold,
                classify_threshold=self.corr_threshold * self.truck_ratio_for_split,
            )

        count = []
        for section_idx, (thresh, inter, speed, data, corr) in enumerate(
            zip(
                self.detection_thresholds,
                intervals,
                aligned_speed_window,
                aligned_data_window,
                correlations_window,
            )
        ):
            section_count = self.apply_model(
                thresh,
                np.asarray(inter),
                speed,
                data,
                corr,
                section_idx=section_idx,
            )
            count.append(section_count)

        return count, intervals

    def set_section_thresholds(self, n_sections, detect_threshold, classify_threshold=None):
        """Set per-section detection/classification thresholds."""
        classify = classify_threshold if classify_threshold is not None else detect_threshold
        self.detection_thresholds = np.tile(
            np.array([[detect_threshold, classify]], dtype=float), (n_sections, 1)
        )

    # ------------------------------------------------------------------
    # apply_model: NN inference with lambda fallback (matches notebook)
    # ------------------------------------------------------------------

    def apply_model(self, threshold, intervals, speed_section, data_section, corr_section, section_idx=None):
        """Apply NN model (or lambda fallback) to count vehicles in intervals.

        Args:
            threshold: (2,) array [detect_thr, classify_thr] for this section
            intervals: (2, n_interv) array of [start_indices, end_indices]
            speed_section: (Nch-1, time) per-pair aligned speeds
            data_section: (Nch, time) aligned sensor data
            corr_section: (time,) summed GLRT for this section

        Returns:
            (n_interv,) array of vehicle counts per interval
        """
        if intervals.size == 0:
            return np.array([])

        n_interv = intervals.shape[1]
        energy_interval = np.empty(n_interv)
        GLRT_sum_interval = np.empty(n_interv)
        all_speed = np.empty(n_interv)

        time_duration = intervals[1] - intervals[0]

        for j in range(n_interv):
            start, stop = int(intervals[0, j]), int(intervals[1, j])
            energy_interval[j] = np.sum(data_section[:, start:stop] ** 2)
            GLRT_sum_interval[j] = np.sum(corr_section[start:stop] - threshold[0])
            speed_ = np.nanmedian(speed_section[:, start:stop])
            all_speed[j] = np.nan_to_num(speed_)

        vehicles_speeds = all_speed / 3.6  # km/h -> m/s

        vehicles_occupancy_rate = np.sum(time_duration)
        vehicles_occupancy_rate /= self.features_duration
        vehicles_occupancy_rate *= np.ones(len(time_duration))

        # Lambda fallback if no NN model
        if self.NN_model is None:
            section_count, _, _ = self._lambda_peak_count(threshold, intervals, corr_section)
            return section_count

        # Z-score normalization
        dataset_all_data = np.array([
            (time_duration - self.mean_duration) / self.std_duration,
            (GLRT_sum_interval - self.mean_GLRT_sum) / self.std_GLRT_sum,
            (vehicles_speeds - self.mean_speeds) / self.std_speeds,
            (vehicles_occupancy_rate - self.mean_occupancy_rate) / self.std_occupancy_rate,
            (energy_interval - self.mean_energy) / self.std_energy,
        ])  # (5, n_interv)

        # NN inference
        with torch.no_grad():
            section_count = self.NN_model(
                torch.tensor(dataset_all_data.T, dtype=torch.float32)
            ).numpy().flatten()

        if section_count is not None and section_count.size > 0 and any(section_count):
            section_count = np.nan_to_num(section_count, nan=0.0, posinf=0.0, neginf=0.0)
            section_count = np.maximum(section_count, 0.0)

            if self.enable_nn_sanity_cap:
                # Duration cap: max vehicles = ceil(duration / min_headway_in_samples)
                min_headway_samples = max(1.0, float(self.min_headway_seconds * self.fs))
                duration_cap = np.maximum(1.0, np.ceil(time_duration / min_headway_samples))

                # Lambda cap: NN count <= factor * lambda_count + bias
                lambda_peak_count, _, _ = self._lambda_peak_count(threshold, intervals, corr_section)
                lambda_cap = (
                    self.max_count_over_lambda_factor * lambda_peak_count
                    + self.max_count_over_lambda_bias
                )
                lambda_cap = np.maximum(1.0, lambda_cap)

                # Apply conservative upper bound
                section_count = np.minimum(section_count, np.minimum(duration_cap, lambda_cap))

            # Zero-speed zeroing
            section_count[vehicles_speeds == 0] = 0

        return section_count

    # ------------------------------------------------------------------
    # _lambda_peak_count: peak-based counting (matches notebook exactly)
    # ------------------------------------------------------------------

    def _lambda_peak_count(self, threshold, intervals, corr_section):
        """Count vehicles using peak detection in GLRT signal.

        Uses 0.25s min peak distance (hardcoded to match notebook).

        Args:
            threshold: (2,) array [detect_thr, classify_thr]
            intervals: (2, n_interv) array of [starts, ends]
            corr_section: (time,) summed GLRT

        Returns:
            (section_count, cars_count, trucks_count) each (n_interv,)
        """
        n_interv = intervals.shape[1]
        section_count = np.zeros(n_interv, dtype=float)
        cars_count = np.zeros(n_interv, dtype=float)
        trucks_count = np.zeros(n_interv, dtype=float)

        detect_thr = float(threshold[0]) if np.ndim(threshold) > 0 else float(threshold)
        classify_thr = (
            float(threshold[1])
            if np.ndim(threshold) > 0 and len(threshold) > 1
            else 2.0 * detect_thr
        )

        min_peak_distance = max(1, int(0.25 * self.fs))  # 0.25s hardcoded (matches notebook)
        min_prominence = max(1.0, 0.1 * detect_thr)

        for j in range(n_interv):
            start, stop = int(intervals[0, j]), int(intervals[1, j])
            seg = corr_section[start:stop]
            if seg.size == 0:
                section_count[j] = 0
                continue

            peaks, props = find_peaks(
                seg, height=detect_thr, distance=min_peak_distance, prominence=min_prominence
            )

            if len(peaks) == 0 and np.nanmax(seg) >= detect_thr:
                section_count[j] = 1
                if np.nanmax(seg) >= classify_thr:
                    trucks_count[j] = 1
                else:
                    cars_count[j] = 1
            else:
                section_count[j] = float(len(peaks))
                if len(peaks) > 0:
                    peak_heights = props.get("peak_heights", np.array([]))
                    trucks_count[j] = float(np.sum(peak_heights >= classify_thr))
                    cars_count[j] = float(len(peaks) - trucks_count[j])

        return section_count, cars_count, trucks_count
