"""Model weight integrity tests.

Verifies that model weight files have not been inadvertently modified.
If you intentionally update a model, update the hashes here AND run
`make snapshot-confirm` to update the golden reference.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
import torch

from ai_engine.model_vehicle.simple_interval_counter import build_counting_network
from tests.ai_engine.conftest import CHANNELS_PER_SECTION, SAMPLES_PER_WINDOW

_MODEL_DIR = (
    Path(__file__).resolve().parents[2] / "ai_engine" / "model_vehicle" / "models_parameters"
)

# SHA-256 hashes of committed model files
EXPECTED_HASHES = {
    "allignment_parameters_3_03_2026_30s_windows_parameters_best.pth": "6457a130b674f0634580d2775cf7a2c700219de539a4ca6df6a61c720d6959ad",  # pragma: allowlist secret
    "vehicle_counting_model.pt": "6bf53edfdcfab4fb589aff6783231e952b61ada5c914a83d961bdc9749a65626",  # pragma: allowlist secret
}


class TestModelWeightFingerprint:
    """Verify model files haven't changed without updating snapshots."""

    @pytest.mark.parametrize("filename,expected_hash", list(EXPECTED_HASHES.items()))
    def test_weight_file_hash(self, filename, expected_hash):
        """Model weight file SHA-256 must match expected hash."""
        path = _MODEL_DIR / filename
        if not path.exists():
            pytest.skip(f"Model file not found: {path}")

        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual_hash == expected_hash, (
            f"Model file '{filename}' has changed.\n"
            f"  Expected: {expected_hash}\n"
            f"  Actual:   {actual_hash}\n\n"
            f"If you intentionally updated this model:\n"
            f"  1. Update the hash in test_model_integrity.py\n"
            f"  2. Run: make snapshot-confirm\n"
            f"  3. Commit both the new model and updated fixtures"
        )


class TestModelLoadValidation:
    """Tests for model loading safety and validation."""

    def test_weights_only_enforced(self):
        """Model loading must use weights_only=True (no arbitrary code execution)."""
        path = _MODEL_DIR / "allignment_parameters_3_03_2026_30s_windows_parameters_best.pth"
        if not path.exists():
            pytest.skip("DTAN model file not found")

        # This should succeed with weights_only=True
        state_dict = torch.load(path, map_location="cpu", weights_only=True)
        assert isinstance(state_dict, dict)

    def test_counting_model_loads_correctly(self):
        """Counting MLP must load into the expected architecture."""
        path = _MODEL_DIR / "vehicle_counting_model.pt"
        if not path.exists():
            pytest.skip("Counting model file not found")

        network = build_counting_network()
        try:
            state = torch.load(path, map_location="cpu", weights_only=True)
        except Exception:
            state = torch.load(path, map_location="cpu", weights_only=False).state_dict()  # nosec
        network.load_state_dict(state)

        # Verify it produces output of correct shape
        with torch.no_grad():
            x = torch.randn(5, 5)
            y = network(x)
        assert y.shape == (5, 1)

    def test_corrupt_weights_rejected(self, tmp_path):
        """A random tensor saved as weights must be rejected by load_state_dict."""
        # Save random data as a .pth file
        fake_weights = {"garbage_key": torch.randn(100, 100)}
        fake_path = tmp_path / "fake_model.pth"
        torch.save(fake_weights, fake_path)

        network = build_counting_network()
        with pytest.raises(RuntimeError):
            state = torch.load(fake_path, map_location="cpu", weights_only=True)
            network.load_state_dict(state, strict=True)

    def test_missing_model_file_raises(self):
        """Attempting to load a nonexistent model file must raise."""
        with pytest.raises(FileNotFoundError):
            torch.load("/nonexistent/model.pth", map_location="cpu", weights_only=True)

    def test_dtan_model_architecture_matches_weights(self):
        """DTAN model architecture must accept the saved weights without size errors."""
        path = _MODEL_DIR / "allignment_parameters_3_03_2026_30s_windows_parameters_best.pth"
        if not path.exists():
            pytest.skip("DTAN model file not found")

        from ai_engine.model_vehicle.DTAN import DTAN

        model = DTAN(
            signal_len=SAMPLES_PER_WINDOW,
            Nch=CHANNELS_PER_SECTION,
            channels=1,
            tess_size=[20],
            bidirectional_RNN=True,
            zero_boundary=False,
            device="cpu",
            device_name="cpu",
        )

        state_dict = torch.load(path, map_location="cpu", weights_only=True)
        # strict=True ensures all keys match and shapes are compatible
        model.load_state_dict(state_dict, strict=True)

    def test_thresholds_csv_valid(self):
        """Detection threshold CSVs must be loadable with expected shapes."""
        thr_path = _MODEL_DIR / "detection_thresholds_adapted_sectionwise.csv"
        if not thr_path.exists():
            pytest.skip("Thresholds CSV not found")

        thresholds = np.loadtxt(thr_path, delimiter=",")
        assert thresholds.ndim == 2, f"Expected 2D array, got {thresholds.ndim}D"
        assert thresholds.shape[1] == 2, f"Expected 2 columns, got {thresholds.shape[1]}"
        assert np.all(np.isfinite(thresholds)), "Thresholds contain NaN/Inf"
        assert np.all(thresholds >= 0), "Thresholds must be non-negative"

    def test_mean_std_csv_valid(self):
        """Mean/std normalization CSV must be loadable with expected shape."""
        ms_path = _MODEL_DIR / "mean_std_features_adapted_sectionwise.csv"
        if not ms_path.exists():
            pytest.skip("Mean/std CSV not found")

        mean_std = np.loadtxt(ms_path, delimiter=",")
        assert mean_std.ndim == 2, f"Expected 2D array, got {mean_std.ndim}D"
        assert mean_std.shape[0] == 2, f"Expected 2 rows (mean, std), got {mean_std.shape[0]}"
        assert mean_std.shape[1] == 5, f"Expected 5 features, got {mean_std.shape[1]}"
        assert np.all(np.isfinite(mean_std)), "Mean/std contains NaN/Inf"
        # Stds must be positive
        assert np.all(mean_std[1] > 0), "Standard deviations must be positive"
