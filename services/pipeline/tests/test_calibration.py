"""Unit tests for CalibrationManager and CalibrationData."""

import pickle
import tempfile
from pathlib import Path

import numpy as np
import pytest

from ai_engine.model_vehicle.calibration import (
    CalibrationData,
    CalibrationManager,
)


class TestCalibrationData:
    """Test suite for CalibrationData."""

    @pytest.fixture
    def sample_calibration(self):
        """Create sample calibration data."""
        return CalibrationData(
            fiber_id="test_fiber",
            date="20260101",
            n_sections=3,
            threshold_curve=np.array([100.0, 150.0, 200.0]),
            baseline=np.array([50.0, 75.0, 100.0]),
            noise_estimate=np.array([10.0, 15.0, 20.0]),
            threshold_method="MAD",
            correction_factors=np.array([1.0, 0.95, 1.05]),
            median_glrt=200.0,
        )

    def test_apply_coupling_correction(self, sample_calibration):
        """Test coupling correction application."""
        # GLRT: 3 sections × 5 samples
        glrt = np.array(
            [[100, 200, 150, 180, 120], [50, 100, 75, 90, 60], [200, 300, 250, 280, 220]]
        )

        corrected = sample_calibration.apply_coupling_correction(glrt)

        # Should multiply each section by its factor
        expected = glrt * sample_calibration.correction_factors[:, np.newaxis]

        np.testing.assert_array_almost_equal(corrected, expected)

    def test_apply_coupling_correction_none(self):
        """Test coupling correction when factors are None."""
        calib = CalibrationData(
            fiber_id="test",
            date="20260101",
            n_sections=2,
            threshold_curve=np.array([100.0, 150.0]),
            baseline=np.array([50.0, 75.0]),
            noise_estimate=np.array([10.0, 15.0]),
            threshold_method="MAD",
            correction_factors=None,  # No coupling correction
            median_glrt=None,
        )

        glrt = np.array([[100, 200], [150, 250]])
        corrected = calib.apply_coupling_correction(glrt)

        # Should return unchanged
        np.testing.assert_array_equal(corrected, glrt)

    def test_get_threshold(self, sample_calibration):
        """Test getting threshold for specific section."""
        assert sample_calibration.get_threshold(0) == 100.0
        assert sample_calibration.get_threshold(1) == 150.0
        assert sample_calibration.get_threshold(2) == 200.0

    def test_get_threshold_out_of_range(self, sample_calibration):
        """Test getting threshold for invalid section raises error."""
        with pytest.raises(IndexError):
            sample_calibration.get_threshold(-1)

        with pytest.raises(IndexError):
            sample_calibration.get_threshold(3)

    def test_apply_variable_threshold(self, sample_calibration):
        """Test variable threshold application."""
        # GLRT: 3 sections × 4 samples
        # Section 0 threshold: 100, section 1: 150, section 2: 200
        glrt = np.array([[50, 100, 150, 200], [100, 150, 200, 250], [150, 200, 250, 300]])

        mask = sample_calibration.apply_variable_threshold(glrt)

        # Expected: values >= threshold get 1.0, others get 0.0
        expected = np.array(
            [
                [0.0, 1.0, 1.0, 1.0],  # threshold=100
                [0.0, 1.0, 1.0, 1.0],  # threshold=150
                [0.0, 1.0, 1.0, 1.0],  # threshold=200
            ]
        )

        np.testing.assert_array_equal(mask, expected)


