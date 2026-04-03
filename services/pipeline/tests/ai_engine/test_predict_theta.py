"""Tests for DTANInference.predict_theta.

Validates the DTAN model forward pass: output shapes, determinism,
bounded outputs, and that batching produces the same result as
single-sample inference.

Speed computation (comp_speed) is tested in test_speed_formula.py.
"""

from __future__ import annotations

import numpy as np
import pytest
import torch

from ai_engine.model_vehicle.dtan_inference import DTANInference
from ai_engine.model_vehicle.utils import normalize_channel_energy
from tests.ai_engine.conftest import CHANNELS_PER_SECTION, SAMPLES_PER_WINDOW


class TestPredictTheta:
    """Tests for the DTAN model forward pass."""

    @pytest.fixture
    def dtan(self, estimator) -> DTANInference:
        return estimator._dtan

    @pytest.fixture
    def prepared_windows(self, dtan, synthetic_section_data) -> np.ndarray:
        """Spatial windows with energy normalization applied (ready for inference)."""
        space_split = dtan.split_channel_overlap(synthetic_section_data)
        for i in range(space_split.shape[0]):
            space_split[i] = normalize_channel_energy(space_split[i])
        return space_split

    def test_output_shapes(self, dtan, prepared_windows):
        """thetas and grid_t must have correct shapes."""
        thetas, grid_t = dtan.predict_theta(prepared_windows)
        n_windows = prepared_windows.shape[0]
        n_pairs = CHANNELS_PER_SECTION - 1

        assert thetas.shape[0] == n_windows
        assert thetas.shape[1] == n_pairs
        assert grid_t.shape == (n_windows, n_pairs, SAMPLES_PER_WINDOW)

    def test_deterministic(self, dtan, prepared_windows):
        """Same input must produce identical output (with fixed seeds)."""
        torch.manual_seed(42)
        thetas1, grid_t1 = dtan.predict_theta(prepared_windows)

        torch.manual_seed(42)
        thetas2, grid_t2 = dtan.predict_theta(prepared_windows)

        np.testing.assert_array_equal(thetas1.numpy(), thetas2.numpy())
        np.testing.assert_array_equal(grid_t1, grid_t2)

    def test_single_window_matches_batch(self, dtan, prepared_windows):
        """Single window inference must match batch result."""
        thetas_full, grid_t_full = dtan.predict_theta(prepared_windows)
        thetas_single, grid_t_single = dtan.predict_theta(prepared_windows[:1])

        assert thetas_single.shape[0] == 1
        np.testing.assert_allclose(
            thetas_single.numpy(), thetas_full[:1].numpy(), rtol=1e-5, atol=1e-6
        )
        np.testing.assert_allclose(grid_t_single, grid_t_full[:1], rtol=1e-5, atol=1e-6)

    def test_grid_t_bounded(self, dtan, prepared_windows):
        """For random noise, grid_t should be within a reasonable range."""
        _, grid_t = dtan.predict_theta(prepared_windows)
        assert grid_t.min() >= -0.5, f"grid_t min {grid_t.min()} too negative"
        assert grid_t.max() <= 1.5, f"grid_t max {grid_t.max()} too large"

    def test_thetas_bounded(self, dtan, prepared_windows):
        """Theta values should be bounded (Tanh output layer)."""
        thetas, _ = dtan.predict_theta(prepared_windows)
        assert thetas.abs().max() <= 1.0 + 1e-6, (
            f"Thetas out of tanh range: max abs = {thetas.abs().max()}"
        )
