"""Tests for CalibrationData and CalibrationManager.

Validates variable threshold application, coupling correction, threshold lookup,
calibration loading/caching from .npz files, and graceful error handling.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pytest

_pipeline_root = Path(__file__).resolve().parents[2]
if str(_pipeline_root) not in sys.path:
    sys.path.insert(0, str(_pipeline_root))

from ai_engine.model_vehicle.calibration import CalibrationData, CalibrationManager  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_calibration_data(
    n_sections: int = 4,
    threshold_values: np.ndarray | None = None,
    correction_factors: np.ndarray | None = None,
    median_glrt: float | None = None,
) -> CalibrationData:
    """Build a CalibrationData with controllable fields."""
    if threshold_values is None:
        threshold_values = np.linspace(5.0, 20.0, n_sections)
    return CalibrationData(
        fiber_id="test_fiber",
        date="20260401",
        n_sections=n_sections,
        threshold_curve=threshold_values,
        baseline=np.ones(n_sections) * 2.0,
        noise_estimate=np.ones(n_sections) * 0.5,
        threshold_method="MAD",
        correction_factors=correction_factors,
        median_glrt=median_glrt,
    )


def _write_threshold_npz(path: Path, n_sections: int = 4) -> None:
    """Write a minimal valid threshold .npz calibration file."""
    np.savez(
        str(path),
        n_sections=np.array(n_sections),
        threshold_curve=np.linspace(5.0, 20.0, n_sections),
        baseline=np.ones(n_sections) * 2.0,
        noise_estimate=np.ones(n_sections) * 0.5,
        method=np.array("MAD"),
        date=np.array("20260401"),
    )


def _write_coupling_npz(path: Path, n_sections: int = 4) -> None:
    """Write a minimal valid coupling .npz calibration file."""
    np.savez(
        str(path),
        correction_factors=np.array([1.0, 1.2, 0.8, 1.1][:n_sections]),
        median_glrt=np.array(10.0),
    )


# ===========================================================================
# CalibrationData tests
# ===========================================================================


class TestApplyVariableThreshold:
    """Tests for CalibrationData.apply_variable_threshold."""

    def test_binary_mask_known_values(self):
        """Threshold produces correct binary mask for known inputs."""
        thresholds = np.array([10.0, 20.0, 30.0])
        cal = _make_calibration_data(n_sections=3, threshold_values=thresholds)

        # 3 sections, 5 samples each
        glrt = np.array(
            [
                [5.0, 10.0, 15.0, 9.99, 10.01],  # threshold = 10
                [19.0, 20.0, 21.0, 0.0, 100.0],  # threshold = 20
                [30.0, 29.99, 30.01, 50.0, 0.0],  # threshold = 30
            ]
        )

        mask = cal.apply_variable_threshold(glrt)

        expected = np.array(
            [
                [0.0, 1.0, 1.0, 0.0, 1.0],
                [0.0, 1.0, 1.0, 0.0, 1.0],
                [1.0, 0.0, 1.0, 1.0, 0.0],
            ]
        )
        np.testing.assert_array_equal(mask, expected)

    def test_output_dtype_is_float64(self):
        """Output mask must be float64 regardless of input dtype."""
        cal = _make_calibration_data(n_sections=2, threshold_values=np.array([1.0, 2.0]))
        glrt = np.array([[0.0, 5.0], [3.0, 0.0]], dtype=np.float32)
        mask = cal.apply_variable_threshold(glrt)
        assert mask.dtype == np.float64

    def test_output_shape_matches_input(self):
        """Output mask shape equals input GLRT shape."""
        cal = _make_calibration_data(n_sections=3)
        glrt = np.random.default_rng(0).random((3, 100))
        mask = cal.apply_variable_threshold(glrt)
        assert mask.shape == glrt.shape


class TestApplyCouplingCorrection:
    """Tests for CalibrationData.apply_coupling_correction."""

    def test_scales_glrt_correctly(self):
        """Correction factors multiply each section row independently."""
        factors = np.array([2.0, 0.5, 1.0])
        cal = _make_calibration_data(n_sections=3, correction_factors=factors)

        glrt = np.array(
            [
                [10.0, 20.0],
                [10.0, 20.0],
                [10.0, 20.0],
            ]
        )

        corrected = cal.apply_coupling_correction(glrt)

        expected = np.array(
            [
                [20.0, 40.0],
                [5.0, 10.0],
                [10.0, 20.0],
            ]
        )
        np.testing.assert_array_almost_equal(corrected, expected)

    def test_returns_original_when_no_factors(self):
        """When correction_factors is None, the original array is returned."""
        cal = _make_calibration_data(n_sections=3, correction_factors=None)
        glrt = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])

        result = cal.apply_coupling_correction(glrt)

        # Must be the exact same object, not a copy
        assert result is glrt


class TestGetThreshold:
    """Tests for CalibrationData.get_threshold."""

    def test_returns_correct_value(self):
        """Valid section index returns the matching threshold float."""
        thresholds = np.array([5.0, 10.0, 15.0, 20.0])
        cal = _make_calibration_data(n_sections=4, threshold_values=thresholds)

        assert cal.get_threshold(0) == 5.0
        assert cal.get_threshold(2) == 15.0
        assert cal.get_threshold(3) == 20.0

    def test_return_type_is_float(self):
        """get_threshold always returns a Python float."""
        cal = _make_calibration_data(n_sections=2, threshold_values=np.array([7.0, 8.0]))
        result = cal.get_threshold(0)
        assert isinstance(result, float)

    def test_raises_index_error_negative(self):
        """Negative section index raises IndexError."""
        cal = _make_calibration_data(n_sections=3)
        with pytest.raises(IndexError, match="Section -1 out of range"):
            cal.get_threshold(-1)

    def test_raises_index_error_out_of_range(self):
        """Section index == n_sections raises IndexError."""
        cal = _make_calibration_data(n_sections=3)
        with pytest.raises(IndexError, match="Section 3 out of range"):
            cal.get_threshold(3)


class TestBroadcasting:
    """Verify broadcasting works correctly for multi-section arrays."""

    def test_threshold_broadcasting_many_sections(self):
        """Variable threshold broadcasts across many sections and samples."""
        n_sections = 6
        n_samples = 50
        thresholds = np.arange(1.0, n_sections + 1.0)  # [1, 2, 3, 4, 5, 6]
        cal = _make_calibration_data(n_sections=n_sections, threshold_values=thresholds)

        rng = np.random.default_rng(42)
        glrt = rng.uniform(0.0, 10.0, size=(n_sections, n_samples))
        mask = cal.apply_variable_threshold(glrt)

        # Check each section individually against its own threshold
        for s in range(n_sections):
            expected_row = (glrt[s, :] >= thresholds[s]).astype(np.float64)
            np.testing.assert_array_equal(mask[s, :], expected_row)

    def test_coupling_broadcasting_many_sections(self):
        """Coupling correction broadcasts across many sections and samples."""
        n_sections = 5
        n_samples = 30
        factors = np.array([0.5, 1.0, 1.5, 2.0, 3.0])
        cal = _make_calibration_data(n_sections=n_sections, correction_factors=factors)

        glrt = np.ones((n_sections, n_samples)) * 10.0
        corrected = cal.apply_coupling_correction(glrt)

        for s in range(n_sections):
            np.testing.assert_array_almost_equal(
                corrected[s, :], np.full(n_samples, 10.0 * factors[s])
            )


# ===========================================================================
# CalibrationManager tests
# ===========================================================================


class TestLoadCalibrationMissingDir:
    """CalibrationManager.load_calibration with missing fiber directory."""

    def test_returns_none_for_missing_dir(self, tmp_path: Path):
        """Returns None when fiber directory does not exist."""
        manager = CalibrationManager(calibration_base_path=str(tmp_path))
        result = manager.load_calibration("nonexistent_fiber")
        assert result is None


class TestLoadCalibrationMissingThreshold:
    """CalibrationManager.load_calibration with missing threshold file."""

    def test_returns_none_for_missing_threshold(self, tmp_path: Path):
        """Returns None when directory exists but has no threshold file."""
        fiber_dir = tmp_path / "test_fiber"
        fiber_dir.mkdir()
        # Directory exists but is empty (no threshold .npz)
        manager = CalibrationManager(calibration_base_path=str(tmp_path))
        result = manager.load_calibration("test_fiber")
        assert result is None


class TestLoadCalibrationSuccess:
    """CalibrationManager.load_calibration with valid .npz files."""

    def test_loads_threshold_only(self, tmp_path: Path):
        """Loads successfully with only threshold file (no coupling)."""
        fiber_dir = tmp_path / "myfiber"
        fiber_dir.mkdir()
        _write_threshold_npz(fiber_dir / "myfiber_20260401_threshold.npz", n_sections=4)

        manager = CalibrationManager(calibration_base_path=str(tmp_path))
        result = manager.load_calibration("myfiber")

        assert result is not None
        assert result.fiber_id == "myfiber"
        assert result.n_sections == 4
        assert result.threshold_curve.shape == (4,)
        assert result.correction_factors is None
        assert result.median_glrt is None

    def test_loads_threshold_and_coupling(self, tmp_path: Path):
        """Loads both threshold and coupling calibration files."""
        fiber_dir = tmp_path / "myfiber"
        fiber_dir.mkdir()
        _write_threshold_npz(fiber_dir / "myfiber_20260401_threshold.npz", n_sections=4)
        _write_coupling_npz(fiber_dir / "myfiber_20260401_coupling.npz", n_sections=4)

        manager = CalibrationManager(calibration_base_path=str(tmp_path))
        result = manager.load_calibration("myfiber")

        assert result is not None
        assert result.correction_factors is not None
        assert result.correction_factors.shape == (4,)
        assert result.median_glrt == pytest.approx(10.0)

    def test_result_is_cached(self, tmp_path: Path):
        """Second call returns the cached object (same identity)."""
        fiber_dir = tmp_path / "myfiber"
        fiber_dir.mkdir()
        _write_threshold_npz(fiber_dir / "myfiber_20260401_threshold.npz")

        manager = CalibrationManager(calibration_base_path=str(tmp_path))
        first = manager.load_calibration("myfiber")
        second = manager.load_calibration("myfiber")

        assert first is second


class TestClearCache:
    """CalibrationManager.clear_cache."""

    def test_empties_cache(self, tmp_path: Path):
        """After clear_cache, the cache is empty and a fresh load is required."""
        fiber_dir = tmp_path / "myfiber"
        fiber_dir.mkdir()
        _write_threshold_npz(fiber_dir / "myfiber_20260401_threshold.npz")

        manager = CalibrationManager(calibration_base_path=str(tmp_path))
        manager.load_calibration("myfiber")
        assert "myfiber" in manager.get_cached_fiber_ids()

        manager.clear_cache()
        assert manager.get_cached_fiber_ids() == []


class TestFindLatestFile:
    """CalibrationManager._find_latest_file."""

    def test_returns_most_recent_by_mtime(self, tmp_path: Path):
        """Selects the file with the newest modification time."""
        fiber_dir = tmp_path / "myfiber"
        fiber_dir.mkdir()

        # Create two threshold files with different mtimes
        old_file = fiber_dir / "myfiber_20260301_threshold.npz"
        new_file = fiber_dir / "myfiber_20260401_threshold.npz"

        _write_threshold_npz(old_file)
        # Ensure distinct mtime (filesystem resolution can be coarse)
        time.sleep(0.05)
        _write_threshold_npz(new_file)

        manager = CalibrationManager(calibration_base_path=str(tmp_path))
        result = manager._find_latest_file(fiber_dir, "*_threshold.npz")

        assert result is not None
        assert result.name == "myfiber_20260401_threshold.npz"

    def test_returns_none_when_no_match(self, tmp_path: Path):
        """Returns None when no files match the pattern."""
        fiber_dir = tmp_path / "myfiber"
        fiber_dir.mkdir()

        manager = CalibrationManager(calibration_base_path=str(tmp_path))
        result = manager._find_latest_file(fiber_dir, "*_threshold.npz")
        assert result is None


class TestCorruptNpzHandling:
    """CalibrationManager graceful handling of corrupt .npz files."""

    def test_returns_none_for_corrupt_threshold(self, tmp_path: Path):
        """Corrupt threshold .npz returns None with logged error."""
        fiber_dir = tmp_path / "myfiber"
        fiber_dir.mkdir()

        corrupt_file = fiber_dir / "myfiber_20260401_threshold.npz"
        corrupt_file.write_bytes(b"this is not a valid npz file")

        manager = CalibrationManager(calibration_base_path=str(tmp_path))
        result = manager.load_calibration("myfiber")

        assert result is None

    def test_returns_none_for_missing_keys(self, tmp_path: Path):
        """Threshold .npz missing required keys returns None."""
        fiber_dir = tmp_path / "myfiber"
        fiber_dir.mkdir()

        # Write an npz with wrong keys
        bad_file = fiber_dir / "myfiber_20260401_threshold.npz"
        np.savez(str(bad_file), wrong_key=np.array([1, 2, 3]))

        manager = CalibrationManager(calibration_base_path=str(tmp_path))
        result = manager.load_calibration("myfiber")

        assert result is None

    def test_loads_threshold_despite_corrupt_coupling(self, tmp_path: Path):
        """Valid threshold + corrupt coupling still loads (coupling is optional)."""
        fiber_dir = tmp_path / "myfiber"
        fiber_dir.mkdir()

        _write_threshold_npz(fiber_dir / "myfiber_20260401_threshold.npz")
        corrupt_coupling = fiber_dir / "myfiber_20260401_coupling.npz"
        corrupt_coupling.write_bytes(b"corrupt coupling data")

        manager = CalibrationManager(calibration_base_path=str(tmp_path))
        result = manager.load_calibration("myfiber")

        assert result is not None
        assert result.correction_factors is None
        assert result.n_sections == 4
