"""Tests for DASProcessor.transform() and related methods.

These tests verify the real DASProcessor logic with mocked infrastructure.
"""

import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from processor.main import DASProcessor
from processor.processing_tools import ProcessingChain
from config import FiberConfig, SectionConfig, PipelineStepConfig
from shared.message import Message, KafkaMessage
from shared.service_config import ServiceConfig


@pytest.fixture
def mock_fiber_config():
    """Create a test fiber configuration."""
    return FiberConfig(
        fiber_id="test_fiber",
        input_topic="das.raw.test_fiber",
        total_channels=1000,
        sampling_rate_hz=50.0,
        sections=[
            SectionConfig(
                name="section1",
                channel_start=0,
                channel_stop=100,
                model="test_model",
                pipeline=[
                    PipelineStepConfig(step="temporal_decimation", params={"factor": 5}),
                ],
            ),
            SectionConfig(
                name="section2",
                channel_start=100,
                channel_stop=200,
                model="test_model",
                pipeline=[
                    PipelineStepConfig(step="temporal_decimation", params={"factor": 5}),
                ],
            ),
        ],
    )


@pytest.fixture
def mock_service_config():
    """Minimal service config for testing."""
    return ServiceConfig(
        kafka_bootstrap_servers="localhost:9092",
        schema_registry_url="http://localhost:8081",
        input_topic_pattern="das.raw.*",
        output_topic="das.processed",
        input_key_schema_file=None,
        input_value_schema_file=None,
        output_key_schema_file=None,
        output_value_schema_file=None,
        enable_dlq=False,
    )


class TestDASProcessorMessageAdaptation:
    """Test _adapt_message format conversion."""

    def test_adapts_floatdata_format(self, mock_service_config, mock_fiber_config):
        """Should convert floatData format to internal format."""
        with patch('services.processor.main.load_service_config', return_value=mock_service_config), \
             patch('services.processor.main.get_service_name', return_value='das-processor'), \
             patch('services.processor.main.get_fiber_config', return_value=mock_fiber_config), \
             patch('services.patterns.service_base.ServiceBase._load_schema', return_value=None), \
             patch('services.processor.main.setup_otel'):

            processor = DASProcessor()
            processor.logger = MagicMock()

            raw_msg = {
                "floatData": [1.0, 2.0, 3.0, 4.0, 5.0],
                "timeStampNanoSec": 1234567890000,
            }

            result = processor._adapt_message(raw_msg, "test_fiber", 50.0)

            assert result["fiber_id"] == "test_fiber"
            assert result["values"] == [1.0, 2.0, 3.0, 4.0, 5.0]
            assert result["timestamp_ns"] == 1234567890000
            assert result["channel_start"] == 0
            assert result["sampling_rate_hz"] == 50.0

    def test_adapts_longdata_format(self, mock_service_config, mock_fiber_config):
        """Should convert longData format to internal format."""
        with patch('services.processor.main.load_service_config', return_value=mock_service_config), \
             patch('services.processor.main.get_service_name', return_value='das-processor'), \
             patch('services.processor.main.get_fiber_config', return_value=mock_fiber_config), \
             patch('services.patterns.service_base.ServiceBase._load_schema', return_value=None), \
             patch('services.processor.main.setup_otel'):

            processor = DASProcessor()
            processor.logger = MagicMock()

            raw_msg = {
                "longData": [100, 200, 300],
                "timeStampNanoSec": 9876543210000,
            }

            result = processor._adapt_message(raw_msg, "test_fiber", 50.0)

            assert result["values"] == [100, 200, 300]
            assert result["timestamp_ns"] == 9876543210000

    def test_passes_internal_format_unchanged(self, mock_service_config, mock_fiber_config):
        """Already-internal format should just get fiber_id updated."""
        with patch('services.processor.main.load_service_config', return_value=mock_service_config), \
             patch('services.processor.main.get_service_name', return_value='das-processor'), \
             patch('services.processor.main.get_fiber_config', return_value=mock_fiber_config), \
             patch('services.patterns.service_base.ServiceBase._load_schema', return_value=None), \
             patch('services.processor.main.setup_otel'):

            processor = DASProcessor()
            processor.logger = MagicMock()

            internal_msg = {
                "values": [1.0, 2.0, 3.0],
                "timestamp_ns": 1000000000000,
                "channel_start": 50,
                "sampling_rate_hz": 50.0,
            }

            result = processor._adapt_message(internal_msg, "new_fiber", 50.0)

            assert result["fiber_id"] == "new_fiber"
            assert result["values"] == [1.0, 2.0, 3.0]
            assert result["channel_start"] == 50  # Preserved


