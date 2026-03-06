import numpy as np
from scipy.signal import butter


class VectorizedBiquadFilter:
    def __init__(self, low_freq: float, high_freq: float, sampling_rate: float = 50.0):
        sos = butter(4, [low_freq, high_freq], btype="band", fs=sampling_rate, output="sos")
        sos = sos.astype(np.float64)
        self.num_sections = sos.shape[0]

        b, a = sos[:, :3], sos[:, 3:]
        a0 = a[:, 0]

        self.b0 = (b[:, 0] / a0).astype(np.float64)
        self.b1 = (b[:, 1] / a0).astype(np.float64)
        self.b2 = (b[:, 2] / a0).astype(np.float64)
        self.a1 = (a[:, 1] / a0).astype(np.float64)
        self.a2 = (a[:, 2] / a0).astype(np.float64)

    def create_state(self, num_channels: int) -> np.ndarray:
        return np.zeros((num_channels, self.num_sections, 2), dtype=np.float64)

    def filter(self, values: np.ndarray, state: np.ndarray) -> np.ndarray:
        x = np.asarray(values, dtype=np.float64)

        for sec in range(self.num_sections):
            b0, b1, b2 = self.b0[sec], self.b1[sec], self.b2[sec]
            a1, a2 = self.a1[sec], self.a2[sec]

            w1, w2 = state[:, sec, 0], state[:, sec, 1]

            w0 = x - a1 * w1 - a2 * w2
            y = b0 * w0 + b1 * w1 + b2 * w2

            state[:, sec, 1] = w1
            state[:, sec, 0] = w0

            x = y

        return y