class TestCalibrationManager:
    """Test suite for CalibrationManager."""

    @pytest.fixture
    def temp_calibration_dir(self):
        """Create temporary calibration directory structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create test_fiber directory with calibration files
            fiber_dir = tmpdir / "test_fiber"
            fiber_dir.mkdir()

            # Create threshold calibration
            threshold_data = {
                "fiber_id": "test_fiber",
                "date": "20260101",
                "n_sections": 3,
                "threshold_curve": [100.0, 150.0, 200.0],
                "baseline": [50.0, 75.0, 100.0],
                "noise_estimate": [10.0, 15.0, 20.0],
                "method": "MAD",
            }
            threshold_file = fiber_dir / "test_fiber_20260101_threshold.pkl"
            with open(threshold_file, "wb") as f:
                pickle.dump(threshold_data, f)

            # Create coupling calibration
            coupling_data = {
                "fiber_id": "test_fiber",
                "date": "20260101",
                "correction_factors": [1.0, 0.95, 1.05],
                "median_glrt": 200.0,
                "n_sections": 3,
            }
            coupling_file = fiber_dir / "test_fiber_20260101_coupling.pkl"
            with open(coupling_file, "wb") as f:
                pickle.dump(coupling_data, f)

            yield tmpdir

    @pytest.fixture
    def temp_threshold_only_dir(self):
        """Create directory with only threshold calibration (no coupling)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            fiber_dir = tmpdir / "threshold_only_fiber"
            fiber_dir.mkdir()

            threshold_data = {
                "fiber_id": "threshold_only_fiber",
                "date": "20260101",
                "n_sections": 2,
                "threshold_curve": [80.0, 120.0],
                "baseline": [40.0, 60.0],
                "noise_estimate": [8.0, 12.0],
                "method": "MAD",
            }
            threshold_file = fiber_dir / "threshold_only_fiber_20260101_threshold.pkl"
            with open(threshold_file, "wb") as f:
                pickle.dump(threshold_data, f)

            yield tmpdir

    def test_loads_threshold_and_coupling(self, temp_calibration_dir):
        """Test loading both threshold and coupling calibration."""
        manager = CalibrationManager(str(temp_calibration_dir))

        calib = manager.load_calibration("test_fiber")

        assert calib is not None
        assert calib.fiber_id == "test_fiber"
        assert calib.date == "20260101"
        assert calib.n_sections == 3
        np.testing.assert_array_equal(calib.threshold_curve, [100.0, 150.0, 200.0])
        np.testing.assert_array_equal(calib.baseline, [50.0, 75.0, 100.0])
        np.testing.assert_array_equal(calib.noise_estimate, [10.0, 15.0, 20.0])
        assert calib.threshold_method == "MAD"
        assert calib.correction_factors is not None
        np.testing.assert_array_equal(calib.correction_factors, [1.0, 0.95, 1.05])
        assert calib.median_glrt == 200.0

    def test_loads_threshold_only(self, temp_threshold_only_dir):
        """Test loading threshold-only calibration (no coupling)."""
        manager = CalibrationManager(str(temp_threshold_only_dir))

        calib = manager.load_calibration("threshold_only_fiber")

        assert calib is not None
        assert calib.fiber_id == "threshold_only_fiber"
        assert calib.n_sections == 2
        np.testing.assert_array_equal(calib.threshold_curve, [80.0, 120.0])
        assert calib.correction_factors is None  # No coupling
        assert calib.median_glrt is None

    def test_returns_none_if_directory_missing(self, temp_calibration_dir):
        """Test returns None for fiber with no calibration directory."""
        manager = CalibrationManager(str(temp_calibration_dir))

        calib = manager.load_calibration("nonexistent_fiber")

        assert calib is None

    def test_returns_none_if_threshold_file_missing(self):
        """Test returns None if threshold file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create fiber directory but no threshold file
            fiber_dir = tmpdir / "empty_fiber"
            fiber_dir.mkdir()

            manager = CalibrationManager(str(tmpdir))
            calib = manager.load_calibration("empty_fiber")

            assert calib is None

    def test_caches_calibration(self, temp_calibration_dir):
        """Test that second load uses cache."""
        manager = CalibrationManager(str(temp_calibration_dir))

        # First load
        calib1 = manager.load_calibration("test_fiber")
        assert calib1 is not None

        # Second load should use cache (same object)
        calib2 = manager.load_calibration("test_fiber")
        assert calib2 is calib1

    def test_selects_latest_file(self):
        """Test that manager selects most recent calibration file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            fiber_dir = tmpdir / "versioned_fiber"
            fiber_dir.mkdir()

            # Create old calibration
            old_data = {
                "fiber_id": "versioned_fiber",
                "date": "20250101",
                "n_sections": 1,
                "threshold_curve": [100.0],
                "baseline": [50.0],
                "noise_estimate": [10.0],
                "method": "MAD",
            }
            old_file = fiber_dir / "versioned_fiber_20250101_threshold.pkl"
            with open(old_file, "wb") as f:
                pickle.dump(old_data, f)

            # Create new calibration (modify after old to ensure later mtime)
            import time

            time.sleep(0.01)

            new_data = {
                "fiber_id": "versioned_fiber",
                "date": "20260101",
                "n_sections": 1,
                "threshold_curve": [150.0],
                "baseline": [75.0],
                "noise_estimate": [15.0],
                "method": "MAD",
            }
            new_file = fiber_dir / "versioned_fiber_20260101_threshold.pkl"
            with open(new_file, "wb") as f:
                pickle.dump(new_data, f)

            manager = CalibrationManager(str(tmpdir))
            calib = manager.load_calibration("versioned_fiber")

            # Should load the newer calibration
            assert calib is not None
            assert calib.date == "20260101"
            assert calib.threshold_curve[0] == 150.0

    def test_clear_cache(self, temp_calibration_dir):
        """Test cache clearing."""
        manager = CalibrationManager(str(temp_calibration_dir))

        # Load and cache
        calib1 = manager.load_calibration("test_fiber")
        assert calib1 is not None
        assert len(manager.get_cached_fiber_ids()) == 1

        # Clear cache
        manager.clear_cache()
        assert len(manager.get_cached_fiber_ids()) == 0

        # Load again (should reload from disk)
        calib2 = manager.load_calibration("test_fiber")
        assert calib2 is not None
        assert calib2 is not calib1  # Different object

    def test_get_cached_fiber_ids(self, temp_calibration_dir, temp_threshold_only_dir):
        """Test getting list of cached fiber IDs."""
        # Combine directories (simulate multiple fibers)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Copy both fiber directories
            import shutil

            shutil.copytree(temp_calibration_dir / "test_fiber", tmpdir / "test_fiber")
            shutil.copytree(
                temp_threshold_only_dir / "threshold_only_fiber", tmpdir / "threshold_only_fiber"
            )

            manager = CalibrationManager(str(tmpdir))

            # Initially empty
            assert manager.get_cached_fiber_ids() == []

            # Load first fiber
            manager.load_calibration("test_fiber")
            assert "test_fiber" in manager.get_cached_fiber_ids()
            assert len(manager.get_cached_fiber_ids()) == 1

            # Load second fiber
            manager.load_calibration("threshold_only_fiber")
            cached_ids = manager.get_cached_fiber_ids()
            assert "test_fiber" in cached_ids
            assert "threshold_only_fiber" in cached_ids
            assert len(cached_ids) == 2
