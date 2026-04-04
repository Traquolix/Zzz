"""DTAN model inference: forward pass, alignment, and speed computation.

Handles the core DTAN pipeline steps:
1. split_channel_overlap -> spatial windows
2. per-window energy normalization
3. predict_theta -> DTAN forward pass
4. align_window / align_window_shift -> aligned channels
5. comp_speed -> absolute speeds from grid_t
"""

from __future__ import annotations

import numpy as np
import torch

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
        C, T = x.shape
        step = self.Nch - self.overlap_space

        if C < self.Nch:
            return np.empty((0, self.Nch, T), dtype=x.dtype)

        max_complete_windows = (C - self.Nch) // step + 1
        usable_channels = min(C, (max_complete_windows - 1) * step + self.Nch)
        x = x[:usable_channels, :]

        # Sliding window view: strided view over channel axis
        from numpy.lib.stride_tricks import sliding_window_view

        windows = sliding_window_view(x, self.Nch, axis=0)  # (C-Nch+1, T, Nch)
        windows = windows[::step]  # subsample by step
        # copy needed: sliding_window_view returns a read-only view
        return windows.transpose(0, 2, 1).copy()  # (num_windows, Nch, T)

    def predict_theta(self, data_window: np.ndarray) -> tuple:
        """Predict transformation parameters via the CNN+RNN+FC head.

        The grid transform is computed separately using the cached alignment
        grid, skipping the redundant CPAB integration + interpolation that
        the old full-model forward pass performed.

        Args:
            data_window: Input data (num_windows, Nch, time_samples)

        Returns:
            Tuple of (thetas, grid_t)
        """
        batch_size = self.model_args.batch_size
        device = self.model_args.device_name
        n_pairs = self.Nch - 1

        data_tensor = torch.from_numpy(data_window).float().to(device, non_blocking=True)

        thetas_list = []
        grid_t_list = []

        with torch.no_grad():
            for start in range(0, len(data_tensor), batch_size):
                batch = data_tensor[start : start + batch_size]
                thetas = self.model.predict_thetas(batch)

                # Compute grid_t for this batch using cached grid
                b = thetas.shape[0]
                thetas_flat = thetas.reshape(b * n_pairs, -1)
                grid_t_flat = self.T.transform_grid(self._align_grid, thetas_flat)
                grid_t = grid_t_flat.squeeze(1).reshape(b, n_pairs, self.window_size)

                thetas_list.append(thetas.detach().cpu())
                grid_t_list.append(grid_t.detach().cpu().numpy())

        return torch.cat(thetas_list, dim=0), np.vstack(grid_t_list)

    def align_window(
        self,
        space_split: np.ndarray,
        thetas_in: torch.Tensor,
        Nch: int,
        align_channel_idx: int,
    ) -> torch.Tensor:
        """Align data window using iterative CPAB transformation.

        Iteratively warps channels outward from the reference channel using
        CPAB ODE integration. Called with Nch=self.Nch for signal alignment
        and Nch=self.Nch-1 for speed field alignment.

        Args:
            space_split: Input data (num_windows, Nch, time_samples)
            thetas_in: CPAB transformation parameters
            Nch: Number of channels in this tensor (may differ from self.Nch)
            align_channel_idx: Reference channel index

        Returns:
            Aligned data tensor on GPU
        """
        device = self.model_args.device_name
        dim = space_split.shape
        N_theta = thetas_in.shape[2]

        thetas = thetas_in.to(device, dtype=torch.float32)
        output = torch.from_numpy(space_split).to(device, dtype=torch.float32)
        output = torch.flatten(output, start_dim=0, end_dim=1).unsqueeze(dim=1)

        first_to_ref = align_channel_idx
        end_to_ref = align_channel_idx

        for i in range(max(first_to_ref, Nch - end_to_ref - 1)):
            nbr_zeros = end_to_ref - first_to_ref + 1
            zeros = torch.zeros((dim[0], nbr_zeros, N_theta), device=device)

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
    ) -> torch.Tensor:
        """Align channels using constant time-shift derived from grid_t.

        Computes the median per-pair time displacement from the deformed grid
        and applies a vectorized linear sub-sample shift. Much faster than
        CPAB alignment with >99% GLRT correlation.

        Args:
            space_split: Input data (num_windows, Nch, time_samples)
            grid_t: Deformed grid from predict_theta (num_windows, Nch-1, time_samples)
            align_channel_idx: Reference channel index

        Returns:
            Aligned data tensor (same shape as input)
        """
        n_windows, Nch, T = space_split.shape
        device = self.model_args.device_name

        # Per-pair median shift in samples: (n_windows, n_pairs)
        delta = (grid_t - self.uniform_grid) * self.window_size
        median_shift = np.median(delta, axis=2)

        # Cumulative shift per channel relative to align_channel_idx.
        # pair i connects channel i to channel i+1, so cumsum gives
        # the shift from channel 0 to channel k. We offset by the
        # reference channel's cumulative value so it becomes zero there.
        cumshift = np.zeros((n_windows, Nch), dtype=np.float32)
        cumshift[:, 1:] = np.cumsum(median_shift, axis=1)
        ref_shift = cumshift[:, align_channel_idx : align_channel_idx + 1]
        cumshift = -(cumshift - ref_shift)  # shift *towards* reference

        # Move everything to GPU in one shot
        sp = torch.from_numpy(space_split).float().to(device, non_blocking=True)
        shifts = torch.from_numpy(cumshift).to(device, non_blocking=True)

        # Build shifted index grid: (n_windows, Nch, T)
        base = torch.arange(T, dtype=torch.float32, device=device)
        shifted = base + shifts.unsqueeze(2)  # broadcast (W,C,1) + (W,C,T)
        shifted = shifted.clamp(0, T - 1)

        # Linear interpolation — single batched gather, no Python loop
        idx0 = shifted.long().clamp(0, T - 2)
        idx1 = idx0 + 1
        frac = shifted - idx0.float()

        v0 = torch.gather(sp, 2, idx0)
        v1 = torch.gather(sp, 2, idx1)
        return v0 + frac * (v1 - v0)

    def comp_speed(self, grid_t: np.ndarray) -> np.ndarray:
        """Calculate vehicle speeds from transformed grid data.

        speed = abs(3.6 * fs * gauge / delta)

        Args:
            grid_t: Transformed grid data

        Returns:
            Absolute speed values for each sensor and time point
        """
        delta = grid_t - self.uniform_grid
        delta *= self.window_size
        delta += self.eps

        return np.abs(self.speed_scaling / delta)
