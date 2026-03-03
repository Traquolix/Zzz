"""Tests for FiberConfigManager and config loading."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from config.fiber_config import (
    FiberConfigManager,
    InferenceConfig,
    ModelSpec,
    SectionConfig,
)


@pytest.fixture
def sample_config_yaml():
    """Sample fibers.yaml content."""
    return {
        "defaults": {
            "model": "test_model",
            "pipeline": [
                {"step": "bandpass_filter", "params": {"low_freq_hz": 0.1, "high_freq_hz": 2.0}},
                {"step": "temporal_decimation", "params": {"factor": 5}},
            ],
        },
        "fibers": {
            "test_fiber": {
                "input_topic": "das.raw.test",
                "total_channels": 1000,
                "sampling_rate_hz": 50.0,
                "sections": [
                    {
                        "name": "section_a",
                        "channels": [0, 500],
                        "model": "model_a",
                    },
                    {
                        "name": "section_b",
                        "channels": [500, 1000],
                        "model": "model_b",
                    },
                ],
            },
        },
        "models": {
            "test_model": {
                "path": "/models/test",
                "exp_name": "test_exp",
                "version": "best",
                "type": "dtan",
                "inference": {
                    "sampling_rate_hz": 10.0,
                    "window_seconds": 30,
                    "channels_per_section": 9,
                    "gauge_meters": 10,
                },
                "speed_detection": {
                    "min_speed_kmh": 20.0,
                    "max_speed_kmh": 120.0,
                },
            },
        },
    }


@pytest.fixture
def temp_config_file(sample_config_yaml):
    """Create a temporary config file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(sample_config_yaml, f)
        temp_path = f.name

    yield Path(temp_path)

    os.unlink(temp_path)


class TestFiberConfigLoading:
    """Test config loading from YAML."""

    def test_loads_fiber_by_id(self, temp_config_file):
        """Should load fiber config by ID."""
        # Reset singleton for testing.
        FiberConfigManager._instance = None

        manager = FiberConfigManager(temp_config_file)
        fiber = manager.get_fiber("test_fiber")

        assert fiber.fiber_id == "test_fiber"
        assert fiber.input_topic == "das.raw.test"
        assert fiber.total_channels == 1000
        assert fiber.sampling_rate_hz == 50.0

    def test_loads_fiber_sections(self, temp_config_file):
        """Should load fiber sections."""
        FiberConfigManager._instance = None

        manager = FiberConfigManager(temp_config_file)
        fiber = manager.get_fiber("test_fiber")

        assert len(fiber.sections) == 2
        assert fiber.sections[0].name == "section_a"
        assert fiber.sections[0].channel_start == 0
        assert fiber.sections[0].channel_stop == 500
        assert fiber.sections[1].name == "section_b"

    def test_raises_for_unknown_fiber(self, temp_config_file):
        """Should raise KeyError for unknown fiber ID."""
        FiberConfigManager._instance = None

        manager = FiberConfigManager(temp_config_file)

        with pytest.raises(KeyError, match="Unknown fiber_id"):
            manager.get_fiber("nonexistent")

    def test_loads_model_by_name(self, temp_config_file):
        """Should load model spec by name."""
        FiberConfigManager._instance = None

        manager = FiberConfigManager(temp_config_file)
        model = manager.get_model("test_model")

        assert model.name == "test_model"
        assert model.path == "/models/test"
        assert model.inference.sampling_rate_hz == 10.0
        assert model.inference.window_seconds == 30

    def test_raises_for_unknown_model(self, temp_config_file):
        """Should raise KeyError for unknown model name."""
        FiberConfigManager._instance = None

        manager = FiberConfigManager(temp_config_file)

        with pytest.raises(KeyError, match="Unknown model"):
            manager.get_model("nonexistent")


class TestConfigHotReload:
    """Test config hot-reload on file change."""

    def test_detects_file_change(self, temp_config_file, sample_config_yaml):
        """Should reload config when file is modified."""
        FiberConfigManager._instance = None

        manager = FiberConfigManager(temp_config_file)
        fiber1 = manager.get_fiber("test_fiber")
        assert fiber1.total_channels == 1000

        sample_config_yaml["fibers"]["test_fiber"]["total_channels"] = 2000
        with open(temp_config_file, "w") as f:
            yaml.dump(sample_config_yaml, f)

        os.utime(temp_config_file, None)

        # Reset the rate limiter to force a reload check
        manager._last_mtime_check = 0

        fiber2 = manager.get_fiber("test_fiber")
        assert fiber2.total_channels == 2000


