"""Tests for DTANInference.predict_theta.

Model forward pass shape/bounds/determinism are validated by the golden
snapshot tests on real data. This file tests the batch-consistency property:
single-window inference must match the corresponding slice from batch inference.

Speed computation is tested in test_speed_formula.py.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ai_engine.model_vehicle.dtan_inference import DTANInference
from ai_engine.model_vehicle.utils import normalize_channel_energy

FIXTURE_DIR = Path(__file__).parent / "fixtures"
GOLDEN_INPUT = FIXTURE_DIR / "golden_input.npz"


class TestPredictThetaBatchConsistency:
    """Single-window inference must match batch result."""

    def _prepare_windows(self, dtan, data_window):
        space_split = dtan.split_channel_overlap(data_window)
        for i in range(space_split.shape[0]):
            space_split[i] = normalize_channel_energy(space_split[i])
        return space_split

    def test_single_window_matches_batch(self, estimator):
        """First window from batch must equal single-window inference."""
        assert GOLDEN_INPUT.exists(), "Golden fixture missing. Run: make snapshot-confirm"
        data = np.load(GOLDEN_INPUT)
        data_window = data["data_window"]

        dtan: DTANInference = estimator._dtan
        prepared = self._prepare_windows(dtan, data_window)

        thetas_full, grid_t_full = dtan.predict_theta(prepared)
        thetas_single, grid_t_single = dtan.predict_theta(prepared[:1])

        assert thetas_single.shape[0] == 1
        np.testing.assert_allclose(
            thetas_single.numpy(), thetas_full[:1].numpy(), rtol=1e-5, atol=1e-6
        )
        np.testing.assert_allclose(grid_t_single, grid_t_full[:1], rtol=1e-5, atol=1e-6)
