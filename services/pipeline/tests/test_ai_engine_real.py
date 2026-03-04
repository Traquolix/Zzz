"""Tests for AI Engine components.

Tests standalone functions (no mocking) and ModelRegistry (with mocking).
"""

import sys
import threading
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Import standalone functions directly - no mocking needed
from ai_engine.message_utils import (
    ProcessingContext,
    create_count_messages,
    create_speed_messages,
    extract_channel_metadata,
    messages_to_arrays,
    validate_sampling_rate,
)

# Mock only for ModelRegistry tests
sys.modules["torch"] = MagicMock()
sys.modules["matplotlib"] = MagicMock()
sys.modules["matplotlib.pyplot"] = MagicMock()

# Import calibration before mocking to avoid import pollution
from ai_engine.model_vehicle import calibration as calibration_module  # noqa: E402

mock_model_vehicle = MagicMock()
mock_model_vehicle.Args_NN_model_all_channels = MagicMock
mock_model_vehicle.VehicleSpeedEstimator = MagicMock
# Keep calibration classes accessible even after mocking parent module
mock_model_vehicle.calibration = calibration_module
sys.modules["ai_engine.model_vehicle"] = mock_model_vehicle
sys.modules["ai_engine.model_vehicle.DTAN"] = MagicMock()

# Mock simple_interval_counter sub-module so main.py can import SimpleIntervalCounter
mock_simple_counter_module = MagicMock()
mock_simple_counter_module.SimpleIntervalCounter = MagicMock
sys.modules["ai_engine.model_vehicle.simple_interval_counter"] = mock_simple_counter_module

from ai_engine.main import ModelRegistry  # noqa: E402


class TestModelRegistry:
    """Test ModelRegistry LRU eviction logic."""

    @pytest.fixture
    def mock_speed_estimator(self):
        return MagicMock()

    @pytest.fixture
    def mock_counter(self):
        return MagicMock()

    @pytest.fixture
    def registry(self, mock_speed_estimator, mock_counter):
        return ModelRegistry(
            default_model=mock_speed_estimator,
            default_counter=mock_counter,
            max_models=3,
        )

    def test_default_model_for_default_hint(self, registry, mock_speed_estimator):
        """'default' hint should return default model."""
        result = registry.get_speed_estimator("default")
        assert result is mock_speed_estimator

    @patch("ai_engine.main.get_model_spec")
    def test_caches_model_on_second_access(self, mock_get_spec, registry):
        """Second access should return cached model, not reload."""
        mock_spec = MagicMock()
        mock_spec.inference.samples_per_window = 300
        mock_spec.inference.gauge_meters = 10
        mock_spec.inference.channels_per_section = 9
        mock_spec.inference.sampling_rate_hz = 10.0
        mock_spec.exp_name = "test"
        mock_spec.version = "v1"
        mock_spec.path = "/models/test"
        mock_spec.speed_detection.time_overlap_ratio = 0.1667
        mock_spec.speed_detection.glrt_window = 20
        mock_spec.speed_detection.min_speed_kmh = 20.0
        mock_spec.speed_detection.max_speed_kmh = 120.0
        mock_spec.speed_detection.correlation_threshold = 130.0
        mock_get_spec.return_value = mock_spec

        model1 = registry.get_speed_estimator("model_a")
        model2 = registry.get_speed_estimator("model_a")

        assert model1 is model2
        assert mock_get_spec.call_count == 1

    def test_lru_access_order_tracking(self, mock_speed_estimator, mock_counter):
        """Accessing a model should update LRU order."""
        registry = ModelRegistry(
            default_model=mock_speed_estimator,
            default_counter=mock_counter,
            max_models=5,
        )

        # Pre-populate models in order: a, b, c
        registry._loaded_models["a"] = MagicMock()
        registry._loaded_models["b"] = MagicMock()
        registry._loaded_models["c"] = MagicMock()

        # Access "a" - should move it to end
        registry.get_speed_estimator("a")

        # Order should now be: b, c, a
        order = list(registry._loaded_models.keys())
        assert order[-1] == "a"
        assert order[0] == "b"

    @patch("ai_engine.main.get_model_spec")
    def test_lru_eviction_when_max_reached(self, mock_get_spec, mock_speed_estimator, mock_counter):
        """Should evict oldest model when max_models reached."""
        registry = ModelRegistry(
            default_model=mock_speed_estimator,
            default_counter=mock_counter,
            max_models=2,
        )

        mock_spec = MagicMock()
        mock_spec.inference.samples_per_window = 300
        mock_spec.inference.gauge_meters = 10
        mock_spec.inference.channels_per_section = 9
        mock_spec.inference.sampling_rate_hz = 10.0
        mock_spec.exp_name = "test"
        mock_spec.version = "v1"
        mock_spec.path = "/models/test"
        mock_spec.speed_detection.time_overlap_ratio = 0.1667
        mock_spec.speed_detection.glrt_window = 20
        mock_spec.speed_detection.min_speed_kmh = 20.0
        mock_spec.speed_detection.max_speed_kmh = 120.0
        mock_spec.speed_detection.correlation_threshold = 130.0
        mock_get_spec.return_value = mock_spec

        registry.get_speed_estimator("model_1")
        registry.get_speed_estimator("model_2")
        registry.get_speed_estimator("model_3")

        assert len(registry._loaded_models) == 2
        assert "model_1" not in registry._loaded_models
        assert "model_3" in registry._loaded_models

    def test_thread_safe_access(self, mock_speed_estimator, mock_counter):
        """Concurrent access should be thread-safe."""
        registry = ModelRegistry(
            default_model=mock_speed_estimator,
            default_counter=mock_counter,
            max_models=10,
        )

        # Pre-populate models
        for i in range(5):
            registry._loaded_models[f"model_{i}"] = MagicMock()

        errors = []
        results = []

        def access_models():
            try:
                for j in range(10):
                    registry.get_speed_estimator(f"model_{j % 5}")
                    results.append(True)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=access_models) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 50


