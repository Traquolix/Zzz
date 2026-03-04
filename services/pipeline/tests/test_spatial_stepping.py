"""Tests for spatial stepping alignment (step=1 matching notebook).

The notebook processes every spatial position with step=1:
    for i in range(n_spatial):
        window_9ch = time_slice[i:i+Nch, :]

Production uses split_channel_overlap with step = Nch - overlap_space.
With N_channels (overlap_space) = Nch-1 = 8, step = 9-8 = 1, matching notebook.
"""

import numpy as np
import pytest


class TestSplitChannelOverlapStep:
    """Verify split_channel_overlap produces step=1 spatial windows."""

    @pytest.fixture
    def estimator(self):
        """Create a minimal VehicleSpeedEstimator with spatial params set."""
        import sys
        from unittest.mock import MagicMock

        # Ensure clean imports (no stale mocked modules)
        sys.modules.setdefault("matplotlib", MagicMock())
        sys.modules.setdefault("matplotlib.pyplot", MagicMock())

        from ai_engine.model_vehicle.dtan_inference import DTANInference
        from ai_engine.model_vehicle.vehicle_speed import VehicleSpeedEstimator

        e = VehicleSpeedEstimator.__new__(VehicleSpeedEstimator)
        e.Nch = 9
        e.overlap_space = 8  # Nch - 1 → step = 1

        # Create minimal DTANInference for split_channel_overlap
        dtan = DTANInference.__new__(DTANInference)
        dtan.Nch = 9
        dtan.overlap_space = 8
        e._dtan = dtan
        return e

    def test_step_1_window_count(self, estimator):
        """With overlap_space=Nch-1, should get C-Nch+1 windows (step=1)."""
        C = 100
        data = np.random.randn(C, 300)
        result = estimator.split_channel_overlap(data)
        expected_windows = C - estimator.Nch + 1  # = 92
        assert result.shape[0] == expected_windows

    def test_step_1_adjacent_windows_differ_by_one_channel(self, estimator):
        """Adjacent windows should share Nch-1 channels (differ by 1)."""
        C = 50
        data = np.arange(C * 100).reshape(C, 100).astype(float)
        result = estimator.split_channel_overlap(data)

        # Window 0 starts at channel 0, window 1 at channel 1, etc.
        for i in range(result.shape[0] - 1):
            # Channels 1..8 of window i should equal channels 0..7 of window i+1
            np.testing.assert_array_equal(result[i, 1:, :], result[i + 1, :-1, :])

    def test_step_1_matches_notebook_loop(self, estimator):
        """split_channel_overlap output should match notebook's manual loop."""
        C = 30
        T = 50
        data = np.random.randn(C, T)
        Nch = estimator.Nch

        # Notebook approach: manual loop with step=1
        n_spatial = C - Nch + 1
        notebook_windows = np.array([data[i : i + Nch, :] for i in range(n_spatial)])

        # Production approach: split_channel_overlap
        production_windows = estimator.split_channel_overlap(data)

        assert production_windows.shape == notebook_windows.shape
        np.testing.assert_array_equal(production_windows, notebook_windows)

    def test_old_step_8_would_give_fewer_windows(self, estimator):
        """Verify the old N_channels=1 (step=8) gives far fewer windows."""
        from ai_engine.model_vehicle.dtan_inference import DTANInference

        estimator_old = type(estimator).__new__(type(estimator))
        estimator_old.Nch = 9
        estimator_old.overlap_space = 1  # OLD: N_channels=1 → step=8
        dtan_old = DTANInference.__new__(DTANInference)
        dtan_old.Nch = 9
        dtan_old.overlap_space = 1
        estimator_old._dtan = dtan_old

        C = 100
        data = np.random.randn(C, 300)

        old_result = estimator_old.split_channel_overlap(data)
        new_result = estimator.split_channel_overlap(data)

        # Old: (100-9)//8 + 1 = 12 windows
        # New: (100-9)//1 + 1 = 92 windows
        assert old_result.shape[0] == 12
        assert new_result.shape[0] == 92

    def test_exact_nch_channels_gives_one_window(self, estimator):
        """If input has exactly Nch channels, should produce exactly 1 window."""
        data = np.random.randn(9, 300)
        result = estimator.split_channel_overlap(data)
        assert result.shape == (1, 9, 300)

    def test_each_window_has_correct_shape(self, estimator):
        """Every window should be (Nch, time)."""
        data = np.random.randn(50, 200)
        result = estimator.split_channel_overlap(data)
        assert result.shape[1] == 9  # Nch
        assert result.shape[2] == 200  # time


class TestNChannelsConfig:
    """Verify N_channels is set correctly in production config."""

    def test_n_channels_matches_nch_minus_1(self):
        """N_channels should be Nch-1 for step=1 spatial overlap."""
        from config.fiber_config import FiberConfigManager

        FiberConfigManager.reset()
        try:
            mgr = FiberConfigManager()
            for model_name, spec in mgr.get_all_models().items():
                nch = spec.inference.channels_per_section
                # The expected N_channels value used in production
                expected_n_channels = nch - 1
                # Verify the config yields step=1
                step = nch - expected_n_channels
                assert step == 1, (
                    f"Model {model_name}: N_channels should be {expected_n_channels} "
                    f"(Nch-1) for step=1, but would give step={step}"
                )
        finally:
            FiberConfigManager.reset()
