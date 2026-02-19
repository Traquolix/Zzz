"""
Self-Supervised Loss for DTAN Training (Thesis Eq. 2.21)
========================================================

Implements the loss function from Khacef's PhD thesis (2024COAZ5070), Section 2.5.3:

    L = L_reconstruction + λ_inner * L_inner + λ_inter * L_inter

Where (Thesis Eq. 2.21):
    L_reconstruction = 1/(Nc-1) * Σ_n ||x_n - W^{θ_{n-1}}(x_{n-1})||²
        Alignment loss: how well does warped channel n-1 match channel n?

    L_inner = 1/(Nc-1) * Σ_n ||θ_n||²_{Σ⁻¹_CPA}
        Inner regularizer: Mahalanobis distance with CPA covariance matrix
        Penalizes deformations based on CPAB basis structure

    L_inter = 1/(Nc-2) * Σ_n ||θ_{n-1} - θ_n||²_{Σ⁻¹_I}
        Inter-channel regularizer: smooths theta across adjacent channels
        Uses identity covariance (standard L2 norm)

The training is SELF-SUPERVISED: the data IS its own label. No external
annotations needed. The model learns the physics of signal propagation
between consecutive channels on a specific fiber.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import torch
import torch.nn as nn


def compute_cpa_covariance(cpab_basis: np.ndarray, length_scale: float = 0.1,
                           output_variance: float = 1.0) -> np.ndarray:
    """Compute the CPA covariance matrix in theta-space.

    This follows the thesis methodology: covariance between CPAB parameters
    is based on distance between cell centers, using a squared exponential kernel.

    Args:
        cpab_basis: [D, d] CPAB basis matrix where D is the full parameter space
                   and d is the reduced theta dimension
        length_scale: Controls how fast covariance decays with distance
        output_variance: Overall variance scale

    Returns:
        cov_theta: [d, d] covariance matrix in theta-space
    """
    D, d = cpab_basis.shape

    # For 1D CPAB with tessellation size n, we have n cells
    # Each cell has 2 parameters (affine transformation a*x + b)
    # Cell centers are at (i + 0.5) / n for i in range(n)
    n_cells = D // 2  # 2 params per cell in 1D

    # Compute cell centers
    cell_centers = np.array([(i + 0.5) / n_cells for i in range(n_cells)])

    # Compute distance matrix between cells
    dist = np.abs(cell_centers[:, None] - cell_centers[None, :])

    # Build covariance in D-space (full parameter space)
    # Block structure: each cell has 2 parameters
    cov_D = np.zeros((D, D))
    params_per_cell = 2

    for i in range(n_cells):
        for j in range(n_cells):
            # Squared exponential kernel
            cov_val = output_variance**2 * np.exp(-(dist[i, j]**2) / (2 * length_scale**2))
            # Fill 2x2 block for this cell pair
            for pi in range(params_per_cell):
                for pj in range(params_per_cell):
                    if pi == pj:  # Only diagonal within block (params within cell are independent)
                        cov_D[i * params_per_cell + pi, j * params_per_cell + pj] = cov_val

    # Transform to theta-space: Σ_θ = B^T * Σ_D * B
    B = cpab_basis
    cov_theta = B.T @ cov_D @ B

    # Add small diagonal for numerical stability
    cov_theta += 1e-6 * np.eye(d)

    return cov_theta


class DTANLoss(nn.Module):
    """Self-supervised loss for DTAN alignment training.

    Implements the full thesis loss function (Eq. 2.21) with Mahalanobis
    distance for the inner regularizer using the CPA covariance matrix.

    Args:
        lambda_inner: Weight for inner regularizer (Mahalanobis norm)
        lambda_inter: Weight for inter-channel regularizer (L2 smoothness)
        cpa_cov_inv: Optional precomputed inverse CPA covariance [d, d].
                     If None, falls back to standard L2 norm for inner loss.
        length_scale: Length scale for CPA covariance kernel (if computing)
        output_variance: Output variance for CPA covariance (if computing)
    """

    def __init__(
        self,
        lambda_inner: float = 1.0,
        lambda_inter: float = 1.0,
        cpa_cov_inv: Optional[torch.Tensor] = None,
        length_scale: float = 0.1,
        output_variance: float = 1.0,
    ):
        super().__init__()
        self.lambda_inner = lambda_inner
        self.lambda_inter = lambda_inter
        self.length_scale = length_scale
        self.output_variance = output_variance

        # Register inverse covariance as buffer (not a parameter)
        # Always register as buffer (even if None) to avoid attribute conflicts
        self.register_buffer('cpa_cov_inv', cpa_cov_inv)

    def set_cpa_covariance_from_basis(self, cpab_basis: np.ndarray):
        """Compute and set the CPA covariance from the CPAB basis matrix.

        Args:
            cpab_basis: [D, d] numpy array, the CPAB transformation basis
        """
        cov = compute_cpa_covariance(
            cpab_basis,
            self.length_scale,
            self.output_variance
        )
        # Compute inverse
        cov_inv = np.linalg.inv(cov)
        cov_inv_tensor = torch.from_numpy(cov_inv.astype(np.float32))

        # Update the buffer (it was registered in __init__)
        self.cpa_cov_inv = cov_inv_tensor

    def forward(
        self,
        x_input: torch.Tensor,
        x_aligned: torch.Tensor,
        thetas: torch.Tensor,
    ) -> dict:
        """Compute the self-supervised DTAN loss (Thesis Eq. 2.21).

        Args:
            x_input: Original input window [batch, Nch, signal_len]
                     The last channel (x_input[:, -1, :]) is the reference.
            x_aligned: DTAN-aligned output [batch, Nch-1, signal_len]
                       x_aligned[:, n, :] = W^{θ_n}(x_input[:, n, :])
                       This should approximate x_input[:, n+1, :].
            thetas: Transformation parameters [batch, Nch-1, theta_dim]
                    Per-channel deformation parameters.

        Returns:
            Dictionary with total loss and individual components.
        """
        batch_size, n_ch_out, signal_len = x_aligned.shape
        _, _, theta_dim = thetas.shape

        # ---------------------------------------------------------------
        # L_reconstruction: 1/(Nc-1) * Σ ||x_n - W^{θ_{n-1}}(x_{n-1})||²
        # x_aligned[:, n, :] should match x_input[:, n+1, :]
        # ---------------------------------------------------------------
        x_target = x_input[:, 1:, :]  # [batch, Nch-1, signal_len]

        # Per-channel MSE, then average over channels (thesis normalization)
        per_channel_mse = torch.mean((x_aligned - x_target) ** 2, dim=2)  # [batch, Nch-1]
        reconstruction_loss = torch.mean(per_channel_mse)  # Average over batch and channels

        # ---------------------------------------------------------------
        # L_inner: 1/(Nc-1) * Σ ||θ||²_{Σ⁻¹_CPA} (Mahalanobis norm)
        # = 1/(Nc-1) * Σ θ^T * Σ⁻¹_CPA * θ
        # ---------------------------------------------------------------
        if self.cpa_cov_inv is not None:
            # Mahalanobis distance: θ^T * Σ⁻¹ * θ
            # thetas: [batch, Nch-1, d] -> reshape for matmul
            thetas_flat = thetas.reshape(-1, theta_dim)  # [batch*(Nch-1), d]

            # Compute θ^T * Σ⁻¹ * θ for each theta vector
            # result[i] = thetas_flat[i] @ cpa_cov_inv @ thetas_flat[i]
            mahal = torch.sum(thetas_flat @ self.cpa_cov_inv * thetas_flat, dim=1)  # [batch*(Nch-1)]
            inner_loss = torch.mean(mahal)
        else:
            # Fallback to simple L2 norm if no covariance provided
            inner_loss = torch.mean(thetas ** 2)

        # ---------------------------------------------------------------
        # L_inter: 1/(Nc-2) * Σ ||θ_{n-1} - θ_n||² (L2 smoothness)
        # ---------------------------------------------------------------
        if thetas.shape[1] > 1:
            theta_diff = thetas[:, 1:, :] - thetas[:, :-1, :]  # [batch, Nch-2, d]
            inter_loss = torch.mean(theta_diff ** 2)
        else:
            inter_loss = torch.tensor(0.0, device=thetas.device)

        # Total loss (Thesis Eq. 2.21)
        total_loss = (
            reconstruction_loss
            + self.lambda_inner * inner_loss
            + self.lambda_inter * inter_loss
        )

        return {
            "total": total_loss,
            "reconstruction": reconstruction_loss,
            "inner": inner_loss,
            "inter": inter_loss,
        }


class DTANLossWeighted(DTANLoss):
    """DTANLoss variant with per-channel weighting.

    Channels closer to the reference (last channel) get higher weight
    in the reconstruction loss, since their alignment is more reliable.

    Args:
        lambda_inner: Weight for inner regularizer
        lambda_inter: Weight for inter-channel regularizer
        cpa_cov_inv: Optional precomputed inverse CPA covariance [d, d]
        channel_weight_decay: Exponential decay for channel weights (0 = uniform)
    """

    def __init__(
        self,
        lambda_inner: float = 1.0,
        lambda_inter: float = 1.0,
        cpa_cov_inv: Optional[torch.Tensor] = None,
        channel_weight_decay: float = 0.1,
    ):
        super().__init__(lambda_inner, lambda_inter, cpa_cov_inv)
        self.channel_weight_decay = channel_weight_decay

    def forward(
        self,
        x_input: torch.Tensor,
        x_aligned: torch.Tensor,
        thetas: torch.Tensor,
    ) -> dict:
        batch_size, n_ch_out, signal_len = x_aligned.shape
        _, _, theta_dim = thetas.shape

        # Channel weights: higher weight for channels closer to reference
        weights = torch.exp(
            self.channel_weight_decay * torch.arange(n_ch_out, device=x_aligned.device, dtype=torch.float32)
        )
        weights = weights / weights.sum()  # normalize

        # Reconstruction loss with channel weighting
        x_target = x_input[:, 1:, :]
        per_channel_loss = torch.mean((x_aligned - x_target) ** 2, dim=(0, 2))  # [Nch-1]
        reconstruction_loss = (per_channel_loss * weights).sum()

        # Inner regularizer with Mahalanobis distance (if covariance provided)
        if self.cpa_cov_inv is not None:
            thetas_flat = thetas.reshape(-1, theta_dim)
            mahal = torch.sum(thetas_flat @ self.cpa_cov_inv * thetas_flat, dim=1)
            inner_loss = torch.mean(mahal)
        else:
            inner_loss = torch.mean(thetas ** 2)

        # Inter-channel smoothness
        if thetas.shape[1] > 1:
            theta_diff = thetas[:, 1:, :] - thetas[:, :-1, :]
            inter_loss = torch.mean(theta_diff ** 2)
        else:
            inter_loss = torch.tensor(0.0, device=thetas.device)

        total_loss = (
            reconstruction_loss
            + self.lambda_inner * inner_loss
            + self.lambda_inter * inter_loss
        )

        return {
            "total": total_loss,
            "reconstruction": reconstruction_loss,
            "inner": inner_loss,
            "inter": inter_loss,
        }
