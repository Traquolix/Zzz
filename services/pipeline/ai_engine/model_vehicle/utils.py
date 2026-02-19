from __future__ import annotations

import numpy as np

from .constants import DEFAULT_EPSILON


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
