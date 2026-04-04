"""DTAN model inference: forward pass, alignment, and speed computation.

Handles the core DTAN pipeline steps:
1. split_channel_overlap -> spatial windows
2. per-window energy normalization
3. predict_theta -> DTAN forward pass
4. align_window -> aligned channels
5. comp_speed -> absolute speeds from grid_t
"""

from __future__ import annotations

import numpy as np

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

from .constants import DEFAULT_EPSILON, SPEED_CONVERSION_FACTOR


class DTANInference:
    """Encapsulates DTAN model forward pass, alignment, and speed computation."""

    def __init__(self, model_args, T, model, uniform_grid):
        self.model_args = model_args
        self.T = T
        self.model = model
        self.uniform_grid = uniform_grid

        self.Nch = model_args.Nch
        self.fs = model_args.fs
        self.gauge = model_args.gauge
        self.window_size = model_args.signal_length
        self.overlap_space = model_args.N_channels

        self.eps = DEFAULT_EPSILON
        self.speed_scaling = SPEED_CONVERSION_FACTOR * self.fs * self.gauge

        # Cache the alignment grid — uniform_meshgrid(signal_length) is called
        # on every transform_data inside align_window. It's always the same.
        self._align_grid = T.uniform_meshgrid((model_args.signal_length,))

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

    def predict_theta(self, data_window: np.ndarray) -> tuple:
        """Predicts transformation parameters from data.

        Uses only the CNN+RNN+FC head (no CPAB transform in the forward pass).
        The grid transform is computed separately using the cached alignment grid,
        eliminating a redundant CPAB integration + interpolation that the old path
        performed just to discard the interpolated output.

        Args:
            data_window: Input data (num_windows, Nch, time_samples)

        Returns:
            Tuple of (thetas, grid_t)
        """
        batch_size = self.model_args.batch_size
        device = self.model_args.device_name

        data_tensor = torch.from_numpy(data_window).float().to(device, non_blocking=True)

        n_pairs = self.Nch - 1

        with torch.no_grad():

            test_thetas_list = []
            test_grid_t_list = []

            for start in range(0, len(data_tensor), batch_size):
                batch = data_tensor[start : start + batch_size]
                thetas = self.model.predict_thetas(batch)

                # Compute grid_t for this batch using cached grid
                b = thetas.shape[0]
                thetas_flat = thetas.reshape(b * n_pairs, -1)
                grid_t_flat = self.T.transform_grid(self._align_grid, thetas_flat)
                grid_t = grid_t_flat.squeeze(1).reshape(b, n_pairs, self.window_size)

                test_thetas_list.append(thetas.detach().cpu())
                test_grid_t_list.append(grid_t.detach().cpu().numpy())

        thetas = torch.cat(test_thetas_list, dim=0)
        grid_t = np.vstack(test_grid_t_list)

        return thetas, grid_t

    def align_window(
        self,
        space_split: np.ndarray,
        thetas_in: "torch.Tensor",
        Nch: int,
        align_channel_idx: int,
    ) -> "torch.Tensor":
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

            grid_t = self.T.transform_grid(self._align_grid, thetas_flatten)
            output = self.T.interpolate(output, grid_t, (self.model_args.signal_length,))

            end_to_ref = min(end_to_ref + 1, Nch - 1)
            first_to_ref = max(first_to_ref - 1, 0)

        return output.reshape(dim)

    def align_window_shift(
        self,
        space_split: np.ndarray,
        grid_t: np.ndarray,
        align_channel_idx: int,
    ) -> "torch.Tensor":
        """Align channels using constant time-shift derived from grid_t.

        Instead of iterative CPAB ODE integration, computes the median
        per-pair time displacement from grid_t and applies a linear
        sub-sample shift to each channel. ~40x faster than CPAB alignment
        with 99.9% GLRT correlation on highway traffic data.

        Args:
            space_split: Input data (num_windows, Nch, time_samples)
            grid_t: Deformed grid from predict_theta (num_windows, Nch-1, time_samples)
            align_channel_idx: Reference channel index

        Returns:
            Aligned data tensor (same shape as input)
        """
        n_windows, Nch, T = space_split.shape

        # Compute per-pair median shift in samples from the grid deformation
        delta = (grid_t - self.uniform_grid) * self.window_size
        median_shift = np.median(delta, axis=2)  # (n_windows, n_pairs)

        sp_tensor = torch.from_numpy(space_split).float()
        aligned = torch.clone(sp_tensor)
        indices = torch.arange(T, dtype=torch.float32)

        for ch in range(Nch):
            if ch == align_channel_idx:
                continue

            # Cumulative shift from reference channel to this channel
            if ch < align_channel_idx:
                shifts = np.sum(median_shift[:, ch:align_channel_idx], axis=1)
            else:
                shifts = -np.sum(median_shift[:, align_channel_idx:ch], axis=1)

            # Vectorized sub-sample shift via linear interpolation
            shifts_t = torch.from_numpy(shifts).float()
            shifted_indices = indices.unsqueeze(0) + shifts_t.unsqueeze(1)
            shifted_indices = shifted_indices.clamp(0, T - 1)

            idx0 = shifted_indices.long().clamp(0, T - 2)
            idx1 = idx0 + 1
            frac = shifted_indices - idx0.float()

            signal = sp_tensor[:, ch, :]
            v0 = torch.gather(signal, 1, idx0)
            v1 = torch.gather(signal, 1, idx1)
            aligned[:, ch, :] = v0 * (1 - frac) + v1 * frac

        return aligned

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
