"""Tests for DTANInference alignment methods.

Shape, determinism, and full-pipeline alignment are validated by the golden
snapshot tests. This file tests:
1. Identity property: zero theta / uniform grid → approximate identity
2. Cross-validation: align_window_shift matches align_window (CPAB) on real data
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from ai_engine.model_vehicle.dtan_inference import DTANInference
from ai_engine.model_vehicle.utils import normalize_channel_energy
from tests.ai_engine.conftest import CHANNELS_PER_SECTION

FIXTURE_DIR = Path(__file__).parent / "fixtures"
GOLDEN_INPUT = FIXTURE_DIR / "golden_input.npz"


def _prepare_space_split(dtan: DTANInference, n_windows: int = 5) -> np.ndarray:
    """Load golden data, split, normalize, and return first n_windows."""
    assert GOLDEN_INPUT.exists(), "Golden fixture missing. Run: make snapshot-confirm"
    data = np.load(GOLDEN_INPUT)
    space_split = dtan.split_channel_overlap(data["data_window"])
    space_split = space_split[:n_windows]
    for i in range(space_split.shape[0]):
        space_split[i] = normalize_channel_energy(space_split[i])
    return space_split


class TestAlignWindowIdentity:
    """Test that zero theta produces an approximate identity transform."""

    def test_zero_theta_approximates_identity(self, estimator):
        """With zero thetas, alignment should approximately preserve the input."""
        dtan: DTANInference = estimator._dtan
        space_split = _prepare_space_split(dtan)

        n_windows = space_split.shape[0]
        n_pairs = CHANNELS_PER_SECTION - 1
        theta_dim = dtan.T.get_theta_dim()
        align_idx = (CHANNELS_PER_SECTION - 1) // 2

        zero_thetas = torch.zeros(n_windows, n_pairs, theta_dim)
        aligned = dtan.align_window(space_split, zero_thetas, CHANNELS_PER_SECTION, align_idx)
        aligned_np = aligned.detach().cpu().numpy()

        np.testing.assert_allclose(aligned_np, space_split, atol=0.15, rtol=0.05)


class TestAlignWindowShift:
    """Tests for the shift alignment method."""

    def test_uniform_grid_is_identity(self, estimator):
        """With a uniform grid (no deformation), shift alignment preserves input."""
        dtan: DTANInference = estimator._dtan
        space_split = _prepare_space_split(dtan)
        align_idx = (CHANNELS_PER_SECTION - 1) // 2

        # Uniform grid = no shift — broadcast to (n_windows, n_pairs, T)
        n_windows = space_split.shape[0]
        n_pairs = CHANNELS_PER_SECTION - 1
        grid_t = np.broadcast_to(dtan.uniform_grid, (n_windows, n_pairs, dtan.window_size)).copy()

        aligned = dtan.align_window_shift(space_split, grid_t, align_idx)
        aligned_np = aligned.detach().cpu().numpy()

        np.testing.assert_allclose(aligned_np, space_split, atol=1e-5, rtol=1e-5)

    def test_output_on_model_device(self, estimator):
        """Shift alignment output must be on the model's device (GPU if available)."""
        dtan: DTANInference = estimator._dtan
        space_split = _prepare_space_split(dtan, n_windows=2)
        align_idx = (CHANNELS_PER_SECTION - 1) // 2

        n_windows = space_split.shape[0]
        n_pairs = CHANNELS_PER_SECTION - 1
        grid_t = np.broadcast_to(dtan.uniform_grid, (n_windows, n_pairs, dtan.window_size)).copy()

        aligned = dtan.align_window_shift(space_split, grid_t, align_idx)
        expected_device = torch.device(dtan.model_args.device_name)
        assert aligned.device.type == expected_device.type

    def test_output_shape_matches_input(self, estimator):
        """Shift alignment output shape must match input shape."""
        dtan: DTANInference = estimator._dtan
        space_split = _prepare_space_split(dtan)
        align_idx = (CHANNELS_PER_SECTION - 1) // 2

        _thetas, grid_t = dtan.predict_theta(space_split)
        aligned = dtan.align_window_shift(space_split, grid_t, align_idx)

        assert aligned.shape == space_split.shape

    def test_shift_correlates_with_cpab(self, estimator):
        """Shift alignment should produce similar GLRT to CPAB on real data."""
        dtan: DTANInference = estimator._dtan
        space_split = _prepare_space_split(dtan, n_windows=10)
        align_idx = (CHANNELS_PER_SECTION - 1) // 2

        thetas, grid_t = dtan.predict_theta(space_split)

        cpab_aligned = dtan.align_window(space_split, thetas, CHANNELS_PER_SECTION, align_idx)
        shift_aligned = dtan.align_window_shift(space_split, grid_t, align_idx)

        # Compare per-pair correlation (adjacent channel products summed over time).
        # This is what GLRT uses — the detection-relevant signal.
        cpab_np = cpab_aligned.detach().cpu().numpy()
        shift_np = shift_aligned.detach().cpu().numpy()

        cpab_corr = np.sum(cpab_np[:, :-1, :] * cpab_np[:, 1:, :], axis=2)
        shift_corr = np.sum(shift_np[:, :-1, :] * shift_np[:, 1:, :], axis=2)

        # Pearson correlation between the two GLRT-like signals
        corr = np.corrcoef(cpab_corr.ravel(), shift_corr.ravel())[0, 1]
        assert corr > 0.95, f"Shift vs CPAB GLRT correlation too low: {corr:.4f}"
