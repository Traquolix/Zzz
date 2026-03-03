from __future__ import annotations

import logging
import time
import numpy as np

try:
    import torch
    from torch.utils.data import DataLoader, TensorDataset
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

    class DataLoader:
        pass

    class TensorDataset:
        pass

    class torch:
        @staticmethod
        def tensor(*args, **kwargs):
            return None

from .calibration import CalibrationData

logger = logging.getLogger(__name__)
from .constants import (
    DEFAULT_EPSILON,
    GLRT_DEFAULT_WINDOW,
    GLRT_EDGE_SAFETY_SAMPLES,
    SPEED_CONVERSION_FACTOR,
)
from .utils import (
    compute_speed_from_pairs,
    correlation_threshold,
    find_ind,
    normalize_channel_energy,
)


def compute_edge_trim(glrt_window: int = GLRT_DEFAULT_WINDOW, safety: int = GLRT_EDGE_SAFETY_SAMPLES) -> int:
    """Compute edge trim size based on GLRT parameters.

    The GLRT zeroes out (safety + glrt_window//2) samples at each edge.
    We trim these to avoid outputting degraded data.

    Args:
        glrt_window: GLRT sliding window size
        safety: Additional safety margin at edges

    Returns:
        Number of samples to trim from each edge
    """
    return safety + glrt_window // 2


