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
from .utils import correlation_threshold, find_ind, normalize_windows


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
            count_data: Tuple of (counts, intervals, timestamps) from VehicleCounter
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

        Args:
            grid_t: Transformed grid data

        Returns:
            Speed values for each sensor and time point
        """
        delta = grid_t - self.uniform_grid
        delta *= self.window_size
        delta += self.eps

        speed_section = self.speed_scaling / delta

        invalid_mask = (np.abs(speed_section) > self.max_speed) | (np.abs(speed_section) < self.min_speed)
        speed_section = np.where(invalid_mask, np.nan, speed_section)

        return speed_section

    def apply_glrt(self, aligned: np.ndarray, safety: int = GLRT_EDGE_SAFETY_SAMPLES) -> np.ndarray:
        """Applies Generalized Likelihood Ratio Test to aligned data.

        Args:
            aligned: 3D array of aligned sensor data
            safety: Samples to exclude at edges

        Returns:
            2D array of GLRT results
        """
        dim = aligned.shape
        l = self.glrt_win

        values = aligned[:, :-1, :] * aligned[:, 1:, :]

        res = torch.zeros((dim[0], dim[2] - l))
        out = torch.zeros((dim[0], dim[2]))

        for i in range(dim[2] - l):
            res[:, i] = torch.sum(values[:, :, i : i + l], dim=(1, 2))

        out[:, safety + l // 2 : -safety - l // 2] = res[:, safety:-safety]
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
        self, speed: np.ndarray, binary_filter: np.ndarray, intervals: tuple
    ) -> np.ndarray:
        """Filters unrealistic speeds from a spatial section.

        Args:
            speed: Speed values for a single section
            binary_filter: Binary mask indicating valid intervals
            intervals: Tuple of (start_indices, end_indices)

        Returns:
            Filtered speed data with invalid values as NaN
        """
        filtered_data = np.where(binary_filter == 1, speed, np.nan)
        start, finish = intervals

        vehicle_speeds = np.array(
            [np.nanmedian(filtered_data[:, start[i] : finish[i]]) for i in range(len(start))]
        )

        # Use abs() to handle both directions (negative = opposite direction)
        mask = (np.abs(vehicle_speeds) > self.max_speed) | (np.abs(vehicle_speeds) < self.min_speed)

        for idx in np.where(mask)[0]:
            filtered_data[:, start[idx] : finish[idx]] = np.nan

        return filtered_data

    def filtering_speed(self, speed: np.ndarray, binary_filter: np.ndarray) -> tuple:
        """Filters unrealistic speeds from all sections.

        Args:
            speed: 3D array of speed values (sections, channels, time)
            binary_filter: 3D binary mask for valid intervals

        Returns:
            Tuple of (filtered_speed, intervals_list)
        """
        filtered_data_list = []
        intervals_list = find_ind(binary_filter)

        for i in range(speed.shape[0]):
            filtered_data_per_channel = self.filtering_speed_per_channel(
                speed[i], binary_filter[i], intervals_list[i]
            )
            filtered_data_list.append(filtered_data_per_channel)

        return np.array(filtered_data_list), intervals_list

    def process_file(self, x: np.ndarray, d: np.ndarray, d_ns: np.ndarray | None = None):
        """Processes a single window of sensor data through the DTAN pipeline.

        The rolling buffer logic is now handled by RollingBufferedTransformer,
        which maintains a deque(maxlen=300) and triggers processing every 250
        new messages. This method receives exactly window_size (300) samples
        and processes one window.

        The 50-sample overlap between windows is automatically maintained by
        the rolling FIFO buffer in RollingBufferedTransformer.

        Args:
            x: Sensor data (channels, time_samples) - exactly window_size samples
            d: Timestamps for each time sample (datetime objects)
            d_ns: Timestamps in nanoseconds (optional, for output messages)

        Yields:
            Tuple of (unaligned_speed, filtered_speed, glrt_res, aligned_data, date_window, date_window_ns)
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

        # Process window through DTAN pipeline
        space_split = self.split_channel_overlap(data_window)
        space_split = normalize_windows(space_split)

        thetas, grid_t = self.predict_theta(space_split)
        aligned = self.align_window(space_split, thetas, self.Nch, align_channel_idx)

        all_speed = self.comp_speed(grid_t)
        aligned_speed_tensor = self.align_window(
            all_speed, thetas[:, :-1, :], self.Nch - 1, align_channel_idx
        )
        aligned_speed = aligned_speed_tensor.detach().cpu().numpy()

        glrt_tensor = self.apply_glrt(aligned)
        glrt_res = glrt_tensor.detach().cpu().numpy()

        # Apply coupling correction if available
        if self.calibration_data is not None:
            glrt_res = self.calibration_data.apply_coupling_correction(glrt_res)

        # Apply threshold (variable or static)
        if self.calibration_data is not None:
            binary_filter = self.calibration_data.apply_variable_threshold(glrt_res)
        else:
            binary_filter = correlation_threshold(glrt_res, corr_threshold=self.corr_threshold)
        filtered_speed, self.intervals = self.filtering_speed(aligned_speed, binary_filter)

        # Generate visualization if enabled and interval elapsed
        if self.visualizer is not None:
            current_time = time.time()
            if current_time - self.last_visualization_time >= self.visualization_interval:
                try:
                    self.visualizer.generate_waterfall(
                        glrt_res=glrt_res,
                        filtered_speed=filtered_speed,
                        intervals_list=self.intervals,
                        date_window=date_window,
                        calibration_data=self.calibration_data,
                        min_speed_kmh=self.min_speed,
                        max_speed_kmh=self.max_speed,
                        count_data=self.count_data_for_viz,
                    )
                    self.last_visualization_time = current_time
                except Exception as e:
                    logger.error(f"Visualization generation failed: {e}")

        unaligned_speed_tensor = self.align_window(
            filtered_speed, -thetas[:, :-1, :], self.Nch - 1, align_channel_idx
        )
        unaligned_speed = unaligned_speed_tensor.detach().cpu().numpy()
        aligned_np = aligned.detach().cpu().numpy()

        # Trim edges for seamless output
        trim_start = self.edge_trim
        trim_end = self.window_size - self.edge_trim
        trimmed_unaligned = unaligned_speed[..., trim_start:trim_end]
        trimmed_filtered = filtered_speed[..., trim_start:trim_end]
        trimmed_glrt = glrt_res[:, trim_start:trim_end]
        trimmed_aligned = aligned_np[..., trim_start:trim_end]
        trimmed_date = date_window[trim_start:trim_end]
        trimmed_date_ns = date_window_ns[trim_start:trim_end] if date_window_ns is not None else None

        yield trimmed_unaligned, trimmed_filtered, trimmed_glrt, trimmed_aligned, trimmed_date, trimmed_date_ns