class TestDASProcessorFiberIdExtraction:
    """Test _extract_fiber_id from topic name."""

    def test_extracts_fiber_id_from_topic(self, mock_service_config, mock_fiber_config):
        """Should extract last segment of topic as fiber_id."""
        with patch('services.processor.main.load_service_config', return_value=mock_service_config), \
             patch('services.processor.main.get_service_name', return_value='das-processor'), \
             patch('services.processor.main.get_fiber_config', return_value=mock_fiber_config), \
             patch('services.patterns.service_base.ServiceBase._load_schema', return_value=None), \
             patch('services.processor.main.setup_otel'):

            processor = DASProcessor()

            assert processor._extract_fiber_id("das.raw.carros") == "carros"
            assert processor._extract_fiber_id("das.raw.fiber1") == "fiber1"
            assert processor._extract_fiber_id("some.topic.name") == "name"


class TestDASProcessorTransform:
    """Test transform() method - the core processing logic."""

    @pytest.mark.asyncio
    async def test_transform_processes_matching_sections(self, mock_service_config, mock_fiber_config):
        """Should process message through matching section pipelines."""
        with patch('services.processor.main.load_service_config', return_value=mock_service_config), \
             patch('services.processor.main.get_service_name', return_value='das-processor'), \
             patch('services.processor.main.get_fiber_config', return_value=mock_fiber_config), \
             patch('services.patterns.service_base.ServiceBase._load_schema', return_value=None), \
             patch('services.processor.main.setup_otel'):

            processor = DASProcessor()
            processor.logger = MagicMock()
            processor.tracer = MagicMock()
            processor.tracer.start_as_current_span = MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()))

            # Message overlaps section1 (channels 0-100)
            message = Message(
                id="test_msg",
                payload={
                    "fiber_id": "test_fiber",  # Required for non-Kafka messages
                    "values": [1.0] * 100,
                    "timestamp_ns": int(time.time() * 1e9),
                    "channel_start": 0,
                    "sampling_rate_hz": 50.0,
                },
            )

            # Need to send 5 messages for temporal decimation factor=5 to produce output
            results = []
            for i in range(5):
                result = await processor.transform(message)
                results.extend(result)

            # Should have at least one output after 5 messages (temporal decimation)
            assert len(results) >= 1

            # Check output structure
            output = results[0]
            assert output.payload["fiber_id"] == "test_fiber"
            assert "section1" in output.id
            assert output.headers["fiber_id"] == "test_fiber"
            assert output.headers["section"] == "section1"
            assert output.headers["model_hint"] == "test_model"

    @pytest.mark.asyncio
    async def test_transform_skips_non_overlapping_sections(self, mock_service_config, mock_fiber_config):
        """Should skip sections that don't overlap with message channels."""
        with patch('services.processor.main.load_service_config', return_value=mock_service_config), \
             patch('services.processor.main.get_service_name', return_value='das-processor'), \
             patch('services.processor.main.get_fiber_config', return_value=mock_fiber_config), \
             patch('services.patterns.service_base.ServiceBase._load_schema', return_value=None), \
             patch('services.processor.main.setup_otel'):

            processor = DASProcessor()
            processor.logger = MagicMock()
            processor.tracer = MagicMock()
            processor.tracer.start_as_current_span = MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()))

            # Message channels 500-600 don't overlap any section (section1: 0-100, section2: 100-200)
            message = Message(
                id="test_msg",
                payload={
                    "fiber_id": "test_fiber",  # Required for non-Kafka messages
                    "values": [1.0] * 100,
                    "timestamp_ns": int(time.time() * 1e9),
                    "channel_start": 500,
                    "sampling_rate_hz": 50.0,
                },
            )

            # Send 5 messages
            results = []
            for i in range(5):
                result = await processor.transform(message)
                results.extend(result)

            # No sections match, so no outputs
            assert len(results) == 0

    @pytest.mark.asyncio
    async def test_transform_raises_for_unknown_fiber(self, mock_service_config):
        """Should raise ValueError for unknown fiber_id."""
        with patch('services.processor.main.load_service_config', return_value=mock_service_config), \
             patch('services.processor.main.get_service_name', return_value='das-processor'), \
             patch('services.processor.main.get_fiber_config', side_effect=KeyError("unknown_fiber")), \
             patch('services.patterns.service_base.ServiceBase._load_schema', return_value=None), \
             patch('services.processor.main.setup_otel'):

            processor = DASProcessor()
            processor.logger = MagicMock()
            processor.tracer = MagicMock()
            span_mock = MagicMock()
            # __exit__ must return False to not suppress exceptions
            processor.tracer.start_as_current_span = MagicMock(
                return_value=MagicMock(
                    __enter__=MagicMock(return_value=span_mock),
                    __exit__=MagicMock(return_value=False)
                )
            )

            message = Message(
                id="test_msg",
                payload={"values": [1.0], "fiber_id": "unknown_fiber"},
            )

            with pytest.raises(ValueError, match="No config for fiber"):
                await processor.transform(message)

    @pytest.mark.asyncio
    async def test_transform_extracts_fiber_id_from_kafka_topic(self, mock_service_config, mock_fiber_config):
        """Should extract fiber_id from Kafka message topic."""
        with patch('services.processor.main.load_service_config', return_value=mock_service_config), \
             patch('services.processor.main.get_service_name', return_value='das-processor'), \
             patch('services.processor.main.get_fiber_config', return_value=mock_fiber_config), \
             patch('services.patterns.service_base.ServiceBase._load_schema', return_value=None), \
             patch('services.processor.main.setup_otel'):

            processor = DASProcessor()
            processor.logger = MagicMock()
            processor.tracer = MagicMock()
            processor.tracer.start_as_current_span = MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()))

            # Create a KafkaMessage with a mock Kafka message
            kafka_msg = MagicMock()
            kafka_msg.topic.return_value = "das.raw.test_fiber"

            message = KafkaMessage(
                id="test_msg",
                payload={
                    "values": [1.0] * 100,
                    "timestamp_ns": int(time.time() * 1e9),
                    "channel_start": 0,
                    "sampling_rate_hz": 50.0,
                },
                _kafka_message=kafka_msg,
            )

            # Should not raise - fiber_id extracted from topic
            results = []
            for i in range(5):
                result = await processor.transform(message)
                results.extend(result)

            # Verify topic was accessed
            kafka_msg.topic.assert_called()


