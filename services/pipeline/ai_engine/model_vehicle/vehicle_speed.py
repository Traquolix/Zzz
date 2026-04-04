"""Vehicle speed estimation orchestrator.

Thin orchestrator that delegates to:
- DTANInference: model forward pass, alignment, speed computation
- GLRTDetector: GLRT correlation detection, peak extraction
- SpeedFilter: speed post-processing, outlier rejection
"""

from __future__ import annotations

import logging
import threading
from typing import NamedTuple

import numpy as np

from .calibration import CalibrationData
from .constants import GLRT_EDGE_SAFETY_SAMPLES
from .dtan_inference import DTANInference
from .glrt_detector import GLRTDetector
from .speed_filter import SpeedFilter
from .utils import correlation_threshold, normalize_channel_energy

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
    timestamps_ns: np.ndarray | None  # (trimmed_time,) nanosecond timestamps, or None
    direction_mask: np.ndarray       # (sections, trimmed_time) direction value (0=fwd, 1=rev)
    aligned_speed_per_pair: np.ndarray  # (sections, Nch-1, trimmed_time) per-pair speeds


def compute_edge_trim(
    window_size: int,
    overlap_ratio: float,
    safety: int = GLRT_EDGE_SAFETY_SAMPLES,
) -> int:
    """Compute edge trim so consecutive windows tile without overlap or gaps.

    With overlap_ratio, step_size = window_size * (1 - overlap_ratio).
    Trimming (window_size - step_size) / 2 from each side means each window
    emits detections for exactly step_size samples — no duplicates.

    The trim is always at least ``safety`` samples to avoid GLRT edge artifacts.
    """
    step_size = int(window_size * (1 - overlap_ratio))
    overlap_trim = (window_size - step_size) // 2
    return max(overlap_trim, safety)


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
        alignment_method: str = "cpab",
        nstepsolver: int = 10,
    ):
        if model_args is None:
            raise ValueError("model_args is required to initialize VehicleSpeedEstimator")

        self.verbose = verbose
        self.window_size = model_args.signal_length
        self.Nch = model_args.Nch
        self.fs = model_args.fs
        self.glrt_win = glrt_win
        self.edge_trim = compute_edge_trim(model_args.signal_length, ovr_time)
        self.model_args = model_args

        self.corr_threshold = corr_threshold
        self.calibration_data = calibration_data
        self.bidirectional_detection = bidirectional_detection
        self.min_speed = min_speed
        self.max_speed = max_speed
        self.alignment_method = alignment_method

        # Initialize DTAN inference
        T, model = model_args.get_model_Theta()
        device = model_args.device_name
        model = model.to(device)
        model.eval()

        # CPAB ODE solver steps — configurable per model for sections that
        # need higher accuracy. Default 10 converges for 1D piecewise-affine
        # transforms (<0.05 km/h mean speed diff vs 50 steps on carros:202Bis).
        # Increase for difficult fiber sections where marginal detections are lost.
        T.set_solver_params(nstepsolver=nstepsolver)
        logger.info(f"CPAB solver: nstepsolver={nstepsolver}")

        # Compile the NN head (CNN+RNN+FC) for faster theta prediction.
        # The CPAB transform is not compiled — it uses custom autograd functions
        # that cause graph breaks. Only the pure NN forward pass is compiled.
        # Using "default" mode (TorchInductor kernel fusion) on all platforms.
        # "reduce-overhead" (CUDA graphs) causes transient errors at startup
        # when multiple fibers trigger concurrent graph captures on the same GPU.
        import torch
        if hasattr(torch, "compile"):
            try:
                model.predict_thetas = torch.compile(
                    model.predict_thetas, mode="default"
                )
                logger.info("DTAN predict_thetas compiled (mode=default)")
            except Exception as e:
                logger.warning(f"torch.compile failed (non-critical): {e}")

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
        self._inference_lock = threading.Lock()

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
                           classify_threshold_factor=2.0,
                           aligned_data: np.ndarray | None = None):
        return self._glrt.extract_detections(
            glrt_summed, aligned_speed_pairs, direction, timestamps_ns,
            min_vehicle_duration_s, classify_threshold_factor,
            aligned_data=aligned_data,
        )

    # --- Core pipeline ---

    def _process_single_direction(self, data_window: np.ndarray):
        """Process data in one direction through DTAN pipeline."""
        align_channel_idx = (self.Nch - 1) // 2

        space_split = self._dtan.split_channel_overlap(data_window)

        for i in range(space_split.shape[0]):
            space_split[i] = normalize_channel_energy(space_split[i])

        thetas, grid_t = self._dtan.predict_theta(space_split)
        all_speed = self._dtan.comp_speed(grid_t)

        if self.alignment_method == "shift":
            aligned = self._dtan.align_window_shift(
                space_split, grid_t, align_channel_idx
            )
            aligned_speed = all_speed
        else:
            aligned = self._dtan.align_window(
                space_split, thetas, self.Nch, align_channel_idx
            )
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

        yield DirectionResult(
            filtered_speed=trimmed_filtered,
            glrt_summed=trimmed_glrt,
            aligned_data=trimmed_aligned,
            timestamps=trimmed_date,
            timestamps_ns=trimmed_date_ns,
            direction_mask=direction_mask,
            aligned_speed_per_pair=trimmed_aligned_speed,
        )

    def process_batch(self, sections: list[tuple[np.ndarray, np.ndarray, np.ndarray | None]]):
        """Process multiple sections in a single batched GPU pass.

        Args:
            sections: List of (data, timestamps, timestamps_ns) tuples,
                      one per section. data shape: (channels, time_samples).

        Returns:
            List of lists of DirectionResult, one inner list per section.
        """
        with self._inference_lock:
            results, _ = self._process_batch_unlocked(sections)
            return results

    def _process_batch_unlocked(self, sections):
        """Returns (results, stage_times)."""
        prepared, valid_indices, fwd_combined, rev_combined, window_counts = (
            self._preprocess_batch(sections)
        )

        if fwd_combined is None:
            return [[] for _ in sections], {}

        return self._run_inference_and_postprocess(
            sections, prepared, valid_indices,
            fwd_combined, rev_combined, window_counts,
        )

    def _run_inference_and_postprocess(
        self, sections, prepared, valid_indices,
        fwd_combined, rev_combined, window_counts,
    ):
        """GPU inference + postprocessing. Caller holds GPU lock if needed.

        Returns:
            (batch_results, stage_times) where stage_times is from the last
            _batched_direction call (fwd or rev).
        """
        fwd_results, stage_times = self._batched_direction(fwd_combined, window_counts)
        rev_results_list = None
        if self.bidirectional_detection and rev_combined is not None:
            rev_results_list, rev_times = self._batched_direction(rev_combined, window_counts)
            # Sum both directions — operator cares about total GPU time per window
            for k, v in rev_times.items():
                stage_times[k] = stage_times.get(k, 0.0) + v

        results = self._postprocess_batch(
            sections, prepared, valid_indices, fwd_results, rev_results_list
        )
        return results, stage_times

    def _preprocess_batch(self, sections):
        """CPU-only preprocessing: validate, split, normalize.

        Returns:
            (prepared, valid_indices, fwd_combined, rev_combined, window_counts)
            where fwd_combined/rev_combined are ready for _batched_direction,
            or (prepared, valid_indices, None, None, []) if no valid sections.
        """
        prepared = []
        for x, d, d_ns in sections:
            _, L = x.shape
            if self.window_size > L:
                logger.warning(f"Batch: {L} samples < {self.window_size}. Skipping section.")
                prepared.append(None)
                continue
            data_window = x[:, :self.window_size]
            date_window = d[:self.window_size]
            date_window_ns = d_ns[:self.window_size] if d_ns is not None else None
            prepared.append((data_window, date_window, date_window_ns))

        valid_indices = []
        space_splits = []
        window_counts = []
        for i, p in enumerate(prepared):
            if p is None:
                continue
            data_window = p[0]
            ss = self._dtan.split_channel_overlap(data_window)
            for j in range(ss.shape[0]):
                ss[j] = normalize_channel_energy(ss[j])
            space_splits.append(ss)
            window_counts.append(ss.shape[0])
            valid_indices.append(i)

        if not space_splits:
            return prepared, valid_indices, None, None, []

        fwd_combined = np.concatenate(space_splits, axis=0)

        rev_combined = None
        if self.bidirectional_detection:
            rev_splits = []
            for idx in valid_indices:
                data_window = prepared[idx][0]
                data_flipped = data_window[::-1, :].copy()
                ss = self._dtan.split_channel_overlap(data_flipped)
                for j in range(ss.shape[0]):
                    ss[j] = normalize_channel_energy(ss[j])
                rev_splits.append(ss)
            rev_combined = np.concatenate(rev_splits, axis=0)

        return prepared, valid_indices, fwd_combined, rev_combined, window_counts

    def _postprocess_batch(self, sections, prepared, valid_indices,
                           fwd_results, rev_results_list):
        """CPU-only postprocessing: calibration, trimming, result assembly."""
        all_results = [[] for _ in sections]
        for list_idx, section_idx in enumerate(valid_indices):
            data_window, date_window, date_window_ns = prepared[section_idx]
            fwd_glrt_summed, fwd_filtered, fwd_aligned = fwd_results[list_idx]

            if self.calibration_data is not None:
                fwd_glrt_summed = self.calibration_data.apply_coupling_correction(fwd_glrt_summed)

            for dr in self._trim_and_yield(fwd_glrt_summed, fwd_filtered, fwd_aligned,
                                           date_window, date_window_ns, direction_value=0):
                all_results[section_idx].append(dr)

            if self.bidirectional_detection and rev_results_list is not None:
                rev_glrt_summed, rev_filtered, rev_aligned = rev_results_list[list_idx]
                rev_glrt_summed = rev_glrt_summed[::-1, :].copy()
                rev_filtered = rev_filtered[::-1, :, :].copy()
                for dr in self._trim_and_yield(rev_glrt_summed, rev_filtered, rev_aligned,
                                               date_window, date_window_ns, direction_value=1):
                    all_results[section_idx].append(dr)

        return all_results

    def _batched_direction(self, combined_space_split, window_counts):
        """Run DTAN + GLRT on concatenated space_split, return per-section results.

        Stores per-stage timing in self._last_stage_times for the caller
        to report to metrics.
        """
        import time as _time

        align_channel_idx = (self.Nch - 1) // 2

        t0 = _time.perf_counter()
        thetas, grid_t = self._dtan.predict_theta(combined_space_split)
        all_speed = self._dtan.comp_speed(grid_t)
        t_predict = _time.perf_counter() - t0

        t0 = _time.perf_counter()
        if self.alignment_method == "shift":
            aligned = self._dtan.align_window_shift(
                combined_space_split, grid_t, align_channel_idx
            )
            aligned_speed = all_speed
        else:
            aligned = self._dtan.align_window(
                combined_space_split, thetas, self.Nch, align_channel_idx
            )
            aligned_speed = self._dtan.align_window(
                all_speed, thetas[:, :-1, :], self.Nch - 1, align_channel_idx
            ).detach().cpu().numpy()
        t_align = _time.perf_counter() - t0

        t0 = _time.perf_counter()
        glrt_per_pair = self._glrt.apply_glrt(aligned).detach().cpu().numpy()
        t_glrt = _time.perf_counter() - t0

        stage_times = {
            "predict_theta": t_predict,
            "align": t_align,
            "glrt": t_glrt,
        }

        # Split back per section
        results = []
        offset = 0
        for count in window_counts:
            sec_glrt = glrt_per_pair[offset:offset + count]
            sec_speed = aligned_speed[offset:offset + count]
            sec_aligned = aligned[offset:offset + count]

            binary_filter = correlation_threshold(sec_glrt, corr_threshold=self.corr_threshold)
            filtered_speed, _ = self._speed_filter.filtering_speed(sec_speed, binary_filter)
            glrt_summed = np.sum(sec_glrt, axis=1)

            results.append((glrt_summed, filtered_speed, sec_aligned))
            offset += count

        return results, stage_times

    def process_file(self, x: np.ndarray, d: np.ndarray, d_ns: np.ndarray | None = None):
        """Processes a single window of sensor data through the DTAN pipeline.

        Args:
            x: Sensor data (channels, time_samples) - exactly window_size samples
            d: Timestamps for each time sample
            d_ns: Timestamps in nanoseconds (optional, for output messages)

        Yields:
            DirectionResult named tuple with trimmed arrays.
        """
        with self._inference_lock:
            yield from self._process_file_unlocked(x, d, d_ns)

    def _process_file_unlocked(self, x: np.ndarray, d: np.ndarray, d_ns: np.ndarray | None = None):
        C, L = x.shape

        if self.Nch > C:
            logger.warning(f"Received {C} channels, need >= {self.Nch}. Skipping.")
            return

        if self.window_size > L:
            logger.warning(f"Received {L} samples, need {self.window_size}. Skipping.")
            return

        if self.window_size < L:
            logger.warning(
                f"Received {L} samples, expected {self.window_size}. "
                f"Processing first window only."
            )

        data_window = x[:, :self.window_size]
        date_window = d[:self.window_size]
        date_window_ns = d_ns[:self.window_size] if d_ns is not None else None

        # --- Forward pass ---
        _fwd_per_pair, fwd_summed, fwd_filtered, fwd_aligned, _fwd_thetas = (
            self._process_single_direction(data_window)
        )

        if self.calibration_data is not None:
            fwd_summed = self.calibration_data.apply_coupling_correction(fwd_summed)

        yield from self._trim_and_yield(
            fwd_summed, fwd_filtered, fwd_aligned,
            date_window, date_window_ns, direction_value=0,
        )

        # --- Reverse pass (if bidirectional) ---
        if self.bidirectional_detection:
            data_flipped = data_window[::-1, :].copy()
            _rev_per_pair, rev_summed, rev_filtered, rev_aligned, _rev_thetas = (
                self._process_single_direction(data_flipped)
            )
            rev_summed = rev_summed[::-1, :].copy()
            rev_filtered = rev_filtered[::-1, :, :].copy()

            yield from self._trim_and_yield(
                rev_summed, rev_filtered, rev_aligned,
                date_window, date_window_ns, direction_value=1,
            )
