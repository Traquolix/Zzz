"""Tests for FiberConfigManager: hot-reload, rate limiting, parse errors."""

import time

import pytest
import yaml

from config.fiber_config import FiberConfigManager


@pytest.fixture(autouse=True)
def reset_singleton():
    """Ensure clean singleton state for each test."""
    FiberConfigManager.reset()
    yield
    FiberConfigManager.reset()


@pytest.fixture
def config_file(tmp_path):
    """Create a minimal fibers.yaml for testing."""
    config = {
        "defaults": {"model": "test_model"},
        "model_defaults": {
            "path": "models/test",
            "exp_name": "test",
            "version": "best",
            "type": "dtan",
            "inference": {"sampling_rate_hz": 10.0, "channels_per_section": 9},
            "speed_detection": {"correlation_threshold": 500.0},
        },
        "fibers": {
            "fiber1": {
                "input_topic": "das.raw.fiber1",
                "total_channels": 100,
                "sampling_rate_hz": 50.0,
                "sections": [{"name": "section_a", "channels": [0, 50], "model": "test_model"}],
            }
        },
        "models": {
            "test_model": {
                "path": "models/test",
                "exp_name": "test",
                "version": "best",
            }
        },
    }
    path = tmp_path / "fibers.yaml"
    path.write_text(yaml.dump(config))
    return path, config


class TestBasicLoading:
    def test_loads_fibers(self, config_file):
        path, _ = config_file
        mgr = FiberConfigManager(config_path=path)

        fiber = mgr.get_fiber("fiber1")
        assert fiber.fiber_id == "fiber1"
        assert fiber.input_topic == "das.raw.fiber1"
        assert fiber.sampling_rate_hz == 50.0
        assert len(fiber.sections) == 1

    def test_loads_models(self, config_file):
        path, _ = config_file
        mgr = FiberConfigManager(config_path=path)

        model = mgr.get_model("test_model")
        assert model.name == "test_model"
        assert model.exp_name == "test"

    def test_unknown_fiber_raises(self, config_file):
        path, _ = config_file
        mgr = FiberConfigManager(config_path=path)

        with pytest.raises(KeyError, match="no_such_fiber"):
            mgr.get_fiber("no_such_fiber")

    def test_unknown_model_raises(self, config_file):
        path, _ = config_file
        mgr = FiberConfigManager(config_path=path)

        with pytest.raises(KeyError, match="no_such_model"):
            mgr.get_model("no_such_model")


class TestHotReload:
    def test_reloads_on_file_change(self, config_file):
        path, config = config_file
        mgr = FiberConfigManager(config_path=path)

        assert mgr.get_fiber("fiber1").total_channels == 100

        # Modify config and touch the file
        config["fibers"]["fiber1"]["total_channels"] = 200
        path.write_text(yaml.dump(config))

        # Force mtime check by resetting the interval timer
        mgr._last_mtime_check = 0

        assert mgr.get_fiber("fiber1").total_channels == 200

    def test_rate_limits_mtime_checks(self, config_file):
        path, _ = config_file
        mgr = FiberConfigManager(config_path=path)
        mgr._mtime_check_interval = 999  # Very long interval

        # Record mtime check time
        mgr._last_mtime_check = time.monotonic()

        # Access should NOT trigger reload (within interval)
        original_mtime = mgr._mtime
        mgr.get_fiber("fiber1")  # Should skip check
        assert mgr._mtime == original_mtime


class TestParseErrors:
    def test_invalid_yaml_raises(self, tmp_path):
        path = tmp_path / "bad.yaml"
        path.write_text("{{invalid yaml content")

        with pytest.raises(Exception):
            FiberConfigManager(config_path=path)

    def test_missing_file_raises(self, tmp_path):
        path = tmp_path / "nonexistent.yaml"

        with pytest.raises(Exception):
            FiberConfigManager(config_path=path)


class TestSectionConfig:
    def test_section_channel_range(self, config_file):
        path, _ = config_file
        mgr = FiberConfigManager(config_path=path)

        fiber = mgr.get_fiber("fiber1")
        section = fiber.sections[0]
        assert section.channel_start == 0
        assert section.channel_stop == 50
        assert section.channel_count == 50

    def test_get_section_for_channel(self, config_file):
        path, _ = config_file
        mgr = FiberConfigManager(config_path=path)

        fiber = mgr.get_fiber("fiber1")
        assert fiber.get_section_for_channel(25) is not None
        assert fiber.get_section_for_channel(25).name == "section_a"
        assert fiber.get_section_for_channel(99) is None


class TestUtilityMethods:
    def test_get_input_topics(self, config_file):
        path, _ = config_file
        mgr = FiberConfigManager(config_path=path)

        topics = mgr.get_input_topics()
        assert "das.raw.fiber1" in topics

    def test_get_fiber_by_topic(self, config_file):
        path, _ = config_file
        mgr = FiberConfigManager(config_path=path)

        fiber = mgr.get_fiber_by_topic("das.raw.fiber1")
        assert fiber is not None
        assert fiber.fiber_id == "fiber1"

    def test_extract_fiber_id_from_topic(self, config_file):
        path, _ = config_file
        mgr = FiberConfigManager(config_path=path)

        assert mgr.extract_fiber_id_from_topic("das.raw.carros") == "carros"

    def test_get_default_model_name(self, config_file):
        path, _ = config_file
        mgr = FiberConfigManager(config_path=path)

        assert mgr.get_default_model_name() == "test_model"
