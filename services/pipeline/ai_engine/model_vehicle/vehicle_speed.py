from __future__ import annotations

import logging
import time
import numpy as np
from scipy.signal import find_peaks

try:
    import torch
    import torch.nn.functional as F
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
    return safety


class VehicleSpeedEstimator:
    """Processes sensor data to estimate vehicle speeds using DTAN alignment.

    Matches the notebook's SpeedVehicules.process_one_file flow exactly:
    1. split_channel_overlap → spatial windows
    2. per-window energy normalization
    3. predict_theta → DTAN forward pass
    4. align_window → aligned channels
    5. comp_speed → absolute speeds from grid_t
    6. align_window(speeds) → aligned speeds
    7. apply_glrt (F.conv1d) → per-pair GLRT
    8. correlation_threshold → per-pair binary mask
    9. filtering_speed → median per interval, reject outside [min, max]
    10. align_window(-thetas) → unaligned speeds

    For bidirectional: runs forward + reverse, combines with OR on detection
    mask and max on GLRT. Filtered speeds come from the dominant direction.

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
        # Kept for config compatibility but unused — notebook doesn't have these
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

        # Edge trimming
        self.edge_trim = compute_edge_trim(glrt_win, GLRT_EDGE_SAFETY_SAMPLES)

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

        Matches notebook: speed = abs(3.6 * fs * gauge / delta)

        Args:
            grid_t: Transformed grid data

        Returns:
            Absolute speed values for each sensor and time point
        """
        delta = grid_t - self.uniform_grid
        delta *= self.window_size
        delta += self.eps

        speed_section = self.speed_scaling / delta
        speed_section = np.abs(speed_section)

        return speed_section

    def apply_glrt(self, aligned, safety: int = GLRT_EDGE_SAFETY_SAMPLES):
        """Applies GLRT using F.conv1d for vectorized sliding window sum.

        Matches notebook Cell 28: uses F.conv1d with box kernel instead
        of a Python loop.

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
        # F.conv1d with padding='valid' gives output length T - l + 1
        conv_out = F.conv1d(values_flat, kernel)  # (N*n_pairs, 1, T-l+1)
        conv_out = conv_out.squeeze(1).reshape(N, n_pairs, T - l + 1)

        # Place result with safety margins (matches notebook)
        out = torch.zeros((N, n_pairs, T), device=values.device)
        left = safety + l // 2
        right = T - safety - l // 2
        # conv_out indices [safety : -(safety)] map to out indices [left : right]
        valid_len = right - left
        if valid_len > 0 and conv_out.shape[2] > 2 * safety:
            out[:, :, left:right] = conv_out[:, :, safety:safety + valid_len]

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
            section_intervals = find_ind(binary_filter[i])
            intervals_list.append(section_intervals)

            filtered_data_per_channel = self.filtering_speed_per_channel(
                speed[i], binary_filter[i], section_intervals
            )
            filtered_data_list.append(filtered_data_per_channel)

        return np.array(filtered_data_list), intervals_list

    def _process_single_direction(self, data_window: np.ndarray):
        """Process data in one direction through DTAN pipeline.

        Matches notebook's process_one_file flow exactly:
        1. split_channel_overlap → spatial windows
        2. per-window energy normalization
        3. predict_theta → thetas, grid_t
        4. align_window → aligned channels
        5. comp_speed → absolute speeds
        6. align_window(speeds) → aligned_speed
        7. apply_glrt (F.conv1d) → per-pair GLRT
        8. correlation_threshold → per-pair binary mask
        9. filtering_speed → per-pair filtered speeds
        10. align_window(filtered, -thetas) → unaligned speeds

        Args:
            data_window: (channels, time) sensor data

        Returns:
            Tuple of:
            - glrt_per_pair: (sections, Nch-1, time) per-pair GLRT
            - glrt_summed: (sections, time) summed GLRT for detection
            - filtered_speed: (sections, Nch-1, time) filtered per-pair speeds
            - aligned: aligned sensor data tensor
            - thetas: CPAB transformation parameters
        """
        align_channel_idx = (self.Nch - 1) // 2

        space_split = self.split_channel_overlap(data_window)

        # Energy normalization per spatial window (matches notebook Cell 4/28)
        for i in range(space_split.shape[0]):
            space_split[i] = normalize_channel_energy(space_split[i])

        thetas, grid_t = self.predict_theta(space_split)
        aligned = self.align_window(space_split, thetas, self.Nch, align_channel_idx)

        all_speed = self.comp_speed(grid_t)
        aligned_speed = self.align_window(
            all_speed, thetas[:, :-1, :], self.Nch - 1, align_channel_idx
        ).detach().cpu().numpy()

        # Per-pair GLRT via F.conv1d: (sections, Nch-1, time)
        glrt_per_pair = self.apply_glrt(aligned).detach().cpu().numpy()

        # Per-pair thresholding + speed filtering (matches notebook exactly)
        binary_filter = correlation_threshold(glrt_per_pair, corr_threshold=self.corr_threshold)
        filtered_speed, _ = self.filtering_speed(aligned_speed, binary_filter)

        # Summed across pairs: (sections, time)
        glrt_summed = np.sum(glrt_per_pair, axis=1)

        return glrt_per_pair, glrt_summed, filtered_speed, aligned, thetas

    def _trim_and_yield(self, glrt_summed, filtered_speed, aligned, date_window,
                        date_window_ns, direction_value):
        """Trim edges and yield a single direction's results.

        Args:
            glrt_summed: (sections, time) summed GLRT
            filtered_speed: (sections, Nch-1, time) per-pair filtered speeds
            aligned: aligned sensor data tensor
            date_window: timestamps
            date_window_ns: timestamps in nanoseconds
            direction_value: 1 for forward, 2 for reverse

        Yields:
            8-tuple matching downstream expectations.
        """
        trim_start = self.edge_trim
        trim_end = self.window_size - self.edge_trim

        # Aggregate across pairs → median per section for speed messages
        agg_speed = np.nanmedian(filtered_speed[:, :, trim_start:trim_end], axis=1)
        trimmed_filtered = agg_speed[:, np.newaxis, :]

        trimmed_glrt = glrt_summed[:, trim_start:trim_end]
        aligned_np = aligned.detach().cpu().numpy() if hasattr(aligned, 'detach') else aligned
        trimmed_aligned = aligned_np[..., trim_start:trim_end]
        trimmed_date = date_window[trim_start:trim_end]
        trimmed_date_ns = date_window_ns[trim_start:trim_end] if date_window_ns is not None else None

        # Direction mask: constant for all sections/time in this yield
        n_sections = glrt_summed.shape[0]
        trimmed_time = trim_end - trim_start
        direction_mask = np.full((n_sections, trimmed_time), direction_value, dtype=int)

        trimmed_aligned_speed = filtered_speed[..., trim_start:trim_end]

        # Store intervals for counting
        summed_threshold = self.corr_threshold * (self.Nch - 1)
        detection_mask = (glrt_summed >= summed_threshold).astype(float)
        intervals_full = find_ind(detection_mask)

        self.intervals = []
        for starts, ends in intervals_full:
            shifted_starts = [s - trim_start for s in starts if s >= trim_start and s < trim_end]
            shifted_ends = [min(e - trim_start, trim_end - trim_start) for s, e in zip(starts, ends) if s >= trim_start and s < trim_end]
            self.intervals.append((shifted_starts, shifted_ends))
        self._intervals_full = intervals_full

        yield trimmed_filtered, trimmed_filtered, trimmed_glrt, trimmed_aligned, trimmed_date, trimmed_date_ns, direction_mask, trimmed_aligned_speed

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

        Matches the notebook's detection extraction:
        1. Threshold summed GLRT → binary mask → find_ind intervals
        2. Filter by min vehicle duration
        3. Per interval: median speed across pairs and time → one detection
        4. Per interval: count vehicles via peak detection, classify car/truck

        Args:
            glrt_summed: (sections, trimmed_time) summed GLRT
            aligned_speed_pairs: (sections, Nch-1, trimmed_time) per-pair speeds
            direction: 1 for forward, 2 for reverse
            timestamps_ns: nanosecond timestamps for trimmed window, or None
            min_vehicle_duration_s: minimum detection duration in seconds
            classify_threshold_factor: peaks above detect_thr * this factor are trucks

        Returns:
            List of detection dicts with keys:
                section_idx, speed_kmh, direction, timestamp_ns, glrt_max,
                vehicle_count, n_cars, n_trucks
        """
        summed_threshold = self.corr_threshold * (self.Nch - 1)
        min_vehicle_samples = max(3, int(min_vehicle_duration_s * self.fs))

        # Peak counting parameters (matches _lambda_peak_count)
        detect_thr = summed_threshold
        classify_thr = detect_thr * classify_threshold_factor
        min_peak_distance = max(1, int(0.25 * self.fs))
        min_prominence = max(1.0, 0.1 * detect_thr)

        binary_mask = correlation_threshold(glrt_summed, corr_threshold=summed_threshold)
        intervals_per_section = find_ind(binary_mask)

        detections = []
        for section_idx, (starts, ends) in enumerate(intervals_per_section):
            for v_start, v_end in zip(starts, ends):
                if v_end - v_start < min_vehicle_samples:
                    continue

                # Per-interval median speed across valid pairs
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

                # Timestamp at midpoint of interval
                t_mid = (v_start + v_end) // 2
                if timestamps_ns is not None and t_mid < len(timestamps_ns):
                    ts_ns = int(timestamps_ns[t_mid])
                else:
                    ts_ns = None

                # Peak counting: how many vehicles in this interval + car/truck
                seg = glrt_summed[section_idx, v_start:v_end]
                peaks, props = find_peaks(
                    seg, height=detect_thr, distance=min_peak_distance,
                    prominence=min_prominence,
                )

                if len(peaks) == 0 and np.nanmax(seg) >= detect_thr:
                    n_vehicles = 1.0
                    if np.nanmax(seg) >= classify_thr:
                        n_trucks = 1.0
                        n_cars = 0.0
                    else:
                        n_trucks = 0.0
                        n_cars = 1.0
                else:
                    n_vehicles = float(max(1, len(peaks)))
                    peak_heights = props.get("peak_heights", np.array([]))
                    n_trucks = float(np.sum(peak_heights >= classify_thr))
                    n_cars = float(len(peaks) - n_trucks)

                detections.append({
                    "section_idx": section_idx,
                    "speed_kmh": vehicle_speed,
                    "direction": direction,
                    "timestamp_ns": ts_ns,
                    "glrt_max": float(np.max(seg)),
                    "vehicle_count": n_vehicles,
                    "n_cars": n_cars,
                    "n_trucks": n_trucks,
                })

        return detections

    def process_file(self, x: np.ndarray, d: np.ndarray, d_ns: np.ndarray | None = None):
        """Processes a single window of sensor data through the DTAN pipeline.

        Matches notebook Cell 28: forward and reverse are processed independently
        and yielded separately. Each yield contains detections for one direction
        only, allowing the consumer to treat them as independent detection lists.

        Args:
            x: Sensor data (channels, time_samples) - exactly window_size samples
            d: Timestamps for each time sample
            d_ns: Timestamps in nanoseconds (optional, for output messages)

        Yields:
            8-tuple of (filtered_speed_3d, filtered_speed_3d, glrt_summed,
                        aligned_data, date_window, date_window_ns,
                        direction_mask, aligned_speed_per_pair)
            All arrays are trimmed to exclude edge samples.
            When bidirectional, yields twice: once for forward (direction=1),
            once for reverse (direction=2).
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

        # Extract exactly one window
        data_window = x[:, :self.window_size]
        date_window = d[:self.window_size]
        date_window_ns = d_ns[:self.window_size] if d_ns is not None else None

        # --- Forward pass ---
        fwd_per_pair, fwd_summed, fwd_filtered, fwd_aligned, fwd_thetas = (
            self._process_single_direction(data_window)
        )

        # Apply coupling correction if available
        if self.calibration_data is not None:
            fwd_summed = self.calibration_data.apply_coupling_correction(fwd_summed)

        # Generate visualization using forward results
        if self.visualizer is not None:
            current_time = time.time()
            if current_time - self.last_visualization_time >= self.visualization_interval:
                try:
                    viz_speed = np.nanmedian(fwd_filtered, axis=1, keepdims=True)
                    summed_threshold = self.corr_threshold * (self.Nch - 1)
                    det_mask = (fwd_summed >= summed_threshold).astype(float)
                    viz_intervals = find_ind(det_mask)
                    self.visualizer.generate_waterfall(
                        glrt_res=fwd_summed,
                        filtered_speed=viz_speed,
                        intervals_list=viz_intervals,
                        date_window=date_window,
                        calibration_data=self.calibration_data,
                        min_speed_kmh=self.min_speed,
                        max_speed_kmh=self.max_speed,
                        count_data=self.count_data_for_viz,
                    )
                    self.last_visualization_time = current_time
                except Exception as e:
                    logger.error(f"Visualization generation failed: {e}")

        # Yield forward results (direction=1)
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
            # Flip results back to original spatial order
            rev_summed = rev_summed[::-1, :].copy()
            rev_filtered = rev_filtered[::-1, :, :].copy()

            # Yield reverse results (direction=2)
            yield from self._trim_and_yield(
                rev_summed, rev_filtered, rev_aligned,
                date_window, date_window_ns, direction_value=2,
            )
