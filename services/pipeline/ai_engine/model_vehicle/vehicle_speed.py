"""Vehicle speed estimation orchestrator.

Thin orchestrator that delegates to:
- DTANInference: model forward pass, alignment, speed computation
- GLRTDetector: GLRT correlation detection, peak extraction
- SpeedFilter: speed post-processing, outlier rejection
"""

from __future__ import annotations

import logging
import time
from typing import NamedTuple, Optional

import numpy as np

from .calibration import CalibrationData
from .constants import GLRT_DEFAULT_WINDOW, GLRT_EDGE_SAFETY_SAMPLES
from .dtan_inference import DTANInference
from .glrt_detector import GLRTDetector
from .speed_filter import SpeedFilter
from .utils import correlation_threshold, find_ind, normalize_channel_energy

logger = logging.getLogger(__name__)


class DirectionResult(NamedTuple):
    """Result from processing one direction through the DTAN pipeline.

    Yielded by process_file for each direction (forward, and optionally reverse).
    All arrays are edge-trimmed.
    """

    filtered_speed: np.ndarray       # (sections, 1, trimmed_time) median speed per section
    glrt_summed: np.ndarray          # (sections, trimmed_time) summed GLRT
    aligned_data: np.ndarray         # (sections, Nch, trimmed_time) aligned sensor data
    timestamps: np.ndarray           # (trimmed_time,) datetime timestamps
    timestamps_ns: Optional[np.ndarray]  # (trimmed_time,) nanosecond timestamps, or None
    direction_mask: np.ndarray       # (sections, trimmed_time) direction value (1=fwd, 2=rev)
    aligned_speed_per_pair: np.ndarray  # (sections, Nch-1, trimmed_time) per-pair speeds
    intervals: list = []             # Per-section [(starts, ends), ...] for counting


def compute_edge_trim(glrt_window: int = GLRT_DEFAULT_WINDOW, safety: int = GLRT_EDGE_SAFETY_SAMPLES) -> int:
    """Compute edge trim size based on GLRT parameters."""
    return safety


