"""Tests for service configuration loader."""

import os
from unittest.mock import MagicMock, patch

import pytest

from config.service_loader import (
    _build_outputs,
    _get_input_config,
    get_service_name,
    load_service_config,
)


class TestBuildOutputs:
    """Test output configuration building."""

    def test_processor_outputs(self):
        """Processor should have single 'default' output."""
        topics = {"processed": "das.processed"}
        schemas = {"output_key": "key.avsc", "output_value": "value.avsc"}

        outputs = _build_outputs("processor", topics, schemas)

        assert "default" in outputs
        assert outputs["default"].topic == "das.processed"
        assert outputs["default"].key_schema_file == "key.avsc"
        assert outputs["default"].value_schema_file == "value.avsc"

    def test_ai_engine_outputs(self):
        """AI engine should have 'speed' and 'counting' outputs."""
        topics = {"speeds": "das.speeds", "counts": "das.counts"}
        schemas = {
            "speed_key": "speed_key.avsc",
            "speed_value": "speed_value.avsc",
            "count_key": "count_key.avsc",
            "count_value": "count_value.avsc",
        }

        outputs = _build_outputs("ai_engine", topics, schemas)

        assert "speed" in outputs
        assert "counting" in outputs
        assert outputs["speed"].topic == "das.speeds"
        assert outputs["counting"].topic == "das.counts"

    def test_unknown_service_type_raises(self):
        """Unknown service type should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown service type"):
            _build_outputs("unknown_service", {}, {})

    def test_uses_defaults_when_topics_missing(self):
        """Should use default topic names when not specified."""
        outputs = _build_outputs("processor", {}, {})

        assert outputs["default"].topic == "das.processed"


class TestGetInputConfig:
    """Test input configuration retrieval."""

    def test_processor_uses_pattern(self):
        """Processor should use topic pattern, not specific topic."""
        topics = {"raw_pattern": "^das\\.raw\\..+$"}

        topic, pattern = _get_input_config("processor", topics)

        assert topic is None
        assert pattern == "^das\\.raw\\..+$"

    def test_ai_engine_uses_topic(self):
        """AI engine should use specific topic, not pattern."""
        topics = {"processed": "das.processed"}

        topic, pattern = _get_input_config("ai_engine", topics)

        assert topic == "das.processed"
        assert pattern is None

    def test_unknown_service_type_raises(self):
        """Unknown service type should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown service type"):
            _get_input_config("unknown_service", {})

    def test_uses_defaults_when_topics_missing(self):
        """Should use default values when topics not specified."""
        topic, pattern = _get_input_config("processor", {})
        assert pattern == "^das\\.raw\\..+$"

        topic, pattern = _get_input_config("ai_engine", {})
        assert topic == "das.processed"


class TestGetServiceName:
    """Test service name retrieval."""

    @patch("config.service_loader.FiberConfigManager")
    def test_returns_configured_name(self, mock_manager_class):
        """Should return name from config if specified."""
        mock_manager = MagicMock()
        mock_manager.get_raw_config.return_value = {
            "services": {
                "processor": {"name": "custom-processor-name"}
            }
        }
        mock_manager_class.return_value = mock_manager

        name = get_service_name("processor")

        assert name == "custom-processor-name"

    @patch("config.service_loader.FiberConfigManager")
    def test_returns_default_name(self, mock_manager_class):
        """Should return default name if not configured."""
        mock_manager = MagicMock()
        mock_manager.get_raw_config.return_value = {"services": {}}
        mock_manager_class.return_value = mock_manager

        assert get_service_name("processor") == "das-processor"
        assert get_service_name("ai_engine") == "ai-engine"

    @patch("config.service_loader.FiberConfigManager")
    def test_unknown_service_returns_type_as_name(self, mock_manager_class):
        """Unknown service should return the type itself as name."""
        mock_manager = MagicMock()
        mock_manager.get_raw_config.return_value = {"services": {}}
        mock_manager_class.return_value = mock_manager

        name = get_service_name("unknown_type")

        assert name == "unknown_type"


class TestLoadServiceConfig:
    """Test full service configuration loading."""

    @patch("config.service_loader.FiberConfigManager")
    def test_loads_processor_config(self, mock_manager_class):
        """Should load complete processor configuration."""
        mock_manager = MagicMock()
        mock_manager.get_raw_config.return_value = {
            "service_defaults": {
                "kafka_bootstrap_servers": "kafka:9092",
                "schema_registry_url": "http://registry:8081",
                "topics": {
                    "raw_pattern": "^das\\.raw\\..+$",
                    "processed": "das.processed",
                    "dlq": "das.dlq",
                },
                "schemas": {
                    "processor": {
                        "output_key": "key.avsc",
                        "output_value": "value.avsc",
                    }
                },
                "producer": {
                    "flush_threshold": 5,
                    "linger_ms": 50,
                },
            },
            "services": {
                "processor": {
                    "max_concurrent_messages": 100,
                }
            },
        }
        mock_manager_class.return_value = mock_manager

        config = load_service_config("processor")

        assert config.input_topic_pattern == "^das\\.raw\\..+$"
        assert config.kafka_bootstrap_servers == "kafka:9092"
        assert config.max_concurrent_messages == 100
        assert config.producer_flush_threshold == 5
        assert "default" in config.outputs

    @patch("config.service_loader.FiberConfigManager")
    def test_env_vars_override_config(self, mock_manager_class):
        """Environment variables should override config file."""
        mock_manager = MagicMock()
        mock_manager.get_raw_config.return_value = {
            "service_defaults": {
                "kafka_bootstrap_servers": "kafka:9092",
            },
            "services": {},
        }
        mock_manager_class.return_value = mock_manager

        with patch.dict(os.environ, {"KAFKA_BOOTSTRAP_SERVERS": "custom-kafka:9092"}):
            config = load_service_config("processor")

        assert config.kafka_bootstrap_servers == "custom-kafka:9092"

    @patch("config.service_loader.FiberConfigManager")
    def test_loads_ai_engine_config(self, mock_manager_class):
        """Should load complete AI engine configuration."""
        mock_manager = MagicMock()
        mock_manager.get_raw_config.return_value = {
            "service_defaults": {
                "topics": {
                    "processed": "das.processed",
                    "speeds": "das.speeds",
                    "counts": "das.counts",
                },
                "schemas": {
                    "ai_engine": {
                        "speed_key": "sk.avsc",
                        "speed_value": "sv.avsc",
                        "count_key": "ck.avsc",
                        "count_value": "cv.avsc",
                    }
                },
            },
            "services": {
                "ai_engine": {
                    "buffer_timeout_seconds": 120.0,
                    "max_active_buffers": 20,
                }
            },
        }
        mock_manager_class.return_value = mock_manager

        config = load_service_config("ai_engine")

        assert config.input_topic == "das.processed"
        assert config.buffer_timeout == 120.0
        assert config.max_active_buffers == 20
        assert "speed" in config.outputs
        assert "counting" in config.outputs