class TestDASProcessorBuildOutput:
    """Test _build_output construction."""

    def test_builds_output_with_correct_structure(self, mock_service_config, mock_fiber_config):
        """Should build output with all required fields."""
        with patch('services.processor.main.load_service_config', return_value=mock_service_config), \
             patch('services.processor.main.get_service_name', return_value='das-processor'), \
             patch('services.processor.main.get_fiber_config', return_value=mock_fiber_config), \
             patch('services.patterns.service_base.ServiceBase._load_schema', return_value=None), \
             patch('services.processor.main.setup_otel'):

            processor = DASProcessor()
            processor.logger = MagicMock()

            original = {
                "values": list(range(100)),
                "timestamp_ns": 1000000000000,
            }
            processed = {
                "fiber_id": "test_fiber",
                "values": [1.0, 2.0, 3.0],
                "timestamp_ns": 1000000000000,
                "sampling_rate_hz": 10.0,
                "channel_start": 0,
                "temporal_decimation_factor": 5,
                "spatial_decimation_factor": 2,
            }

            output = processor._build_output(
                original, processed, "corr-123", time.time(),
                mock_fiber_config, mock_fiber_config.sections[0]
            )

            assert output["fiber_id"] == "test_fiber"
            assert output["values"] == [1.0, 2.0, 3.0]
            assert output["channel_count"] == 3
            assert output["section"] == "section1"
            assert output["model_hint"] == "test_model"
            assert "signal_stats" in output
            assert output["signal_stats"]["min_value"] == 1.0
            assert output["signal_stats"]["max_value"] == 3.0
            assert "processing_metadata" in output
            assert output["processing_metadata"]["correlation_id"] == "corr-123"

    def test_handles_empty_values(self, mock_service_config, mock_fiber_config):
        """Should handle empty values array."""
        with patch('services.processor.main.load_service_config', return_value=mock_service_config), \
             patch('services.processor.main.get_service_name', return_value='das-processor'), \
             patch('services.processor.main.get_fiber_config', return_value=mock_fiber_config), \
             patch('services.patterns.service_base.ServiceBase._load_schema', return_value=None), \
             patch('services.processor.main.setup_otel'):

            processor = DASProcessor()
            processor.logger = MagicMock()

            original = {"values": []}
            processed = {
                "fiber_id": "test_fiber",
                "values": [],
                "timestamp_ns": 1000000000000,
            }

            output = processor._build_output(
                original, processed, "corr-123", time.time(),
                mock_fiber_config, mock_fiber_config.sections[0]
            )

            assert output["channel_count"] == 0
            assert output["signal_stats"]["min_value"] == 0.0
            assert output["signal_stats"]["max_value"] == 0.0


