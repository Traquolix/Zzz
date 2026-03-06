"""Tests for bidirectional detection (Phase 4)."""

import sys
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.modules.setdefault("matplotlib", MagicMock())
sys.modules.setdefault("matplotlib.pyplot", MagicMock())

import torch  # noqa: E402

from ai_engine.model_vehicle.vehicle_speed import VehicleSpeedEstimator  # noqa: E402


class FakeModelArgs:
    """Minimal model args for testing without real model loading."""

    def __init__(self):
        self.signal_length = 100
        self.input_shape = 100
        self.N_channels = 1
        self.Nch = 9
        self.fs = 10.0
        self.gauge = 10
        self.batch_size = 32
        self.device_name = "cpu"


class TestBidirectionalDetection:
    """Test bidirectional detection logic."""

    @pytest.fixture
    def make_estimator(self):
        """Factory to create estimator with custom bidirectional setting."""

        def _make(bidirectional: bool):
            e = VehicleSpeedEstimator.__new__(VehicleSpeedEstimator)
            e.window_size = 100
            e.Nch = 9
            e.overlap_space = 1
            e.fs = 10.0
            e.gauge = 10
            e.glrt_win = 20
            e.edge_trim = 25
            e.min_speed = 20
            e.max_speed = 120
            e.corr_threshold = 500
            e.eps = 1e-8
            e.speed_scaling = 3.6 * 10.0 * 10
            e.model_args = FakeModelArgs()
            e.bidirectional_detection = bidirectional
            e.speed_glrt_factor = 2.0
            e.speed_weighting = "glrt"
            e.speed_positive_glrt_only = True
            e.calibration_data = None
            e.visualizer = None
            e.intervals = None
            e.verbose = False
            return e

        return _make

    def test_forward_only_when_disabled(self, make_estimator):
        """bidirectional=False should not flip data."""
        e = make_estimator(False)

        calls = []

        def mock_process(data):
            calls.append(data.shape)
            n_sec = max(1, (data.shape[0] - e.Nch) // (e.Nch - e.overlap_space) + 1)
            n_pairs = e.Nch - 1
            t = data.shape[1]
            return (
                np.ones((n_sec, n_pairs, t)),  # per_pair
                np.ones((n_sec, t)) * 1000,  # summed
                np.ones((n_sec, n_pairs, t)) * 60,  # speed
                torch.ones(n_sec, e.Nch, t),  # aligned
                torch.ones(n_sec, n_pairs, 10),  # thetas
            )

        e._process_single_direction = mock_process
        data = np.random.randn(50, 100)
        dates = np.arange(100) / 10.0
        dates_ns = np.arange(100) * 100_000_000

        results = list(e.process_file(data, dates, dates_ns))
        assert len(results) == 1
        # Should only call _process_single_direction once (forward only)
        assert len(calls) == 1

    def test_bidirectional_calls_twice(self, make_estimator):
        """bidirectional=True should call forward + reverse."""
        e = make_estimator(True)

        calls = []

        def mock_process(data):
            calls.append(data.copy())
            n_sec = max(1, (data.shape[0] - e.Nch) // (e.Nch - e.overlap_space) + 1)
            n_pairs = e.Nch - 1
            t = data.shape[1]
            return (
                np.ones((n_sec, n_pairs, t)),
                np.ones((n_sec, t)) * 1000,
                np.ones((n_sec, n_pairs, t)) * 60,
                torch.ones(n_sec, e.Nch, t),
                torch.ones(n_sec, n_pairs, 10),
            )

        e._process_single_direction = mock_process
        data = np.random.randn(50, 100)
        dates = np.arange(100) / 10.0
        dates_ns = np.arange(100) * 100_000_000

        list(e.process_file(data, dates, dates_ns))
        assert len(calls) == 2

    def test_direction_mask_values(self, make_estimator):
        """Direction mask should have values 0-3."""
        e = make_estimator(True)

        def mock_process(data):
            n_sec = max(1, (data.shape[0] - e.Nch) // (e.Nch - e.overlap_space) + 1)
            n_pairs = e.Nch - 1
            t = data.shape[1]
            return (
                np.ones((n_sec, n_pairs, t)) * 100,
                np.ones((n_sec, t)) * 5000,
                np.ones((n_sec, n_pairs, t)) * 60,
                torch.ones(n_sec, e.Nch, t),
                torch.ones(n_sec, n_pairs, 10),
            )

        e._process_single_direction = mock_process
        data = np.random.randn(50, 100)
        dates = np.arange(100) / 10.0
        dates_ns = np.arange(100) * 100_000_000

        for result in e.process_file(data, dates, dates_ns):
            # Both forward and reverse should be detected -> mask = 3
            assert np.all((result.direction_mask >= 0) & (result.direction_mask <= 3))