class VehicleSpeedEstimator:
    """Processes sensor data to estimate vehicle speeds using DTAN alignment.

    Uses a sliding window approach with CPAB transformations to align sensor
    channels and calculate vehicle speeds from the alignment parameters.

    Note: Not thread-safe. Each instance must be used by a single thread/buffer
    key at a time.

    Args:
        model_args: Configuration from Args_NN_model_all_channels
        ovr_time: Overlap ratio between consecutive time windows
        glrt_win: Window size for GLRT calculation
        min_speed: Minimum realistic vehicle speed (km/h)
        max_speed: Maximum realistic vehicle speed (km/h)
        corr_threshold: Correlation threshold for filtering (fallback if no calibration)
        verbose: Enable verbose logging
        calibration_data: Optional CalibrationData for variable threshold + coupling

    Attributes:
        window_size: Size of the processing window in samples
        overlap_time: Overlap between consecutive time windows
        Nch: Number of channels per section
        fs: Sampling frequency (Hz)
        gauge: Sensor gauge distance (meters)
        calibration_data: Optional calibration for variable threshold and coupling correction
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
            return

        self.verbose = verbose
        self.window_size = model_args.signal_length
        self.overlap_time = int(self.window_size * ovr_time)
        self.overlap_space = model_args.N_channels

        self.Nch = model_args.Nch
        self.fs = model_args.fs
        self.gauge = model_args.gauge

        self.glrt_win = glrt_win

        self.intervals = None

        # Edge trimming: cut degraded samples from window edges
        # GLRT zeroes out (safety + glrt_win//2) samples at each edge
        self.edge_trim = compute_edge_trim(glrt_win, GLRT_EDGE_SAFETY_SAMPLES)

        # Validate overlap is sufficient for seamless window handoff
        # Overlap should be >= 2 * edge_trim so trimmed outputs are adjacent
        min_required_overlap = 2 * self.edge_trim
        if self.overlap_time < min_required_overlap:
            logger.warning(
                f"Overlap ({self.overlap_time} samples) < 2 * edge_trim ({min_required_overlap}). "
                f"This may cause gaps in output. Consider increasing time_overlap_ratio."
            )
        elif self.overlap_time > min_required_overlap:
            logger.info(
                f"Overlap ({self.overlap_time}) > min required ({min_required_overlap}). "
                f"Output will have duplicate timestamps (downstream should deduplicate)."
            )

        self.model_args = model_args

        self.T, self.model = model_args.get_model_Theta()

        device = model_args.device_name
        self.model = self.model.to(device)
        self.model.eval()

        self.eps = DEFAULT_EPSILON
        self.min_speed = min_speed
        self.max_speed = max_speed

        self.uniform_grid = self.T.uniform_meshgrid(
            (self.model_args.input_shape, 1)
        ).detach().to("cpu").numpy()

        self.dx = self.gauge
        self.dt = 1.0 / self.fs
        self.speed_scaling = SPEED_CONVERSION_FACTOR * self.fs * self.gauge

        self.corr_threshold = corr_threshold
        self.calibration_data = calibration_data
        self.bidirectional_detection = bidirectional_detection
        self.speed_glrt_factor = speed_glrt_factor
        self.speed_weighting = speed_weighting
        self.speed_positive_glrt_only = speed_positive_glrt_only

        # Initialize visualizer if enabled
        self.visualizer = None
        self.last_visualization_time = 0
        self.visualization_interval = 0
        # Store last visualization data for post-filter plot
        self.last_viz_data = None
        # Store count data for visualization overlay
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
        """Update the section name for visualization output.

        Args:
            section: Section name (e.g., 'section1', 'default')
        """
        if self.visualizer is not None:
            self.visualizer.section = section

    def set_count_data(self, count_data: tuple | None):
        """Store count data for visualization overlay.

        Args:
            count_data: Tuple of (counts, intervals, timestamps) from SimpleIntervalCounter
        """
        self.count_data_for_viz = count_data
        if count_data is not None:
            counts, intervals, timestamps = count_data
            total_counts = sum(len(c) if c is not None else 0 for c in counts)
            logger.info(f"Count data received for viz: {total_counts} count values across {len(counts)} sections")

    def split_channel_overlap(self, x: np.ndarray) -> np.ndarray:
        """Splits data into overlapping spatial windows.

        Args:
            x: Input data (channels, time_samples)

        Returns:
            3D array (num_windows, Nch, time_samples)
        """
        C, _ = x.shape
        step = self.Nch - self.overlap_space

        max_complete_windows = (C - self.Nch) // step + 1
        usable_channels = min(C, (max_complete_windows - 1) * step + self.Nch)

        if usable_channels < C:
            x = x[:usable_channels, :]
            C = usable_channels

        start_indices = np.arange(0, C, step)
        end_indices = start_indices + self.Nch

        valid_windows = end_indices <= C
        start_indices = start_indices[valid_windows]
        end_indices = end_indices[valid_windows]

        num_windows = len(start_indices)
        result = np.empty((num_windows, self.Nch, x.shape[1]), dtype=x.dtype)

        for i, (start, end) in enumerate(zip(start_indices, end_indices)):
            result[i] = x[start:end, :]

        return result

    def comp_speed(self, grid_t: np.ndarray) -> np.ndarray:
        """Calculates vehicle speeds from transformed grid data.

        Matches notebook: returns absolute speed values without filtering.
        Speed filtering is deferred to filtering_speed() and
        compute_speed_from_pairs() downstream.

        Args:
            grid_t: Transformed grid data

        Returns:
            Absolute speed values for each sensor and time point
        """
        delta = grid_t - self.uniform_grid
        delta *= self.window_size
        delta += self.eps

        speed_section = self.speed_scaling / delta

        # Take absolute value — sign only indicates direction, not speed magnitude
        # (matches notebook's comp_speed which returns np.abs())
        speed_section = np.abs(speed_section)

        return speed_section

    def apply_glrt(self, aligned, safety: int = GLRT_EDGE_SAFETY_SAMPLES):
        """Applies Generalized Likelihood Ratio Test to aligned data.

        Returns per-pair GLRT values (3D) so downstream can aggregate per-pair
        speeds and do per-pair thresholding.

        Args:
            aligned: 3D tensor of aligned sensor data (sections, Nch, time)
            safety: Samples to exclude at edges

        Returns:
            3D tensor of per-pair GLRT results (sections, Nch-1, time)
        """
        dim = aligned.shape
        l = self.glrt_win
        n_pairs = dim[1] - 1

        # Per-pair product: adjacent channel correlation
        values = aligned[:, :-1, :] * aligned[:, 1:, :]

        # Sliding window sum per pair
        res = torch.zeros((dim[0], n_pairs, dim[2] - l))
        out = torch.zeros((dim[0], n_pairs, dim[2]))

        for i in range(dim[2] - l):
            res[:, :, i] = torch.sum(values[:, :, i : i + l], dim=2)

        out[:, :, safety + l // 2 : -safety - l // 2] = res[:, :, safety:-safety]
        return out

    def predict_theta(self, data_window: np.ndarray) -> tuple:
        """Predicts transformation parameters from data.

        Args:
            data_window: Input data (num_windows, Nch, time_samples)

        Returns:
            Tuple of (thetas, grid_t)
        """
        batch_size = self.model_args.batch_size

        test_data_torch = torch.from_numpy(data_window)
        test = TensorDataset(test_data_torch)

        test_loader = DataLoader(
            test, batch_size=batch_size, shuffle=False, num_workers=0, pin_memory=True
        )

        with torch.no_grad():
            torch.backends.cudnn.benchmark = True

            test_thetas_list = []
            test_grid_t_list = []

            for data in test_loader:
                device = self.model_args.device_name
                data = data[0].to(torch.FloatTensor(), non_blocking=True).to(device, non_blocking=True)

                _, thetas, grid_t = self.model(data, return_theta_and_transformed_grid=True)

                test_thetas_list.append(thetas.detach().cpu().numpy())
                test_grid_t_list.append(grid_t.detach().cpu().numpy())

        thetas = np.vstack(test_thetas_list)
        thetas = torch.from_numpy(thetas)
        grid_t = np.vstack(test_grid_t_list)

        return thetas, grid_t

    def align_window(
        self,
        space_split: np.ndarray,
        thetas_in: torch.Tensor,
        Nch: int,
        align_channel_idx: int,
    ) -> torch.Tensor:
        """Aligns data window using CPAB transformation parameters.

        Args:
            space_split: Input data (num_windows, Nch, time_samples)
            thetas_in: CPAB transformation parameters
            Nch: Number of channels
            align_channel_idx: Reference channel index

        Returns:
            Aligned data tensor
        """
        dim = space_split.shape
        N_theta = thetas_in.shape[2]

        thetas = thetas_in.to(self.model_args.device_name).to(dtype=torch.float32)
        space_split = torch.from_numpy(space_split).to(self.model_args.device_name).to(dtype=torch.float32)
        output = torch.clone(space_split)

        output = torch.flatten(output, start_dim=0, end_dim=1).unsqueeze(dim=1)

        first_to_ref = align_channel_idx
        end_to_ref = align_channel_idx

        for i in range(max(first_to_ref, Nch - end_to_ref - 1)):
            nbr_zeros = end_to_ref - first_to_ref + 1

            zeros = torch.zeros((dim[0], nbr_zeros, N_theta), device=self.model_args.device_name)

            thetas_flatten = torch.cat(
                (
                    thetas[:, min(i, align_channel_idx) : align_channel_idx],
                    zeros,
                    -thetas[:, align_channel_idx : max(Nch - 1 - i, align_channel_idx)],
                ),
                dim=1,
            )

            thetas_flatten = torch.flatten(thetas_flatten, start_dim=0, end_dim=1)

            output = self.T.transform_data(output, thetas_flatten, outsize=(self.model_args.signal_length,))

            end_to_ref = min(end_to_ref + 1, Nch - 1)
            first_to_ref = max(first_to_ref - 1, 0)

        return output.reshape(dim)

    def filtering_speed_per_channel(
        self, speed: np.ndarray, binary_filter: np.ndarray, intervals: list
    ) -> np.ndarray:
        """Filters unrealistic speeds from a single section, per channel/pair.

        Matches notebook: processes each channel independently with its own
        intervals derived from the per-channel binary mask.

        Args:
            speed: Speed values (channels/pairs, time) for one section
            binary_filter: Binary mask (channels/pairs, time) for one section
            intervals: List of (start_list, end_list) tuples, one per channel

        Returns:
            Filtered speed data with invalid values as NaN
        """
        filtered_data = speed * binary_filter

        for ch_idx in range(speed.shape[0]):
            start, finish = intervals[ch_idx]

            if len(start) == 0:
                continue

            vehicle_speeds = np.array(
                [np.nanmedian(filtered_data[ch_idx, start[i] : finish[i]])
                 for i in range(len(start))]
            )

            mask = (vehicle_speeds > self.max_speed) | (vehicle_speeds < self.min_speed)

            for idx in np.where(mask)[0]:
                filtered_data[ch_idx, start[idx] : finish[idx]] = np.nan

        return filtered_data

    def filtering_speed(self, speed: np.ndarray, binary_filter: np.ndarray) -> tuple:
        """Filters unrealistic speeds from all sections.

        Matches notebook: for each section, computes per-channel intervals from
        the 2D binary filter, then filters per channel independently.

        Args:
            speed: 3D array of speed values (sections, channels/pairs, time)
            binary_filter: 3D binary mask for valid intervals

        Returns:
            Tuple of (filtered_speed, intervals_list)
        """
        filtered_data_list = []
        intervals_list = []

        for i in range(speed.shape[0]):
            # Per-section: find_ind on 2D (channels, time) → list of (starts, ends) per channel
            section_intervals = find_ind(binary_filter[i])
            intervals_list.append(section_intervals)

            filtered_data_per_channel = self.filtering_speed_per_channel(
                speed[i], binary_filter[i], section_intervals
            )
            filtered_data_list.append(filtered_data_per_channel)

        return np.array(filtered_data_list), intervals_list

    def _process_single_direction(self, data_window: np.ndarray):
        """Process data in one direction through DTAN pipeline.

        Matches notebook's process_one_file flow:
        1. predict_theta → thetas, grid_t
        2. align_window → aligned channels
        3. comp_speed → absolute speeds
        4. align_window(speeds) → aligned_speed
        5. apply_glrt → per-pair GLRT (3D)
        6. correlation_threshold → per-pair binary mask
        7. filtering_speed → per-pair filtered speeds
        8. align_window(filtered, -thetas) → unaligned speeds

        Args:
            data_window: (channels, time) sensor data

        Returns:
            Tuple of (glrt_per_pair, glrt_summed, aligned_speed, aligned, thetas)
            - glrt_per_pair: (sections, Nch-1, time) per-pair GLRT
            - glrt_summed: (sections, time) summed GLRT for detection
            - aligned_speed: (sections, Nch-1, time) per-pair aligned speeds (raw, abs)
            - aligned: aligned sensor data tensor
            - thetas: CPAB transformation parameters
        """
        align_channel_idx = (self.Nch - 1) // 2

        space_split = self.split_channel_overlap(data_window)

        thetas, grid_t = self.predict_theta(space_split)
        aligned = self.align_window(space_split, thetas, self.Nch, align_channel_idx)

        all_speed = self.comp_speed(grid_t)
        aligned_speed_tensor = self.align_window(
            all_speed, thetas[:, :-1, :], self.Nch - 1, align_channel_idx
        )
        aligned_speed = aligned_speed_tensor.detach().cpu().numpy()

        # Per-pair GLRT: (sections, Nch-1, time)
        glrt_per_pair = self.apply_glrt(aligned).detach().cpu().numpy()

        # Per-pair thresholding (matches notebook's correlation_threshold + filtering_speed)
        binary_filter = correlation_threshold(glrt_per_pair, corr_threshold=self.corr_threshold)
        filtered_speed, _ = self.filtering_speed(aligned_speed, binary_filter)

        # Unalign filtered speeds back to original frame (matches notebook)
        unaligned_speed = self.align_window(
            filtered_speed, -thetas[:, :-1, :], self.Nch - 1, align_channel_idx
        ).detach().cpu().numpy()

        # Summed across pairs: (sections, time)
        glrt_summed = np.sum(glrt_per_pair, axis=1)

        return glrt_per_pair, glrt_summed, aligned_speed, aligned, thetas

    def process_file(self, x: np.ndarray, d: np.ndarray, d_ns: np.ndarray | None = None):
        """Processes a single window of sensor data through the DTAN pipeline.

        Supports bidirectional detection (forward + reverse pass) and per-pair
        speed aggregation matching notebook experiment 12.

        Args:
            x: Sensor data (channels, time_samples) - exactly window_size samples
            d: Timestamps for each time sample (datetime objects)
            d_ns: Timestamps in nanoseconds (optional, for output messages)

        Yields:
            Tuple of (unaligned_speed, filtered_speed, glrt_summed, aligned_data,
                       date_window, date_window_ns, direction_mask)
            All arrays are trimmed to exclude edge samples.
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

        align_channel_idx = (self.Nch - 1) // 2

        # Extract exactly one window
        data_window = x[:, :self.window_size]
        date_window = d[:self.window_size]
        date_window_ns = d_ns[:self.window_size] if d_ns is not None else None

        # Equalize per-channel energy before splitting into sections
        data_window = normalize_channel_energy(data_window)

        # --- Forward pass ---
        fwd_per_pair, fwd_summed, fwd_speed, fwd_aligned, fwd_thetas = (
            self._process_single_direction(data_window)
        )

        # --- Reverse pass (if bidirectional) ---
        if self.bidirectional_detection:
            data_flipped = data_window[::-1, :].copy()
            rev_per_pair, rev_summed, rev_speed, rev_aligned, rev_thetas = (
                self._process_single_direction(data_flipped)
            )
            # Flip results back to original spatial order
            rev_per_pair = rev_per_pair[::-1, :, :].copy()
            rev_summed = rev_summed[::-1, :].copy()
            rev_speed = rev_speed[::-1, :, :].copy()
        else:
            rev_per_pair = None
            rev_summed = None
            rev_speed = None

        n_pairs = self.Nch - 1
        # Per-pair threshold: corr_threshold is per-pair, sum threshold = corr_threshold * n_pairs
        summed_threshold = self.corr_threshold * n_pairs

        # Apply coupling correction if available
        if self.calibration_data is not None:
            fwd_summed = self.calibration_data.apply_coupling_correction(fwd_summed)

        # --- Combine directions ---
        if self.bidirectional_detection and rev_summed is not None:
            fwd_det = fwd_summed >= summed_threshold
            rev_det = rev_summed >= summed_threshold
            # Direction mask: 1=forward, 2=reverse, 3=both
            direction_mask = fwd_det.astype(int) + 2 * rev_det.astype(int)
            # Combined GLRT: max from either direction
            glrt_summed = np.maximum(fwd_summed, rev_summed)
            detection_mask = fwd_det | rev_det
        else:
            detection_mask = fwd_summed >= summed_threshold
            direction_mask = detection_mask.astype(int)
            glrt_summed = fwd_summed

        # --- Per-pair speed aggregation ---
        n_sections = fwd_per_pair.shape[0]
        combined_speed = np.full((n_sections, self.window_size), np.nan)

        for s in range(n_sections):
            # Use forward speed where forward is dominant, reverse where reverse is dominant
            if self.bidirectional_detection and rev_per_pair is not None:
                fwd_dominant = fwd_summed[s] >= rev_summed[s]
                # Forward pair speeds for this section
                fwd_s = compute_speed_from_pairs(
                    np.abs(fwd_per_pair[s]), np.abs(fwd_speed[s]),
                    self.min_speed, self.max_speed,
                    self.speed_positive_glrt_only, self.speed_weighting,
                )
                rev_s = compute_speed_from_pairs(
                    np.abs(rev_per_pair[s]), np.abs(rev_speed[s]),
                    self.min_speed, self.max_speed,
                    self.speed_positive_glrt_only, self.speed_weighting,
                )
                combined_speed[s] = np.where(fwd_dominant, fwd_s, rev_s)
            else:
                combined_speed[s] = compute_speed_from_pairs(
                    np.abs(fwd_per_pair[s]), np.abs(fwd_speed[s]),
                    self.min_speed, self.max_speed,
                    self.speed_positive_glrt_only, self.speed_weighting,
                )

        # --- Speed quality filter ---
        speed_quality_mask = detection_mask & (glrt_summed >= summed_threshold * self.speed_glrt_factor)
        filtered_speed = np.where(speed_quality_mask, combined_speed, np.nan)

        # Store intervals for counting (on full window, before edge trimming)
        binary_filter = detection_mask.astype(float)
        self._intervals_full = find_ind(binary_filter)

        # Generate visualization if enabled and interval elapsed
        if self.visualizer is not None:
            current_time = time.time()
            if current_time - self.last_visualization_time >= self.visualization_interval:
                try:
                    self.visualizer.generate_waterfall(
                        glrt_res=glrt_summed,
                        filtered_speed=filtered_speed[:, np.newaxis, :],
                        intervals_list=self._intervals_full,
                        date_window=date_window,
                        calibration_data=self.calibration_data,
                        min_speed_kmh=self.min_speed,
                        max_speed_kmh=self.max_speed,
                        count_data=self.count_data_for_viz,
                    )
                    self.last_visualization_time = current_time
                except Exception as e:
                    logger.error(f"Visualization generation failed: {e}")

        # Trim edges for seamless output
        trim_start = self.edge_trim
        trim_end = self.window_size - self.edge_trim

        # filtered_speed is already 2D (sections, time) - expand to 3D for compat
        # Downstream expects (sections, channels, time) for unaligned_speed
        trimmed_filtered = filtered_speed[:, np.newaxis, trim_start:trim_end]
        trimmed_glrt = glrt_summed[:, trim_start:trim_end]
        aligned_np = fwd_aligned.detach().cpu().numpy()
        trimmed_aligned = aligned_np[..., trim_start:trim_end]
        trimmed_date = date_window[trim_start:trim_end]
        trimmed_date_ns = date_window_ns[trim_start:trim_end] if date_window_ns is not None else None
        trimmed_direction = direction_mask[:, trim_start:trim_end]

        # Shift interval indices to match trimmed arrays
        self.intervals = []
        for starts, ends in self._intervals_full:
            shifted_starts = [s - trim_start for s in starts if s >= trim_start and s < trim_end]
            shifted_ends = [min(e - trim_start, trim_end - trim_start) for s, e in zip(starts, ends) if s >= trim_start and s < trim_end]
            self.intervals.append((shifted_starts, shifted_ends))

        # unaligned_speed = filtered_speed (already in original spatial frame for per-pair aggregated)
        yield trimmed_filtered, trimmed_filtered, trimmed_glrt, trimmed_aligned, trimmed_date, trimmed_date_ns, trimmed_direction