class VehicleSpeedEstimator:
    """Processes sensor data to estimate vehicle speeds using DTAN alignment.

    Orchestrates DTANInference, GLRTDetector, and SpeedFilter to implement
    the full pipeline from raw sensor data to vehicle detections.

    Args:
        model_args: Configuration from Args_NN_model_all_channels
        ovr_time: Overlap ratio between consecutive time windows
        glrt_win: Window size for GLRT calculation
        min_speed: Minimum realistic vehicle speed (km/h)
        max_speed: Maximum realistic vehicle speed (km/h)
        corr_threshold: Per-pair correlation threshold
        verbose: Enable verbose logging
        calibration_data: Optional CalibrationData for variable threshold + coupling
        bidirectional_detection: Enable bidirectional (forward + reverse) detection
    """

    def __init__(
        self,
        model_args,
        ovr_time: float,
        glrt_win: int,
        min_speed: float = 20,
        max_speed: float = 120,
        corr_threshold: float = 500,
        verbose: bool = False,
        calibration_data: CalibrationData | None = None,
        visualization_config: dict | None = None,
        bidirectional_detection: bool = True,
        speed_glrt_factor: float = 1.0,
        speed_weighting: str = "median",
        speed_positive_glrt_only: bool = False,
    ):
        if model_args is None:
            raise ValueError("model_args is required to initialize VehicleSpeedEstimator")

        self.verbose = verbose
        self.window_size = model_args.signal_length
        self.Nch = model_args.Nch
        self.fs = model_args.fs
        self.glrt_win = glrt_win
        self.edge_trim = compute_edge_trim(glrt_win, GLRT_EDGE_SAFETY_SAMPLES)
        self.model_args = model_args

        self.corr_threshold = corr_threshold
        self.calibration_data = calibration_data
        self.bidirectional_detection = bidirectional_detection
        self.min_speed = min_speed
        self.max_speed = max_speed

        # Initialize DTAN inference
        T, model = model_args.get_model_Theta()
        device = model_args.device_name
        model = model.to(device)
        model.eval()

        import torch
        uniform_grid = T.uniform_meshgrid(
            (model_args.input_shape, 1)
        ).detach().to("cpu").numpy()

        self._dtan = DTANInference(model_args, T, model, uniform_grid)

        # Initialize GLRT detector
        self._glrt = GLRTDetector(
            glrt_win=glrt_win,
            Nch=model_args.Nch,
            fs=model_args.fs,
            corr_threshold=corr_threshold,
            min_speed=min_speed,
            max_speed=max_speed,
        )

        # Initialize speed filter
        self._speed_filter = SpeedFilter(min_speed=min_speed, max_speed=max_speed)

        # Initialize visualizer if enabled
        self.visualizer = None
        self.last_visualization_time = 0
        self.visualization_interval = 0
        self.count_data_for_viz = None

        if visualization_config and visualization_config.get("enabled", False):
            from .visualization import VehicleVisualizer

            self.visualizer = VehicleVisualizer(
                output_dir=visualization_config.get("output_dir", "/app/visualizations"),
                fiber_id=visualization_config.get("fiber_id", "unknown"),
                static_threshold=self.corr_threshold,
            )
            self.visualization_interval = visualization_config.get("interval_seconds", 300)
            logger.info(f"Visualization enabled: interval={self.visualization_interval}s")

    def set_section(self, section: str):
        """Update the section name for visualization output."""
        if self.visualizer is not None:
            self.visualizer.section = section

    def set_count_data(self, count_data: tuple | None):
        """Store count data for visualization overlay."""
        self.count_data_for_viz = count_data

    # --- Delegate to sub-components (public API preserved) ---

    def split_channel_overlap(self, x: np.ndarray) -> np.ndarray:
        return self._dtan.split_channel_overlap(x)

    def comp_speed(self, grid_t: np.ndarray) -> np.ndarray:
        return self._dtan.comp_speed(grid_t)

    def predict_theta(self, data_window: np.ndarray) -> tuple:
        return self._dtan.predict_theta(data_window)

    def align_window(self, space_split, thetas_in, Nch, align_channel_idx):
        return self._dtan.align_window(space_split, thetas_in, Nch, align_channel_idx)

    def apply_glrt(self, aligned, safety=GLRT_EDGE_SAFETY_SAMPLES):
        return self._glrt.apply_glrt(aligned, safety)

    def filtering_speed(self, speed, binary_filter):
        return self._speed_filter.filtering_speed(speed, binary_filter)

    def filtering_speed_per_channel(self, speed, binary_filter, intervals):
        return self._speed_filter.filtering_speed_per_channel(speed, binary_filter, intervals)

    def extract_detections(self, glrt_summed, aligned_speed_pairs, direction,
                           timestamps_ns, min_vehicle_duration_s=0.3,
                           classify_threshold_factor=2.0):
        return self._glrt.extract_detections(
            glrt_summed, aligned_speed_pairs, direction, timestamps_ns,
            min_vehicle_duration_s, classify_threshold_factor,
        )

    # --- Core pipeline ---

    def _process_single_direction(self, data_window: np.ndarray):
        """Process data in one direction through DTAN pipeline."""
        align_channel_idx = (self.Nch - 1) // 2

        space_split = self._dtan.split_channel_overlap(data_window)

        for i in range(space_split.shape[0]):
            space_split[i] = normalize_channel_energy(space_split[i])

        thetas, grid_t = self._dtan.predict_theta(space_split)
        aligned = self._dtan.align_window(space_split, thetas, self.Nch, align_channel_idx)

        all_speed = self._dtan.comp_speed(grid_t)
        aligned_speed = self._dtan.align_window(
            all_speed, thetas[:, :-1, :], self.Nch - 1, align_channel_idx
        ).detach().cpu().numpy()

        glrt_per_pair = self._glrt.apply_glrt(aligned).detach().cpu().numpy()

        binary_filter = correlation_threshold(glrt_per_pair, corr_threshold=self.corr_threshold)
        filtered_speed, _ = self._speed_filter.filtering_speed(aligned_speed, binary_filter)

        glrt_summed = np.sum(glrt_per_pair, axis=1)

        return glrt_per_pair, glrt_summed, filtered_speed, aligned, thetas

    def _trim_and_yield(self, glrt_summed, filtered_speed, aligned, date_window,
                        date_window_ns, direction_value):
        """Trim edges and yield a single direction's results."""
        trim_start = self.edge_trim
        trim_end = self.window_size - self.edge_trim

        agg_speed = np.nanmedian(filtered_speed[:, :, trim_start:trim_end], axis=1)
        trimmed_filtered = agg_speed[:, np.newaxis, :]

        trimmed_glrt = glrt_summed[:, trim_start:trim_end]
        aligned_np = aligned.detach().cpu().numpy() if hasattr(aligned, 'detach') else aligned
        trimmed_aligned = aligned_np[..., trim_start:trim_end]
        trimmed_date = date_window[trim_start:trim_end]
        trimmed_date_ns = date_window_ns[trim_start:trim_end] if date_window_ns is not None else None

        n_sections = glrt_summed.shape[0]
        trimmed_time = trim_end - trim_start
        direction_mask = np.full((n_sections, trimmed_time), direction_value, dtype=int)

        trimmed_aligned_speed = filtered_speed[..., trim_start:trim_end]

        summed_threshold = self.corr_threshold * (self.Nch - 1)
        detection_mask = (glrt_summed >= summed_threshold).astype(float)
        intervals_full = find_ind(detection_mask)

        trimmed_intervals = []
        for starts, ends in intervals_full:
            shifted_starts = [s - trim_start for s in starts if s >= trim_start and s < trim_end]
            shifted_ends = [min(e - trim_start, trim_end - trim_start) for s, e in zip(starts, ends) if s >= trim_start and s < trim_end]
            trimmed_intervals.append((shifted_starts, shifted_ends))

        yield DirectionResult(
            filtered_speed=trimmed_filtered,
            glrt_summed=trimmed_glrt,
            aligned_data=trimmed_aligned,
            timestamps=trimmed_date,
            timestamps_ns=trimmed_date_ns,
            direction_mask=direction_mask,
            aligned_speed_per_pair=trimmed_aligned_speed,
            intervals=trimmed_intervals,
        )

    def process_file(self, x: np.ndarray, d: np.ndarray, d_ns: np.ndarray | None = None):
        """Processes a single window of sensor data through the DTAN pipeline.

        Args:
            x: Sensor data (channels, time_samples) - exactly window_size samples
            d: Timestamps for each time sample
            d_ns: Timestamps in nanoseconds (optional, for output messages)

        Yields:
            DirectionResult named tuple with trimmed arrays.
        """
        _, L = x.shape

        if L < self.window_size:
            logger.warning(f"Received {L} samples, need {self.window_size}. Skipping.")
            return

        if L > self.window_size:
            logger.warning(
                f"Received {L} samples, expected {self.window_size}. "
                f"Processing first window only."
            )

        data_window = x[:, :self.window_size]
        date_window = d[:self.window_size]
        date_window_ns = d_ns[:self.window_size] if d_ns is not None else None

        # --- Forward pass ---
        fwd_per_pair, fwd_summed, fwd_filtered, fwd_aligned, fwd_thetas = (
            self._process_single_direction(data_window)
        )

        if self.calibration_data is not None:
            fwd_summed = self.calibration_data.apply_coupling_correction(fwd_summed)

        yield from self._trim_and_yield(
            fwd_summed, fwd_filtered, fwd_aligned,
            date_window, date_window_ns, direction_value=1,
        )

        # --- Reverse pass (if bidirectional) ---
        if self.bidirectional_detection:
            data_flipped = data_window[::-1, :].copy()
            rev_per_pair, rev_summed, rev_filtered, rev_aligned, rev_thetas = (
                self._process_single_direction(data_flipped)
            )
            rev_summed = rev_summed[::-1, :].copy()
            rev_filtered = rev_filtered[::-1, :, :].copy()

            yield from self._trim_and_yield(
                rev_summed, rev_filtered, rev_aligned,
                date_window, date_window_ns, direction_value=2,
            )