class TestExtractChannelMetadata:
    """Test channel metadata extraction from payloads."""

    def test_extracts_from_nested_processing_metadata(self):
        """Should extract channel_step from nested processing_metadata."""
        payload = {"channel_start": 500, "processing_metadata": {"channel_selection": {"step": 2}}}

        result = extract_channel_metadata(payload)

        assert result == (500, 2)

    def test_handles_none_processing_metadata(self):
        """None processing_metadata should not crash."""
        payload = {"channel_start": 100, "processing_metadata": None}

        result = extract_channel_metadata(payload)

        assert result == (100, 1)

    def test_handles_zero_step_as_one(self):
        """Step of 0 should be treated as 1."""
        payload = {"processing_metadata": {"channel_selection": {"step": 0}}}

        result = extract_channel_metadata(payload)

        assert result[1] == 1


class TestValidateSamplingRate:
    """Test sampling rate validation."""

    def test_passes_when_rate_within_tolerance(self):
        """Should not raise when rate within 0.1Hz tolerance."""
        payload = {"sampling_rate_hz": 10.05}
        validate_sampling_rate(payload, 10.0)

    def test_raises_when_rate_mismatch(self):
        """Should raise ValueError when rate differs by more than 0.1Hz."""
        payload = {"sampling_rate_hz": 50.0}

        with pytest.raises(ValueError, match="expects 10.0Hz but received 50.0Hz"):
            validate_sampling_rate(payload, 10.0)


