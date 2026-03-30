"""Central fiber/section/model configuration loader with hot-reload.

Config changes auto-reload without service restart.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).parent / "fibers.yaml"


@dataclass(frozen=True)
class PipelineStepConfig:
    """Configuration for a single processing step."""

    step: str
    params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> PipelineStepConfig:
        return cls(
            step=data.get("step", ""),
            params=data.get("params", {}),
        )


@dataclass(frozen=True)
class SectionConfig:
    """Configuration for a fiber section."""

    name: str
    channel_start: int
    channel_stop: int
    model: str
    pipeline: list[PipelineStepConfig]

    @classmethod
    def from_dict(cls, data: dict, defaults: dict) -> SectionConfig:
        channels = data.get("channels", [0, 1000])

        # Build pipeline from section config or defaults
        pipeline_data = data.get("pipeline", defaults.get("pipeline", []))
        pipeline = [PipelineStepConfig.from_dict(p) for p in pipeline_data]

        return cls(
            name=data["name"],
            channel_start=channels[0],
            channel_stop=channels[1],
            model=data.get("model", defaults.get("model", "default")),
            pipeline=pipeline,
        )

    @property
    def channel_count(self) -> int:
        return self.channel_stop - self.channel_start


@dataclass(frozen=True)
class InferenceConfig:
    """AI model inference parameters."""

    sampling_rate_hz: float = 10.4167
    window_seconds: int = 30
    channels_per_section: int = 9
    gauge_meters: float = 15.3846
    bidirectional_rnn: bool = True
    time_overlap_ratio: float = 0.5

    @classmethod
    def from_dict(cls, data: dict) -> InferenceConfig:
        return cls(
            sampling_rate_hz=data.get("sampling_rate_hz", 10.4167),
            window_seconds=data.get("window_seconds", 30),
            channels_per_section=data.get("channels_per_section", 9),
            gauge_meters=data.get("gauge_meters", 15.3846),
            bidirectional_rnn=data.get("bidirectional_rnn", True),
            time_overlap_ratio=data.get("time_overlap_ratio", 0.5),
        )

    @property
    def samples_per_window(self) -> int:
        return int(self.window_seconds * self.sampling_rate_hz)

    @property
    def step_size(self) -> int:
        """Step size for rolling buffer derived from overlap ratio.

        With 50% overlap: window=300, step=150 (process 2x more often).
        The overlap ensures seamless window handoff with no gaps.
        """
        return int(self.samples_per_window * (1 - self.time_overlap_ratio))


@dataclass(frozen=True)
class SpeedDetectionConfig:
    """Speed detection parameters."""

    min_speed_kmh: float = 20.0
    max_speed_kmh: float = 120.0
    correlation_threshold: float = 500.0
    time_overlap_ratio: float = 0.5
    glrt_window: int = 20
    use_calibration: bool = False
    bidirectional_detection: bool = True
    speed_glrt_factor: float = 1.0
    speed_weighting: str = "median"
    speed_positive_glrt_only: bool = False
    min_vehicle_duration_s: float = 0.3

    @classmethod
    def from_dict(cls, data: dict) -> SpeedDetectionConfig:
        return cls(
            min_speed_kmh=data.get("min_speed_kmh", 20.0),
            max_speed_kmh=data.get("max_speed_kmh", 120.0),
            correlation_threshold=data.get("correlation_threshold", 500.0),
            time_overlap_ratio=data.get("time_overlap_ratio", 0.5),
            glrt_window=data.get("glrt_window", 20),
            use_calibration=data.get("use_calibration", False),
            bidirectional_detection=data.get("bidirectional_detection", True),
            speed_glrt_factor=data.get("speed_glrt_factor", 1.0),
            speed_weighting=data.get("speed_weighting", "median"),
            speed_positive_glrt_only=data.get("speed_positive_glrt_only", False),
            min_vehicle_duration_s=data.get("min_vehicle_duration_s", 0.3),
        )


@dataclass(frozen=True)
class CountingConfig:
    """Vehicle counting configuration."""

    enabled: bool = True
    window_seconds: int = 30
    classify_threshold_factor: float = 50.0
    min_peak_distance_s: float = 1.2
    model_path: str = ""
    thresholds_path: str = ""
    mean_std_path: str = ""
    truck_ratio_for_split: float = 2.0
    time_window_duration: float = 360.0
    corr_threshold: float = 500.0

    @classmethod
    def from_dict(cls, data: dict | None) -> CountingConfig:
        if not data:
            return cls(enabled=False)
        return cls(
            enabled=data.get("enabled", True),
            window_seconds=data.get("window_seconds", 30),
            classify_threshold_factor=data.get("classify_threshold_factor", 50.0),
            min_peak_distance_s=data.get("min_peak_distance_s", 1.2),
            model_path=data.get("model_path", ""),
            thresholds_path=data.get("thresholds_path", ""),
            mean_std_path=data.get("mean_std_path", ""),
            truck_ratio_for_split=data.get("truck_ratio_for_split", 2.0),
            time_window_duration=data.get("time_window_duration", 360.0),
            corr_threshold=data.get("corr_threshold", 500.0),
        )

    def samples_per_window(self, sampling_rate_hz: float) -> int:
        return int(self.window_seconds * sampling_rate_hz)


@dataclass(frozen=True)
class VisualizationConfig:
    """Visualization generation parameters."""

    enabled: bool = False
    interval_seconds: int = 300
    output_dir: str = "/app/visualizations"

    @classmethod
    def from_dict(cls, data: dict | None) -> VisualizationConfig:
        if not data:
            return cls(enabled=False)
        return cls(
            enabled=data.get("enabled", False),
            interval_seconds=data.get("interval_seconds", 300),
            output_dir=data.get("output_dir", "/app/visualizations"),
        )


@dataclass(frozen=True)
class ModelSpec:
    """Complete model specification."""

    name: str
    path: str
    exp_name: str
    version: str
    model_type: str
    inference: InferenceConfig
    speed_detection: SpeedDetectionConfig
    counting: CountingConfig
    visualization: VisualizationConfig = field(default_factory=lambda: VisualizationConfig())
    fiber_id: str = ""

    @classmethod
    def from_dict(cls, name: str, data: dict, model_defaults: dict | None = None) -> ModelSpec:
        """Parse model spec from dict, merging with model_defaults if provided."""
        defaults = model_defaults or {}

        def _merge(section: str) -> dict:
            """Merge per-model section with defaults (model overrides default)."""
            base = dict(defaults.get(section, {}))
            base.update(data.get(section, {}))
            return base

        speed_det = _merge("speed_detection")
        inference = _merge("inference")
        # Propagate time_overlap_ratio to inference config for step_size calculation
        if "time_overlap_ratio" not in inference and "time_overlap_ratio" in speed_det:
            inference["time_overlap_ratio"] = speed_det["time_overlap_ratio"]

        return cls(
            name=name,
            path=data.get("path", defaults.get("path", "")),
            exp_name=data.get("exp_name", defaults.get("exp_name", "")),
            version=data.get("version", defaults.get("version", "best")),
            model_type=data.get("type", defaults.get("type", "dtan")),
            inference=InferenceConfig.from_dict(inference),
            speed_detection=SpeedDetectionConfig.from_dict(speed_det),
            counting=CountingConfig.from_dict(_merge("counting") or None),
            visualization=VisualizationConfig.from_dict(_merge("visualization") or None),
            fiber_id=data.get("fiber_id", defaults.get("fiber_id", "")),
        )

    # Backwards compatibility properties
    @property
    def params(self) -> InferenceConfig:
        """Alias for inference config (backwards compatibility)."""
        return self.inference


@dataclass
class FiberConfig:
    """Complete fiber configuration with sections."""

    fiber_id: str
    input_topic: str
    total_channels: int
    sampling_rate_hz: float
    sections: list[SectionConfig]

    @classmethod
    def from_dict(cls, fiber_id: str, data: dict, defaults: dict) -> FiberConfig:
        sections_data = data.get("sections", [])
        sections = [SectionConfig.from_dict(s, defaults) for s in sections_data]
        return cls(
            fiber_id=fiber_id,
            input_topic=data.get("input_topic", f"das.raw.{fiber_id}"),
            total_channels=data.get("total_channels", 3000),
            sampling_rate_hz=data.get("sampling_rate_hz", 50.0),
            sections=sections,
        )

    def get_section_for_channel(self, channel: int) -> SectionConfig | None:
        """Find which section a channel belongs to."""
        for section in self.sections:
            if section.channel_start <= channel < section.channel_stop:
                return section
        return None


@dataclass
class FibersConfig:
    """Complete configuration from fibers.yaml."""

    fibers: dict[str, FiberConfig]
    models: dict[str, ModelSpec]
    defaults: dict


class FiberConfigManager:
    """Thread-safe singleton config manager with auto-reload."""

    _instance: FiberConfigManager | None = None
    _lock = threading.Lock()
    _initialized: bool = False

    def __new__(cls, config_path: Path | None = None) -> FiberConfigManager:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_path: Path | None = None):
        if self._initialized:
            return

        self._path = config_path or Path(os.getenv("FIBER_CONFIG_PATH", str(DEFAULT_CONFIG_PATH)))
        self._config: FibersConfig | None = None
        self._mtime: float = 0
        self._last_mtime_check: float = 0
        self._mtime_check_interval: float = 5.0  # seconds between filesystem polls
        self._reload_lock = threading.Lock()
        self._initialized = True

        # Initial load
        self._reload()
        logger.info(f"FiberConfigManager initialized from {self._path}")

    def _reload(self) -> None:
        """Reload config from YAML file."""
        try:
            with open(self._path) as f:
                raw = yaml.safe_load(f)

            # Store raw config for service_loader access
            self._raw_config = raw

            defaults = raw.get("defaults", {})
            model_defaults = raw.get("model_defaults", {})

            # Parse fibers
            fibers = {}
            for fiber_id, fiber_data in raw.get("fibers", {}).items():
                fibers[fiber_id] = FiberConfig.from_dict(fiber_id, fiber_data, defaults)

            # Parse models (merge with model_defaults)
            models = {}
            for model_name, model_data in raw.get("models", {}).items():
                models[model_name] = ModelSpec.from_dict(model_name, model_data, model_defaults)

            self._config = FibersConfig(
                fibers=fibers,
                models=models,
                defaults=defaults,
            )
            self._mtime = os.path.getmtime(self._path)

            logger.info(f"Config loaded: {len(fibers)} fibers, {len(models)} models")
        except Exception as e:
            logger.error(f"Failed to load config from {self._path}: {e}")
            raise

    def _check_reload(self) -> None:
        """Check if config file changed and reload if needed.

        Rate-limited to poll the filesystem at most once every _mtime_check_interval
        seconds to avoid excessive stat() calls on hot paths.
        """
        now = time.monotonic()
        if (now - self._last_mtime_check) < self._mtime_check_interval:
            return
        self._last_mtime_check = now

        try:
            mtime = os.path.getmtime(self._path)
            if mtime > self._mtime:
                with self._reload_lock:
                    # Double-check after acquiring lock
                    if os.path.getmtime(self._path) > self._mtime:
                        logger.info("Config file changed, reloading...")
                        self._reload()
        except Exception as e:
            logger.warning(f"Error checking config file: {e}")

    def get_fiber(self, fiber_id: str) -> FiberConfig:
        """Get fiber configuration by ID."""
        self._check_reload()
        if self._config is None:
            raise RuntimeError("FiberConfigManager: config not loaded")
        if fiber_id not in self._config.fibers:
            available = list(self._config.fibers.keys())
            raise KeyError(f"Unknown fiber_id '{fiber_id}'. Available: {available}")
        return self._config.fibers[fiber_id]

    def get_model(self, model_name: str) -> ModelSpec:
        """Get model specification by name."""
        self._check_reload()
        if self._config is None:
            raise RuntimeError("FiberConfigManager: config not loaded")
        if model_name not in self._config.models:
            available = list(self._config.models.keys())
            raise KeyError(f"Unknown model '{model_name}'. Available: {available}")
        return self._config.models[model_name]

    def get_all_fibers(self) -> dict[str, FiberConfig]:
        """Get all fiber configurations."""
        self._check_reload()
        if self._config is None:
            raise RuntimeError("FiberConfigManager: config not loaded")
        return self._config.fibers.copy()

    def get_all_models(self) -> dict[str, ModelSpec]:
        """Get all model specifications."""
        self._check_reload()
        if self._config is None:
            raise RuntimeError("FiberConfigManager: config not loaded")
        return self._config.models.copy()

    def get_input_topics(self) -> list[str]:
        """Get list of all input topics for subscription."""
        self._check_reload()
        if self._config is None:
            raise RuntimeError("FiberConfigManager: config not loaded")
        return [f.input_topic for f in self._config.fibers.values()]

    def get_fiber_by_topic(self, topic: str) -> FiberConfig | None:
        """Get fiber config by its input topic."""
        self._check_reload()
        if self._config is None:
            raise RuntimeError("FiberConfigManager: config not loaded")
        for fiber in self._config.fibers.values():
            if fiber.input_topic == topic:
                return fiber
        return None

    def extract_fiber_id_from_topic(self, topic: str) -> str:
        """Extract fiber_id from topic name: das.raw.carros -> carros"""
        return topic.split(".")[-1]

    def get_raw_config(self) -> dict[str, Any]:
        """Get raw YAML config dict for service_defaults access.

        Used by service_loader to access infrastructure settings
        (service_defaults, services sections). Processing logic should
        use typed methods like get_fiber() and get_model().
        """
        self._check_reload()
        return dict(self._raw_config)

    def get_default_model_name(self) -> str:
        """Get the default model name from config defaults."""
        self._check_reload()
        if self._config is None:
            raise RuntimeError("FiberConfigManager: config not loaded")
        return str(self._config.defaults.get("model", "dtan_unified"))

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance so the next access reloads from disk.

        Intended for testing only -- allows tests to force a fresh config reload
        (e.g. after swapping in a test fixture YAML file).
        """
        with cls._lock:
            cls._instance = None
        # Also clear the module-level convenience reference
        global _manager
        _manager = None


