"""Tests for VehicleCounter (CNN counting with accumulation and lambda fallback).

Architecture validation is in test_model_integrity.py.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from ai_engine.model_vehicle.simple_interval_counter import VehicleCounter, build_counting_network
from tests.ai_engine.conftest import CHANNELS_PER_SECTION, CORR_THRESHOLD, SAMPLING_RATE_HZ

# Paths for the real counting model + calibration files
_MODEL_DIR = Path(__file__).resolve().parents[2] / "ai_engine" / "model_vehicle"
_COUNTING_MODEL_PATH = _MODEL_DIR / "models_parameters" / "vehicle_counting_model.pt"
_THRESHOLDS_PATH = _MODEL_DIR / "models_parameters" / "detection_thresholds_adapted_sectionwise.csv"
_MEAN_STD_PATH = _MODEL_DIR / "models_parameters" / "mean_std_features_adapted_sectionwise.csv"


@pytest.fixture
def lambda_counter() -> VehicleCounter:
    """Counter in lambda mode (no NN model)."""
    return VehicleCounter(
        fiber_id="test",
        sampling_rate_hz=SAMPLING_RATE_HZ,
        correlation_threshold=CORR_THRESHOLD,
        channels_per_section=CHANNELS_PER_SECTION,
        vehicle_counting_model=None,
        time_window_duration=360.0,
    )


@pytest.fixture
def nn_counter() -> VehicleCounter | None:
    """Counter with real NN model loaded (skip if model file missing)."""
    if not _COUNTING_MODEL_PATH.exists():
        pytest.skip(f"Counting model not found: {_COUNTING_MODEL_PATH}")

    import torch

    nn_model = build_counting_network()
    try:
        state = torch.load(_COUNTING_MODEL_PATH, map_location="cpu", weights_only=True)
    except Exception:
        state = torch.load(  # nosec B614
            _COUNTING_MODEL_PATH, map_location="cpu", weights_only=False
        ).state_dict()
    nn_model.load_state_dict(state)
    nn_model.eval()

    thresholds = None
    if _THRESHOLDS_PATH.exists():
        thresholds = np.loadtxt(_THRESHOLDS_PATH, delimiter=",")

    mean_std = None
    if _MEAN_STD_PATH.exists():
        mean_std = np.loadtxt(_MEAN_STD_PATH, delimiter=",")

    return VehicleCounter(
        fiber_id="test",
        sampling_rate_hz=SAMPLING_RATE_HZ,
        correlation_threshold=CORR_THRESHOLD,
        channels_per_section=CHANNELS_PER_SECTION,
        vehicle_counting_model=nn_model,
        detection_thresholds=thresholds,
        mean_std_features=mean_std,
        time_window_duration=360.0,
        step_samples=250,
    )


class TestCountingNetworkOutput:
    """Tests for the counting MLP behavior."""

    def test_relu_output_non_negative(self):
        """Output layer has ReLU: all outputs must be >= 0."""
        import torch

        model = build_counting_network()
        x = torch.randn(100, 5)
        with torch.no_grad():
            y = model(x)
        assert (y >= 0).all()


class TestLambdaCounter:
    """Tests for lambda (peak-based) counting fallback."""

    def test_no_signal_no_counts(self, lambda_counter):
        """Zero GLRT signal should produce zero counts."""
        n_sections, time_samples = 1, 100
        corr = np.zeros((n_sections, time_samples))
        speed = np.zeros((n_sections, CHANNELS_PER_SECTION - 1, time_samples))
        data = np.zeros((n_sections, CHANNELS_PER_SECTION, time_samples))

        counts, _intervals = lambda_counter.process_window_data(speed, corr, data)
        for section_count in counts:
            if section_count.size > 0:
                assert np.all(section_count == 0)

    def test_single_peak_detected(self, lambda_counter):
        """A single strong GLRT peak should produce count=1."""
        n_sections, time_samples = 1, 500
        corr = np.zeros((n_sections, time_samples))
        corr[0, 200:230] = lambda_counter.corr_threshold * 2
        speed = np.full((n_sections, CHANNELS_PER_SECTION - 1, time_samples), 60.0)
        data = np.random.default_rng(0).standard_normal(
            (n_sections, CHANNELS_PER_SECTION, time_samples)
        )

        counts, _intervals = lambda_counter.process_window_data(speed, corr, data)
        total = sum(c.sum() for c in counts if c.size > 0)
        assert total >= 1, f"Expected at least 1 vehicle, got {total}"


class TestNNCounter:
    """Tests for NN-based counting."""

    def test_nn_produces_counts(self, nn_counter):
        """NN counter should produce non-negative counts."""
        n_sections, time_samples = 1, 500
        corr = np.zeros((n_sections, time_samples))
        corr[0, 200:250] = 1000.0
        speed = np.full((n_sections, CHANNELS_PER_SECTION - 1, time_samples), 60.0)
        data = np.random.default_rng(0).standard_normal(
            (n_sections, CHANNELS_PER_SECTION, time_samples)
        )

        counts, _intervals = nn_counter.process_window_data(speed, corr, data)
        for section_count in counts:
            if section_count.size > 0:
                assert np.all(section_count >= 0), "NN counts must be non-negative"

    def test_nn_sanity_cap_applied(self, nn_counter):
        """NN counts should be capped by duration and lambda caps."""
        n_sections, time_samples = 1, 500
        corr = np.zeros((n_sections, time_samples))
        corr[0, 50:450] = 1000.0
        speed = np.full((n_sections, CHANNELS_PER_SECTION - 1, time_samples), 60.0)
        data = np.random.default_rng(0).standard_normal(
            (n_sections, CHANNELS_PER_SECTION, time_samples)
        )

        counts, _intervals = nn_counter.process_window_data(speed, corr, data)
        for section_count in counts:
            if section_count.size > 0:
                max_possible = np.ceil(400 / (nn_counter.min_headway_seconds * nn_counter.fs))
                assert np.all(section_count <= max_possible + 1)


class TestAccumulation:
    """Tests for the sliding-window accumulation buffer."""

    def test_buffer_initialization(self, lambda_counter):
        """First chunk should initialize buffers."""
        assert not lambda_counter._has_buffers()

        n_sections = 1
        speed = np.zeros((n_sections, CHANNELS_PER_SECTION - 1, 100))
        corr = np.zeros((n_sections, 100))
        data = np.zeros((n_sections, CHANNELS_PER_SECTION, 100))

        results = list(lambda_counter.process_data_chunk(speed, corr, data))
        assert lambda_counter._has_buffers()
        assert len(results) == 0

    def test_buffer_fires_when_full(self, lambda_counter):
        """Buffer should yield results when accumulated samples >= time_window_samples."""
        n_sections = 1
        time_window_samples = int(lambda_counter.time_window_duration * lambda_counter.fs)
        chunk_size = 500
        n_chunks = (time_window_samples // chunk_size) + 2
        total_yields = 0

        for _i in range(n_chunks):
            speed = np.zeros((n_sections, CHANNELS_PER_SECTION - 1, chunk_size))
            corr = np.zeros((n_sections, chunk_size))
            data = np.zeros((n_sections, CHANNELS_PER_SECTION, chunk_size))
            for _result in lambda_counter.process_data_chunk(speed, corr, data):
                total_yields += 1

        assert total_yields >= 1, "Counter should fire after accumulating enough data"

    def test_reset_clears_buffers(self, lambda_counter):
        """_reset_buffers should clear all accumulation state."""
        n_sections = 1
        speed = np.zeros((n_sections, CHANNELS_PER_SECTION - 1, 100))
        corr = np.zeros((n_sections, 100))
        data = np.zeros((n_sections, CHANNELS_PER_SECTION, 100))

        list(lambda_counter.process_data_chunk(speed, corr, data))
        assert lambda_counter._has_buffers()

        lambda_counter._reset_buffers()
        assert not lambda_counter._has_buffers()
