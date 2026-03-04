from __future__ import annotations

import numpy as np
from scipy.signal import find_peaks

from .constants import DEFAULT_EPSILON


def normalize_channel_energy(data: np.ndarray) -> np.ndarray:
    """Equalize per-channel energy so weak channels aren't ignored.

    Centers each channel (removes DC offset), then scales each channel
    so all channels have the same total energy.

    Args:
        data: 2D array (channels, time)

    Returns:
        Copy of data with equalized per-channel energy.
    """
    data_norm = data.copy()
    data_norm -= np.mean(data_norm, axis=1, keepdims=True)
    channel_energy = np.sum(np.square(data_norm), axis=1)
    mean_energy = np.mean(channel_energy)
    for i in range(data_norm.shape[0]):
        if channel_energy[i] > 0:
            data_norm[i] *= np.sqrt(mean_energy / channel_energy[i])
    return data_norm


def compute_speed_from_pairs(
    glrt_per_pair: np.ndarray,
    speed_per_pair: np.ndarray,
    min_speed: float = 20,
    max_speed: float = 120,
    positive_glrt_only: bool = True,
    weighting: str = "glrt",
) -> np.ndarray:
    """Compute speed from per-channel-pair estimates.

    Args:
        glrt_per_pair: (Nch-1, time) array of per-pair GLRT
        speed_per_pair: (Nch-1, time) array of per-pair speeds
        min_speed: minimum realistic speed (km/h)
        max_speed: maximum realistic speed (km/h)
        positive_glrt_only: if True, only use pairs with positive GLRT
        weighting: 'glrt' (GLRT-weighted average) or 'median'

    Returns:
        (time,) array of speeds computed from valid pairs
    """
    n_pairs, n_time = glrt_per_pair.shape
    result = np.full(n_time, np.nan)

    for t in range(n_time):
        glrt_col = glrt_per_pair[:, t]
        speed_col = speed_per_pair[:, t]

        valid_mask = (~np.isnan(speed_col)) & (speed_col >= min_speed) & (speed_col <= max_speed)
        if positive_glrt_only:
            valid_mask &= glrt_col > 0

        if np.sum(valid_mask) == 0:
            continue

        valid_speeds = speed_col[valid_mask]
        valid_glrt = glrt_col[valid_mask]

        if weighting == "glrt" and np.sum(np.maximum(valid_glrt, 0)) > 0:
            weights = np.maximum(valid_glrt, 0)
            result[t] = np.sum(valid_speeds * weights) / np.sum(weights)
        else:
            result[t] = np.median(valid_speeds)

    return result


def normalize_windows(space_split: np.ndarray, epsilon: float = DEFAULT_EPSILON) -> np.ndarray:
    """Apply z-score normalization to each window.

    Args:
        space_split: 3D array of shape (num_windows, channels, time_samples)
        epsilon: Small value to prevent division by zero

    Returns:
        Normalized array with same shape
    """
    for i in range(space_split.shape[0]):
        window = space_split[i]
        mean = window.mean()
        std = window.std() + epsilon
        space_split[i] = (window - mean) / std
    return space_split


def correlation_threshold(correlations_window: np.ndarray, corr_threshold: float = 500) -> np.ndarray:
    """Applies a threshold to a correlation matrix.

    Args:
        correlations_window: 2D array of correlation values
        corr_threshold: Static threshold value

    Returns:
        Binary mask where values >= threshold are 1, others are 0
    """
    out = np.zeros_like(correlations_window, dtype=np.float64)
    out[correlations_window >= corr_threshold] = 1
    return out


def count_peaks_in_segment(
    glrt_segment: np.ndarray,
    detect_threshold: float,
    classify_threshold: float,
    sampling_rate_hz: float,
    min_peak_distance_s: float = 0.25,
) -> tuple[int, int, int]:
    """Count vehicles and classify car/truck from a GLRT segment.

    Uses scipy.signal.find_peaks on the GLRT signal within one detection
    interval. Peaks above classify_threshold are trucks, the rest are cars.

    Args:
        glrt_segment: 1D array of summed GLRT values for one interval
        detect_threshold: Minimum GLRT height to count as a vehicle
        classify_threshold: GLRT height above which a peak is a truck
        sampling_rate_hz: Sampling rate for min peak distance conversion
        min_peak_distance_s: Minimum time between peaks in seconds

    Returns:
        (n_vehicles, n_cars, n_trucks)
    """
    if len(glrt_segment) == 0:
        return 0, 0, 0

    min_peak_distance = max(1, int(min_peak_distance_s * sampling_rate_hz))
    min_prominence = max(1.0, 0.1 * detect_threshold)

    peaks, props = find_peaks(
        glrt_segment,
        height=detect_threshold,
        distance=min_peak_distance,
        prominence=min_prominence,
    )

    if len(peaks) == 0:
        if np.nanmax(glrt_segment) >= detect_threshold:
            if np.nanmax(glrt_segment) >= classify_threshold:
                return 1, 0, 1
            return 1, 1, 0
        return 0, 0, 0

    n_vehicles = len(peaks)
    peak_heights = props.get("peak_heights", np.array([]))
    n_trucks = int(np.sum(peak_heights >= classify_threshold))
    n_cars = n_vehicles - n_trucks
    return n_vehicles, n_cars, n_trucks


def find_ind(binary_mask: np.ndarray) -> list:
    """Finds start and end indices of intervals in a binary mask.

    Args:
        binary_mask: 2D binary mask where intervals are marked by 1s

    Returns:
        List of tuples, each containing (start_indices, end_indices) for each row
    """
    return [find_ind_optimised(binary_mask[i, :]) for i in range(binary_mask.shape[0])]


def find_ind_optimised(y: np.ndarray) -> tuple:
    """Finds start and end indices of consecutive 1s in a 1D binary array.

    Args:
        y: 1D binary array containing 0s and 1s

    Returns:
        Tuple of (start_indices, end_indices) lists
    """
    start = np.where(np.diff(y) == 1)[0] + 1
    end = np.where(np.diff(y) == -1)[0] + 1

    if y[0] == 1:
        start = np.insert(start, 0, 0)

    if y[-1] == 1:
        end = np.append(end, len(y))

    return list(start), list(end)