class TestMessagesToArrays:
    """Test message to array conversion."""

    def test_extracts_values_and_converts_to_array(self):
        """Should extract values and convert to numpy array."""
        ctx = ProcessingContext()
        messages = [
            MagicMock(
                payload={"values": [1.0, 2.0, 3.0], "channel_start": 0, "timestamp_ns": 1000}
            ),
            MagicMock(
                payload={"values": [4.0, 5.0, 6.0], "channel_start": 0, "timestamp_ns": 2000}
            ),
        ]

        data, timestamps, timestamps_ns = messages_to_arrays(messages, ctx, 10.0)

        assert data.shape == (3, 2)
        assert np.array_equal(data[:, 0], [1.0, 2.0, 3.0])
        assert np.array_equal(data[:, 1], [4.0, 5.0, 6.0])

    def test_raises_on_channel_count_mismatch(self):
        """Should raise ValueError when channel counts differ."""
        ctx = ProcessingContext()
        messages = [
            MagicMock(
                payload={"values": [1.0, 2.0, 3.0], "channel_start": 0, "timestamp_ns": 1000}
            ),
            MagicMock(payload={"values": [1.0, 2.0], "channel_start": 0, "timestamp_ns": 2000}),
        ]

        with pytest.raises(ValueError, match="Channel count mismatch"):
            messages_to_arrays(messages, ctx, 10.0)

    def test_raises_on_channel_start_mismatch(self):
        """Should raise ValueError when channel_start differs."""
        ctx = ProcessingContext()
        messages = [
            MagicMock(payload={"values": [1.0], "channel_start": 0, "timestamp_ns": 1000}),
            MagicMock(payload={"values": [2.0], "channel_start": 100, "timestamp_ns": 2000}),
        ]

        with pytest.raises(ValueError, match="channel_start mismatch"):
            messages_to_arrays(messages, ctx, 10.0)


class TestCreateSpeedMessages:
    """Test speed message creation from detection dicts."""

    def test_creates_one_message_per_detection(self):
        """Each detection dict should produce one message."""
        ctx = ProcessingContext(channel_start=0, channel_step=1)
        detections = [
            {"section_idx": 0, "speed_kmh": 50.0, "direction": 1, "timestamp_ns": 1000000000000, "glrt_max": 5000.0},
            {"section_idx": 1, "speed_kmh": 60.0, "direction": 1, "timestamp_ns": 2000000000000, "glrt_max": 6000.0},
        ]

        messages = create_speed_messages(
            fiber_id="test",
            detections=detections,
            ctx=ctx,
            service_name="test",
        )

        assert len(messages) == 2
        assert messages[0].payload["speeds"][0]["speed"] == 50.0
        assert messages[1].payload["speeds"][0]["speed"] == 60.0

    def test_maps_channels_with_step(self):
        """Should map section_idx to channel using channel_step."""
        ctx = ProcessingContext(channel_start=100, channel_step=2)
        detections = [
            {"section_idx": 0, "speed_kmh": 50.0, "direction": 1, "timestamp_ns": 1000000000000, "glrt_max": 5000.0},
            {"section_idx": 1, "speed_kmh": 60.0, "direction": 1, "timestamp_ns": 1000000000000, "glrt_max": 5000.0},
            {"section_idx": 2, "speed_kmh": 70.0, "direction": 1, "timestamp_ns": 1000000000000, "glrt_max": 5000.0},
        ]

        messages = create_speed_messages(
            fiber_id="test",
            detections=detections,
            ctx=ctx,
            service_name="test",
        )

        assert messages[0].payload["speeds"][0]["channel_number"] == 100
        assert messages[1].payload["speeds"][0]["channel_number"] == 102
        assert messages[2].payload["speeds"][0]["channel_number"] == 104

    def test_preserves_direction(self):
        """Should preserve direction from detection dict."""
        ctx = ProcessingContext(channel_start=0, channel_step=1)
        detections = [
            {"section_idx": 0, "speed_kmh": 50.0, "direction": 1, "timestamp_ns": 1000000000000, "glrt_max": 5000.0},
            {"section_idx": 0, "speed_kmh": 60.0, "direction": 2, "timestamp_ns": 2000000000000, "glrt_max": 5000.0},
        ]

        messages = create_speed_messages(
            fiber_id="test",
            detections=detections,
            ctx=ctx,
            service_name="test",
        )

        assert messages[0].payload["direction"] == 1
        assert messages[1].payload["direction"] == 2

    def test_empty_detections(self):
        """No detections should produce no messages."""
        ctx = ProcessingContext(channel_start=0, channel_step=1)

        messages = create_speed_messages(
            fiber_id="test",
            detections=[],
            ctx=ctx,
            service_name="test",
        )

        assert len(messages) == 0

    def test_timestamp_from_detection(self):
        """Should use timestamp_ns from detection dict."""
        ctx = ProcessingContext(channel_start=0, channel_step=1)
        detections = [
            {"section_idx": 0, "speed_kmh": 90.0, "direction": 1, "timestamp_ns": 1234567890000, "glrt_max": 5000.0},
        ]

        messages = create_speed_messages(
            fiber_id="test",
            detections=detections,
            ctx=ctx,
            service_name="test",
        )

        assert messages[0].payload["timestamp_ns"] == 1234567890000


