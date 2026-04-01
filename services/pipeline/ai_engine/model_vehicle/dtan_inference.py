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

        Args:
            data_window: Input data (num_windows, Nch, time_samples)

        Returns:
            Tuple of (thetas, grid_t)
        """
        batch_size = self.model_args.batch_size
        device = self.model_args.device_name

        data_tensor = torch.from_numpy(data_window).float().to(device, non_blocking=True)

        with torch.no_grad():
            torch.backends.cudnn.benchmark = True

            test_thetas_list = []
            test_grid_t_list = []

            for start in range(0, len(data_tensor), batch_size):
                batch = data_tensor[start : start + batch_size]

                _, thetas, grid_t = self.model(batch, return_theta_and_transformed_grid=True)

                test_thetas_list.append(thetas.detach().cpu().numpy())
                test_grid_t_list.append(grid_t.detach().cpu().numpy())

        thetas = np.vstack(test_thetas_list)
        thetas = torch.from_numpy(thetas)
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

            output = self.T.transform_data(output, thetas_flatten, outsize=(self.model_args.signal_length,))

            end_to_ref = min(end_to_ref + 1, Nch - 1)
            first_to_ref = max(first_to_ref - 1, 0)

        return output.reshape(dim)

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
