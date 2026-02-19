from __future__ import annotations

import logging
import numpy as np

from .constants import COUNTING_STEP_SAMPLES, SPEED_CONVERSION_FACTOR
from .utils import correlation_threshold, find_ind

logger = logging.getLogger(__name__)

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None


class VehicleCounter:
    """Accumulates and processes sensor data to count vehicles.

    Handles processing of data chunks from multiple windows, accumulating
    them until a full time window is reached. Applies a neural network
    model to the aggregated data to estimate vehicle counts.

    Args:
        vehicle_counting_model: Path to the vehicle counting model file
        time_window_duration: Duration of the time window in seconds
        detection_threshold: Path to detection thresholds CSV
        mean_std_features: Path to feature normalization CSV (optional)
        Nch: Number of channels per section
        fs: Sampling frequency (Hz)
        corr_threshold: Correlation threshold for filtering

    Attributes:
        time_window_duration: Duration of the time window in seconds
        Nch: Number of channels
        fs: Sampling frequency
        count: Vehicle counts for each sensor (after processing)
    """

    def __init__(
        self,
        vehicle_counting_model: str | None,
        time_window_duration: int,
        detection_threshold: str,
        mean_std_features: str | None,
        Nch: int,
        fs: float,
        corr_threshold: float = 500,
    ):
        self.time_window_duration = time_window_duration
        self.detection_threshold = detection_threshold
        self.Nch = Nch
        self.fs = fs

        self.current_time_window = 0
        self.step = COUNTING_STEP_SAMPLES

        if vehicle_counting_model:
            self.NN_model = torch.load(vehicle_counting_model, weights_only=False)
            self.features_duration = int(self.fs * self.time_window_duration)

            if mean_std_features:
                mean_std_data = np.genfromtxt(mean_std_features, delimiter=",")
                (
                    self.mean_duration,
                    self.mean_GLRT_sum,
                    self.mean_speeds,
                    self.mean_occupancy_rate,
                    self.mean_energy,
                ) = mean_std_data[0]
                (
                    self.std_duration,
                    self.std_GLRT_sum,
                    self.std_speeds,
                    self.std_occupancy_rate,
                    self.std_energy,
                ) = mean_std_data[1]
            else:
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

            self.detection_thresholds = np.genfromtxt(detection_threshold, delimiter=",")

            # Log expected feature ranges for diagnosis
            logger.info(
                f"NN feature normalization: GLRT_sum expect={self.mean_GLRT_sum:.1f}±{self.std_GLRT_sum:.1f}, "
                f"speed expect={self.mean_speeds:.2f}±{self.std_speeds:.2f}m/s"
            )
        else:
            self.NN_model = None
            self.features_duration = None
            self.detection_thresholds = None

        self.n = 0
        self.corr_threshold = corr_threshold
        self.dataset_feature_names = [
            "Interval length (data points)",
            "GLRT sum",
            "Interval vehicles speed (m/s)",
            "occupancy rate (%)",
            "Interval energy",
        ]
        self.count = None

    def check_ind(self, binary_mask: np.ndarray, indices: list) -> np.ndarray:
        """Creates a binary mask from interval indices.

        Args:
            binary_mask: Original binary mask (used for shape)
            indices: List of (start, end) tuples per row

        Returns:
            Binary mask with 1s at interval positions
        """
        out = np.zeros(binary_mask.shape) * np.nan
        for n, ind in enumerate(indices):
            if len(ind) == 2:
                begin = ind[0]
                end = ind[1]
                for start, stop in zip(begin, end):
                    out[n, start:stop] = 1
        return out

    def create_visualization(
        self,
        count: list | None = None,
        indices: list | None = None,
        shape: tuple = (37, 3600),
    ) -> np.ndarray:
        """Generates a visualization of vehicle counts over time.

        Args:
            count: Vehicle counts (defaults to self.count)
            indices: Detection intervals (defaults to self.intervals)
            shape: Output shape (sections, time_samples)

        Returns:
            2D array with vehicle counts per interval
        """
        if not count:
            count = self.count
        if not indices:
            indices = self.intervals

        out_check = np.zeros(shape)

        for i, (cpt, (start, end)) in enumerate(zip(count, indices)):
            if cpt is not None:
                for cp, b, e in zip(cpt, start, end):
                    out_check[i, b:e] = cp
        return out_check


    def process_data_chunk(
        self,
        aligned_speed: np.ndarray,
        correlations: np.ndarray,
        aligned_data: np.ndarray,
    ):
        """Processes a chunk of sensor data for vehicle counting.

        Accumulates incoming data chunks until a full time window is reached,
        then processes and yields results.

        Args:
            aligned_speed: Aligned speed data from current chunk
            correlations: GLRT correlation data from current chunk
            aligned_data: Aligned sensor data from current chunk

        Yields:
            Tuple of (count, intervals) - vehicle counts and detection intervals
        """
        time_window_samples = int(self.time_window_duration * self.fs)
        self.n += 1

        if not hasattr(self, "acc_correlations"):
            self.acc_aligned_speed = aligned_speed
            self.acc_correlations = correlations
            self.acc_aligned_data = aligned_data
        else:
            self.acc_aligned_speed = np.concatenate((self.acc_aligned_speed, aligned_speed), axis=2)
            self.acc_correlations = np.concatenate((self.acc_correlations, correlations), axis=1)
            self.acc_aligned_data = np.concatenate((self.acc_aligned_data, aligned_data), axis=2)

        if self.acc_correlations.shape[1] >= time_window_samples:
            aligned_speed_window = self.acc_aligned_speed[:, :, :time_window_samples]
            correlations_window = self.acc_correlations[:, :time_window_samples]
            aligned_data_window = self.acc_aligned_data[:, :, :time_window_samples]

            self.count, self.intervals = self.process_window_data(
                aligned_speed_window, correlations_window, aligned_data_window
            )

            self.acc_aligned_speed = self.acc_aligned_speed[:, :, self.step :]
            self.acc_correlations = self.acc_correlations[:, self.step :]
            self.acc_aligned_data = self.acc_aligned_data[:, :, self.step :]

            yield self.count, self.intervals

    def process_window_data(
        self,
        aligned_speed_window: np.ndarray,
        correlations_window: np.ndarray,
        aligned_data_window: np.ndarray,
    ) -> tuple:
        """Processes a time window of sensor data for vehicle counting.

        Args:
            aligned_speed_window: Aligned speed data within the time window
            correlations_window: Correlation data within the time window
            aligned_data_window: Aligned sensor data within the time window

        Returns:
            Tuple of (counts, intervals) per sensor
        """
        binary_mask = correlation_threshold(correlations_window, corr_threshold=self.corr_threshold)
        intervals = find_ind(binary_mask)

        count = [
            self.apply_model(thresh, np.asarray(inter), speed, data, corr)
            for thresh, inter, speed, data, corr in zip(
                self.detection_thresholds,
                intervals,
                aligned_speed_window,
                aligned_data_window,
                correlations_window,
            )
        ]

        # Log summary of counting run
        total_counts = sum(np.sum(c) for c in count if c is not None)
        non_zero_counts = sum(np.count_nonzero(c) for c in count if c is not None)
        logger.info(
            f"Counting run complete: {len(count)} sections, "
            f"{non_zero_counts} non-zero intervals, total_counts={total_counts:.1f}"
        )

        return count, intervals

    _first_apply = True  # Track first call for diagnostic logging

    def apply_model(
        self,
        threshold: np.ndarray,
        intervals: np.ndarray,
        speed_section: np.ndarray,
        data_section: np.ndarray,
        corr_section: np.ndarray,
    ) -> np.ndarray:
        """Applies the vehicle counting model to data intervals.

        Args:
            threshold: Detection threshold for the sensor
            intervals: Start and end indices of intervals
            speed_section: Speed data for the sensor
            data_section: Aligned data for the sensor
            corr_section: Correlation (GLRT) values

        Returns:
            Vehicle counts for each interval
        """
        n_interv = intervals.shape[1]
        energy_interval = np.empty(n_interv)
        GLRT_sum_interval = np.empty(n_interv)
        all_speed = np.empty(n_interv)

        time_duration = intervals[1] - intervals[0]

        for j in range(n_interv):
            energy_interval[j] = np.sum(data_section[:, intervals[0, j] : intervals[1, j]] ** 2)

            # Use RAW GLRT sum (no threshold subtraction)
            # Model expects GLRT_sum mean of 185,449 which suggests raw values
            GLRT_sum_interval[j] = np.sum(corr_section[intervals[0, j] : intervals[1, j]])

            speed_ = np.nanmedian(speed_section[:, intervals[0, j] : intervals[1, j]])
            all_speed[j] = np.nan_to_num(speed_)

        # Convert km/h to m/s
        vehicles_speeds = all_speed / SPEED_CONVERSION_FACTOR

        vehicles_occupancy_rate = np.sum(time_duration)
        vehicles_occupancy_rate /= self.features_duration
        vehicles_occupancy_rate *= np.ones(len(time_duration))

        # Diagnostic logging for first interval
        if VehicleCounter._first_apply and n_interv > 0:
            VehicleCounter._first_apply = False
            logger.info(
                f"First interval features (raw): GLRT_sum={GLRT_sum_interval[0]:.1f}, "
                f"speed={vehicles_speeds[0]:.2f}m/s, duration={time_duration[0]}, "
                f"threshold={threshold[0]:.1f}"
            )

        dataset_all_data = np.array(
            [
                (time_duration - self.mean_duration) / self.std_duration,
                (GLRT_sum_interval - self.mean_GLRT_sum) / self.std_GLRT_sum,
                (vehicles_speeds - self.mean_speeds) / self.std_speeds,
                (vehicles_occupancy_rate - self.mean_occupancy_rate) / self.std_occupancy_rate,
                (energy_interval - self.mean_energy) / self.std_energy,
            ]
        )

        section_count = None
        with torch.no_grad():
            if self.NN_model:
                section_count = (
                    self.NN_model(torch.tensor(dataset_all_data.T, dtype=torch.float32)).numpy().flatten()
                )

        if section_count is not None and section_count.size > 0:
            section_count[vehicles_speeds == 0] = 0
            logger.info(f"NN counting output: {len(section_count)} intervals, counts range [{section_count.min():.2f}, {section_count.max():.2f}], non-zero={np.count_nonzero(section_count)}")
            return section_count
        else:
            logger.warning(f"NN model produced no output for {len(time_duration)} intervals")
            return np.zeros(len(time_duration))