class TestCreateCountMessages:
    """Test count message creation."""

    def test_creates_messages_from_count_results(self):
        """Should create messages from count results."""
        ctx = ProcessingContext(channel_start=0, channel_step=1)
        count_results = (
            [[1.0]],
            [([250], [260])],
            [i * 100000000000 for i in range(300)],
        )

        messages = create_count_messages(
            fiber_id="test_fiber",
            count_results=count_results,
            ctx=ctx,
            sampling_rate_hz=10.0,
            channels_per_section=9,
            counting_samples=300,
            step_samples=100,
            service_name="test_engine",
        )

        assert len(messages) == 1
        assert messages[0].payload["vehicle_count"] == 1.0

    def test_filters_old_data(self):
        """Should filter out detections in old data."""
        ctx = ProcessingContext(channel_start=0, channel_step=1)
        count_results = (
            [[1.0]],
            [([50], [60])],  # start=50 < new_data_start=200
            [i * 100000000000 for i in range(300)],
        )

        messages = create_count_messages(
            fiber_id="test",
            count_results=count_results,
            ctx=ctx,
            sampling_rate_hz=10.0,
            channels_per_section=9,
            counting_samples=300,
            step_samples=100,
            service_name="test",
        )

        assert len(messages) == 0

    def test_maps_channels_with_step(self):
        """Should map section to actual channels using step."""
        ctx = ProcessingContext(channel_start=100, channel_step=2)
        count_results = (
            [[1.0]],
            [([250], [260])],
            [i * 100000000000 for i in range(300)],
        )

        messages = create_count_messages(
            fiber_id="test",
            count_results=count_results,
            ctx=ctx,
            sampling_rate_hz=10.0,
            channels_per_section=9,
            counting_samples=300,
            step_samples=100,
            service_name="test",
        )

        assert messages[0].payload["channel_start"] == 100
        assert messages[0].payload["channel_end"] == 116

    def test_rounds_timestamp_to_second(self):
        """Should round count timestamp to nearest second."""
        ctx = ProcessingContext(channel_start=0, channel_step=1)
        count_results = (
            [[1.0]],
            [([250], [260])],
            [1704110400123456789 + i * 100000000 for i in range(300)],
        )

        messages = create_count_messages(
            fiber_id="test",
            count_results=count_results,
            ctx=ctx,
            sampling_rate_hz=10.0,
            channels_per_section=9,
            counting_samples=300,
            step_samples=100,
            service_name="test",
        )

        assert messages[0].payload["count_timestamp_ns"] % 1_000_000_000 == 0

    def test_handles_none_section_counts(self):
        """Should handle None section counts."""
        ctx = ProcessingContext(channel_start=0, channel_step=1)
        count_results = (
            [None],
            [([250], [260])],
            [i * 100000000000 for i in range(300)],
        )

        messages = create_count_messages(
            fiber_id="test",
            count_results=count_results,
            ctx=ctx,
            sampling_rate_hz=10.0,
            channels_per_section=9,
            counting_samples=300,
            step_samples=100,
            service_name="test",
        )

        assert len(messages) == 0
