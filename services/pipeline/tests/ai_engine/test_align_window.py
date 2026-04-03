"""Tests for DTANInference.align_window.

Validates the CPAB-based temporal alignment: shapes, determinism,
identity transform behavior, and consistency with predict_theta output.
"""

from __future__ import annotations

import numpy as np
import pytest
import torch

from ai_engine.model_vehicle.dtan_inference import DTANInference
from ai_engine.model_vehicle.utils import normalize_channel_energy
from tests.ai_engine.conftest import CHANNELS_PER_SECTION, SAMPLES_PER_WINDOW


class TestAlignWindow:
    """Tests for CPAB alignment."""

    @pytest.fixture
    def dtan(self, estimator) -> DTANInference:
        return estimator._dtan

    @pytest.fixture
    def inference_state(self, dtan, synthetic_section_data):
        """Prepared space_split, thetas, grid_t from full forward pass."""
        space_split = dtan.split_channel_overlap(synthetic_section_data)
        for i in range(space_split.shape[0]):
            space_split[i] = normalize_channel_energy(space_split[i])
        thetas, grid_t = dtan.predict_theta(space_split)
        return space_split, thetas, grid_t

    def test_output_shape(self, dtan, inference_state):
        """Aligned output must have same shape as input."""
        space_split, thetas, _ = inference_state
        align_idx = (CHANNELS_PER_SECTION - 1) // 2
        aligned = dtan.align_window(space_split, thetas, CHANNELS_PER_SECTION, align_idx)
        assert aligned.shape == space_split.shape

    def test_deterministic(self, dtan, inference_state):
        """Same input must produce identical output."""
        space_split, thetas, _ = inference_state
        align_idx = (CHANNELS_PER_SECTION - 1) // 2

        a1 = dtan.align_window(space_split, thetas, CHANNELS_PER_SECTION, align_idx)
        a2 = dtan.align_window(space_split, thetas, CHANNELS_PER_SECTION, align_idx)

        torch.testing.assert_close(a1, a2)

    def test_speed_alignment_shape(self, dtan, inference_state):
        """Speed alignment (Nch-1 pairs) must produce correct shape."""
        space_split, thetas, grid_t = inference_state
        align_idx = (CHANNELS_PER_SECTION - 1) // 2

        all_speed = dtan.comp_speed(grid_t)
        aligned_speed = dtan.align_window(
            all_speed, thetas[:, :-1, :], CHANNELS_PER_SECTION - 1, align_idx
        )

        n_windows = space_split.shape[0]
        n_pairs = CHANNELS_PER_SECTION - 1
        assert aligned_speed.shape == (n_windows, n_pairs, SAMPLES_PER_WINDOW)

    def test_zero_theta_approximates_identity(self, dtan, inference_state):
        """With near-zero thetas, alignment should approximately preserve the input."""
        space_split, _, _ = inference_state
        n_windows = space_split.shape[0]
        n_pairs = CHANNELS_PER_SECTION - 1
        theta_dim = dtan.T.get_theta_dim()
        align_idx = (CHANNELS_PER_SECTION - 1) // 2

        zero_thetas = torch.zeros(n_windows, n_pairs, theta_dim)
        aligned = dtan.align_window(space_split, zero_thetas, CHANNELS_PER_SECTION, align_idx)
        aligned_np = aligned.detach().cpu().numpy()

        np.testing.assert_allclose(aligned_np, space_split, atol=0.15, rtol=0.05)
