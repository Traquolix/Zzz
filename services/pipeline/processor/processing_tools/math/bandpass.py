import numpy as np
from scipy.signal import butter, sosfilt


class VectorizedBiquadFilter:
    def __init__(self, low_freq: float, high_freq: float, sampling_rate: float = 50.0):
        self.sos = butter(4, [low_freq, high_freq], btype="band", fs=sampling_rate, output="sos")
        self.sos = self.sos.astype(np.float64)
        self.num_sections = self.sos.shape[0]

    def create_state(self, num_channels: int) -> np.ndarray:
        # State shape for sosfilt: (num_sections, num_channels, 2)
        return np.zeros((self.num_sections, num_channels, 2), dtype=np.float64)

    def filter(self, values: np.ndarray, state: np.ndarray) -> np.ndarray:
        """Filter values with maintained state.

        Args:
            values: 1D (channels,) or 2D (samples, channels) array
            state: filter state, shape (num_sections, num_channels, 2)

        Returns:
            Filtered values, same shape as input. State is updated in-place.
        """
        x = np.asarray(values, dtype=np.float64)

        if x.ndim == 2:
            # Batch mode: (samples, channels) → sosfilt on (channels, samples)
            filtered, new_state = sosfilt(self.sos, x.T, axis=1, zi=state)
            state[:] = new_state
            result: np.ndarray = filtered.T
            return result
        else:
            # Single sample: (channels,) → sosfilt on (channels, 1) then squeeze
            filtered, new_state = sosfilt(self.sos, x[:, np.newaxis], axis=1, zi=state)
            state[:] = new_state
            result = np.asarray(filtered.squeeze(axis=1))
            return result
