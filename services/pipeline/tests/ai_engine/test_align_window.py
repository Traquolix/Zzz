"""Tests for DTANInference.align_window.

Shape, determinism, and full-pipeline alignment are validated by the golden
snapshot tests. This file tests the mathematical identity property: zero
theta should produce an approximate identity transform. This uses a
constructed theta (no model inference on noise), so it's GPU-safe.
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


class TestAlignWindowIdentity:
    """Test that zero theta produces an approximate identity transform."""

    def test_zero_theta_approximates_identity(self, estimator):
        """With zero thetas, alignment should approximately preserve the input."""
        assert GOLDEN_INPUT.exists(), "Golden fixture missing. Run: make snapshot-confirm"
        data = np.load(GOLDEN_INPUT)
        data_window = data["data_window"]

        dtan: DTANInference = estimator._dtan
        space_split = dtan.split_channel_overlap(data_window)
        # Use just the first few windows to keep it fast
        space_split = space_split[:5]
        for i in range(space_split.shape[0]):
            space_split[i] = normalize_channel_energy(space_split[i])

        n_windows = space_split.shape[0]
        n_pairs = CHANNELS_PER_SECTION - 1
        theta_dim = dtan.T.get_theta_dim()
        align_idx = (CHANNELS_PER_SECTION - 1) // 2

        zero_thetas = torch.zeros(n_windows, n_pairs, theta_dim)
        aligned = dtan.align_window(space_split, zero_thetas, CHANNELS_PER_SECTION, align_idx)
        aligned_np = aligned.detach().cpu().numpy()

        np.testing.assert_allclose(aligned_np, space_split, atol=0.15, rtol=0.05)