class TestSectionConfig:
    """Test SectionConfig parsing."""

    def test_parses_section_from_dict(self):
        """Should parse section from dict."""
        data = {
            "name": "test_section",
            "channels": [100, 200],
            "model": "test_model",
            "pipeline": [
                {"step": "temporal_decimation", "params": {"factor": 10}},
            ],
        }
        defaults = {"model": "default_model", "pipeline": []}

        section = SectionConfig.from_dict(data, defaults)

        assert section.name == "test_section"
        assert section.channel_start == 100
        assert section.channel_stop == 200
        assert section.model == "test_model"
        assert len(section.pipeline) == 1
        assert section.pipeline[0].step == "temporal_decimation"

    def test_uses_defaults_when_not_specified(self):
        """Should use defaults for missing fields."""
        data = {"name": "minimal", "channels": [0, 100]}
        defaults = {
            "model": "default_model",
            "pipeline": [{"step": "bandpass_filter", "params": {}}],
        }

        section = SectionConfig.from_dict(data, defaults)

        assert section.model == "default_model"
        assert len(section.pipeline) == 1


class TestFiberConfigHelpers:
    """Test FiberConfig helper methods."""

    def test_get_section_for_channel(self, temp_config_file):
        """Should find section containing a channel."""
        FiberConfigManager._instance = None

        manager = FiberConfigManager(temp_config_file)
        fiber = manager.get_fiber("test_fiber")

        section_a = fiber.get_section_for_channel(250)
        assert section_a.name == "section_a"

        section_b = fiber.get_section_for_channel(750)
        assert section_b.name == "section_b"

    def test_get_section_for_channel_not_found(self, temp_config_file):
        """Should return None for channel not in any section."""
        FiberConfigManager._instance = None

        manager = FiberConfigManager(temp_config_file)
        fiber = manager.get_fiber("test_fiber")

        result = fiber.get_section_for_channel(5000)
        assert result is None


class TestModelSpec:
    """Test ModelSpec parsing."""

    def test_parses_model_from_dict(self):
        """Should parse model spec from dict."""
        data = {
            "path": "/models/test",
            "exp_name": "experiment",
            "version": "v1",
            "type": "dtan",
            "inference": {
                "sampling_rate_hz": 10.0,
                "window_seconds": 30,
                "channels_per_section": 9,
            },
            "speed_detection": {
                "min_speed_kmh": 20.0,
                "max_speed_kmh": 120.0,
            },
            "counting": {
                "enabled": True,
                "window_seconds": 30,
            },
        }

        model = ModelSpec.from_dict("test_model", data)

        assert model.name == "test_model"
        assert model.path == "/models/test"
        assert model.inference.samples_per_window == 300
        assert model.speed_detection.min_speed_kmh == 20.0
        assert model.counting.enabled is True

    def test_model_defaults_merging(self):
        """Model-specific values should override model_defaults."""
        model_defaults = {
            "path": "/default/path",
            "exp_name": "default_exp",
            "version": "best",
            "type": "dtan",
            "inference": {
                "sampling_rate_hz": 10.0,
                "window_seconds": 30,
                "channels_per_section": 9,
                "bidirectional_rnn": True,
            },
            "speed_detection": {
                "correlation_threshold": 500.0,
                "time_overlap_ratio": 0.5,
            },
            "counting": {
                "enabled": True,
            },
        }
        # Model only specifies fiber_id and one override
        data = {
            "fiber_id": "carros",
            "speed_detection": {
                "use_calibration": True,
            },
        }

        model = ModelSpec.from_dict("test", data, model_defaults)

        assert model.fiber_id == "carros"
        assert model.path == "/default/path"
        assert model.exp_name == "default_exp"
        assert model.inference.bidirectional_rnn is True
        # Merged: default threshold + model override
        assert model.speed_detection.correlation_threshold == 500.0
        assert model.speed_detection.use_calibration is True
        assert model.speed_detection.time_overlap_ratio == 0.5


class TestStepSize:
    """Test step_size derived from overlap ratio."""

    def test_step_size_with_half_overlap(self):
        """window=300, overlap=0.5 -> step=150."""
        config = InferenceConfig(window_seconds=30, sampling_rate_hz=10.0, time_overlap_ratio=0.5)
        assert config.step_size == 150

    def test_step_size_with_sixth_overlap(self):
        """window=300, overlap=1/6 -> step=250."""
        config = InferenceConfig(window_seconds=30, sampling_rate_hz=10.0, time_overlap_ratio=1/6)
        assert config.step_size == 250

    def test_step_size_with_zero_overlap(self):
        """window=300, overlap=0 -> step=300."""
        config = InferenceConfig(window_seconds=30, sampling_rate_hz=10.0, time_overlap_ratio=0.0)
        assert config.step_size == 300

    def test_overlap_ratio_propagated_from_speed_detection(self):
        """time_overlap_ratio from speed_detection should propagate to inference."""
        model_defaults = {
            "speed_detection": {"time_overlap_ratio": 0.5},
            "inference": {"sampling_rate_hz": 10.0, "window_seconds": 30},
        }
        data = {"fiber_id": "test"}
        model = ModelSpec.from_dict("test", data, model_defaults)
        assert model.inference.time_overlap_ratio == 0.5
        assert model.inference.step_size == 150