_manager: FiberConfigManager | None = None


def _get_manager() -> FiberConfigManager:
    """Get or create the singleton manager."""
    global _manager
    if _manager is None:
        _manager = FiberConfigManager()
    return _manager


def get_fiber_config(fiber_id: str) -> FiberConfig:
    """Get fiber configuration by ID (auto-reloads on file change)."""
    return _get_manager().get_fiber(fiber_id)


def get_model_spec(model_name: str) -> ModelSpec:
    """Get model specification by name (auto-reloads on file change)."""
    return _get_manager().get_model(model_name)


def get_all_fiber_configs() -> dict[str, FiberConfig]:
    """Get all fiber configurations."""
    return _get_manager().get_all_fibers()


def get_all_model_specs() -> dict[str, ModelSpec]:
    """Get all model specifications."""
    return _get_manager().get_all_models()


def get_input_topics() -> list[str]:
    """Get list of all configured input topics."""
    return _get_manager().get_input_topics()


def get_fiber_by_topic(topic: str) -> FiberConfig | None:
    """Get fiber config by its Kafka input topic."""
    return _get_manager().get_fiber_by_topic(topic)


def extract_fiber_id(topic: str) -> str:
    """Extract fiber_id from Kafka topic name."""
    return _get_manager().extract_fiber_id_from_topic(topic)


def get_raw_config() -> dict:
    """Get raw YAML config for service infrastructure settings."""
    return _get_manager().get_raw_config()


def get_default_model_name() -> str:
    """Get the default model name from config defaults."""
    return _get_manager().get_default_model_name()