class TestDASProcessorPipelineCaching:
    """Test fiber pipeline caching and hot-reload."""

    def test_caches_pipelines_per_fiber(self, mock_service_config, mock_fiber_config):
        """Should cache pipelines and reuse them."""
        with patch('services.processor.main.load_service_config', return_value=mock_service_config), \
             patch('services.processor.main.get_service_name', return_value='das-processor'), \
             patch('services.processor.main.get_fiber_config', return_value=mock_fiber_config), \
             patch('services.patterns.service_base.ServiceBase._load_schema', return_value=None), \
             patch('services.processor.main.setup_otel'):

            processor = DASProcessor()
            processor.logger = MagicMock()

            # First call should build pipelines
            pipelines1 = processor._get_fiber_pipelines("test_fiber")
            assert len(pipelines1) == 2  # 2 sections

            # Second call should return cached pipelines (same objects)
            pipelines2 = processor._get_fiber_pipelines("test_fiber")
            assert pipelines1 is pipelines2

    def test_rebuilds_pipelines_on_config_change(self, mock_service_config, mock_fiber_config):
        """Should rebuild pipelines when config changes."""
        with patch('services.processor.main.load_service_config', return_value=mock_service_config), \
             patch('services.processor.main.get_service_name', return_value='das-processor'), \
             patch('services.processor.main.get_fiber_config', return_value=mock_fiber_config), \
             patch('services.patterns.service_base.ServiceBase._load_schema', return_value=None), \
             patch('services.processor.main.setup_otel'):

            processor = DASProcessor()
            processor.logger = MagicMock()

            # First call
            pipelines1 = processor._get_fiber_pipelines("test_fiber")

            # Simulate config change by creating new config object
            new_fiber_config = FiberConfig(
                fiber_id="test_fiber",
                input_topic="das.raw.test_fiber",
                total_channels=1000,
                sampling_rate_hz=50.0,
                sections=[
                    SectionConfig(
                        name="section1",
                        channel_start=0,
                        channel_stop=150,  # Changed
                        model="test_model",
                        pipeline=[],
                    ),
                ],
            )

            # Update the mock to return new config
            with patch('services.processor.main.get_fiber_config', return_value=new_fiber_config):
                pipelines2 = processor._get_fiber_pipelines("test_fiber")

            # Should have different pipelines (rebuilt)
            assert pipelines1 is not pipelines2
            assert len(pipelines2) == 1  # Only 1 section now

    def test_returns_empty_for_unknown_fiber(self, mock_service_config):
        """Should return empty dict for unknown fiber."""
        with patch('services.processor.main.load_service_config', return_value=mock_service_config), \
             patch('services.processor.main.get_service_name', return_value='das-processor'), \
             patch('services.processor.main.get_fiber_config', side_effect=KeyError("unknown")), \
             patch('services.patterns.service_base.ServiceBase._load_schema', return_value=None), \
             patch('services.processor.main.setup_otel'):

            processor = DASProcessor()
            processor.logger = MagicMock()

            pipelines = processor._get_fiber_pipelines("unknown_fiber")
            assert pipelines == {}
