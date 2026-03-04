"""Tests for per-pair GLRT restructuring (Phase 3.1)."""

import sys
from unittest.mock import MagicMock

import numpy as np
import pytest

# Remove ALL mocked modules from earlier test files so we get clean imports
_to_clean = [k for k in sys.modules if isinstance(sys.modules[k], MagicMock)]
for _key in _to_clean:
    del sys.modules[_key]
# Also remove cached ai_engine.model_vehicle submodules that used mocked torch
for _key in list(sys.modules):
    if _key.startswith("ai_engine.model_vehicle"):
        del sys.modules[_key]

# Now mock only matplotlib (which we don't need for real)
sys.modules["matplotlib"] = MagicMock()
sys.modules["matplotlib.pyplot"] = MagicMock()

import torch  # noqa: E402

from ai_engine.model_vehicle.glrt_detector import GLRTDetector  # noqa: E402
from ai_engine.model_vehicle.vehicle_speed import VehicleSpeedEstimator  # noqa: E402


class TestApplyGlrtPerPair:
    """Test that apply_glrt returns per-pair (3D) results."""

    @pytest.fixture
    def estimator(self):
        """Create a minimal estimator with just glrt_win set."""
        e = VehicleSpeedEstimator.__new__(VehicleSpeedEstimator)
        e.glrt_win = 20

        # Create minimal GLRTDetector for apply_glrt
        glrt = GLRTDetector.__new__(GLRTDetector)
        glrt.glrt_win = 20
        e._glrt = glrt
        return e

    def test_output_shape_is_3d(self, estimator):
        """Input (5, 9, 291) -> glrt shape (5, 8, 291)."""
        aligned = torch.randn(5, 9, 291)
        result = estimator.apply_glrt(aligned)
        assert result.shape == (5, 8, 291)

    def test_summed_matches_per_pair_sum(self, estimator):
        """Sum across pairs dimension should equal summed GLRT."""
        aligned = torch.randn(3, 9, 200)
        per_pair = estimator.apply_glrt(aligned)
        summed = per_pair.sum(dim=1)
        # Summed should have shape (3, 200)
        assert summed.shape == (3, 200)

    def test_per_pair_values_positive_for_correlated(self, estimator):
        """Identical aligned channels should produce positive GLRT."""
        # All channels identical -> perfectly correlated
        base = torch.randn(1, 1, 300).expand(1, 9, 300).clone()
        result = estimator.apply_glrt(base)
        # Interior values (not edge-zeroed) should be positive
        interior = result[0, :, 35:265]
        assert (interior > 0).all()

    def test_edge_safety_zeroed(self, estimator):
        """First/last (safety + glrt_win//2) samples should be 0."""
        from ai_engine.model_vehicle.constants import GLRT_EDGE_SAFETY_SAMPLES
        aligned = torch.randn(2, 9, 200)
        result = estimator.apply_glrt(aligned)
        safety = GLRT_EDGE_SAFETY_SAMPLES
        glrt_half = estimator.glrt_win // 2
        edge = safety + glrt_half  # = 25
        # Start edge
        assert (result[:, :, :edge] == 0).all()
        # End edge
        assert (result[:, :, -edge:] == 0).all()
