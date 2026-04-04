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
class InstrumentParams:
    """DAS instrument parameters from the .params Kafka topic."""

    n_channels: int
    sampling_rate_hz: float
    gauge_length: float
    dx: float
    data_scale: float
    unit: str
    schema_version: str
    experiment: str
    instrument: str
    trusted_time_source: bool
    measurement_start_time: str

    @classmethod
    def from_kafka_message(cls, data: dict) -> InstrumentParams:
        dt = data["dt"]
        if dt <= 0:
            raise ValueError(f"Invalid dt={dt} in instrument params (must be > 0)")
        return cls(
            n_channels=data["nChannels"],
            sampling_rate_hz=1.0 / dt,
            gauge_length=data.get("gaugeLength", 0.0),
            dx=data.get("dx", 0.0),
            data_scale=data.get("dataScale", 1.0),
            unit=data.get("unit", ""),
            schema_version=data.get("schemaVersion", ""),
            experiment=data.get("experiment", ""),
            instrument=data.get("instrument", ""),
            trusted_time_source=data.get("trustedTimeSource", False),
            measurement_start_time=data.get("measurementStartTime", ""),
        )


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
    samples_per_message: int = 1

    @classmethod
    def from_dict(cls, data: dict) -> InferenceConfig:
        return cls(
            sampling_rate_hz=data.get("sampling_rate_hz", 10.4167),
            window_seconds=data.get("window_seconds", 30),
            channels_per_section=data.get("channels_per_section", 9),
            gauge_meters=data.get("gauge_meters", 15.3846),
            bidirectional_rnn=data.get("bidirectional_rnn", True),
            time_overlap_ratio=data.get("time_overlap_ratio", 0.5),
            samples_per_message=data.get("samples_per_message", 1),
        )

    @property
    def samples_per_window(self) -> int:
        return int(self.window_seconds * self.sampling_rate_hz)

    @property
    def messages_per_window(self) -> int:
        """Number of Kafka messages needed to fill a processing window."""
        return max(1, self.samples_per_window // self.samples_per_message)

    @property
    def step_size(self) -> int:
        """Step size in messages for rolling buffer derived from overlap ratio."""
        return max(1, int(self.messages_per_window * (1 - self.time_overlap_ratio)))


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
    alignment_method: str = "cpab"  # "cpab" (diffeomorphic ODE) or "shift" (linear delay)
    nstepsolver: int = 10  # CPAB ODE solver steps (10 converges for 1D piecewise-affine)
    speed_sampling: str = "midpoint"  # "midpoint" (fast) or "median" (accurate for slow traffic)

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
            alignment_method=data.get("alignment_method", "cpab"),
            nstepsolver=data.get("nstepsolver", 10),
            speed_sampling=data.get("speed_sampling", "midpoint"),
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
    instrument_params: InstrumentParams | None = None

    @classmethod
    def from_dict(cls, fiber_id: str, data: dict, defaults: dict) -> FiberConfig:
        sections_data = data.get("sections", [])
        sections = [SectionConfig.from_dict(s, defaults) for s in sections_data]
        return cls(
            fiber_id=fiber_id,
            input_topic=f"das.raw.{fiber_id}",
            total_channels=data.get("total_channels", 0),
            sampling_rate_hz=data.get("sampling_rate_hz", 0.0),
            sections=sections,
        )

    @property
    def is_ready(self) -> bool:
        """True when total_channels and sampling_rate_hz are populated."""
        return self.total_channels > 0 and self.sampling_rate_hz > 0.0

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
        self._instrument_params: dict[str, InstrumentParams] = {}
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

            # Re-apply cached instrument params to newly constructed FiberConfig objects.
            # Bootstrap populates these from Kafka .params topics at startup; they must
            # survive YAML hot-reloads since the YAML no longer carries these values.
            for fiber_id, params in self._instrument_params.items():
                if fiber_id in fibers:
                    fibers[fiber_id].total_channels = params.n_channels
                    fibers[fiber_id].sampling_rate_hz = params.sampling_rate_hz
                    fibers[fiber_id].instrument_params = params

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

    def bootstrap_instrument_params(
        self,
        kafka_bootstrap_servers: str,
        schema_registry_url: str,
        timeout_s: float = 10.0,
    ) -> None:
        """Read instrument params from das.raw.<fiber_id>.params topics.

        Creates an ephemeral Kafka consumer, reads the single compacted message
        from each fiber's .params topic, and populates total_channels and
        sampling_rate_hz on the FiberConfig. The instrument is the source of
        truth — values from fibers.yaml are only used as fallback when the
        params topic is unavailable.
        """
        from confluent_kafka import Consumer
        from confluent_kafka.admin import AdminClient
        from confluent_kafka.error import SerializationError
        from confluent_kafka.schema_registry import SchemaRegistryClient
        from confluent_kafka.schema_registry.avro import AvroDeserializer

        if self._config is None:
            raise RuntimeError("FiberConfigManager: config not loaded")

        fibers = self._config.fibers
        if not fibers:
            return

        sr_client = SchemaRegistryClient({"url": schema_registry_url})
        deserializer = AvroDeserializer(sr_client)

        topic_prefix = os.getenv("TOPIC_PREFIX", "das")
        group_id = f"{topic_prefix}-params-bootstrap"
        topics = [f"das.raw.{fid}.params" for fid in fibers]
        consumer = Consumer(
            {
                "bootstrap.servers": kafka_bootstrap_servers,
                "group.id": group_id,
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
            }
        )
        consumer.subscribe(topics)

        bootstrapped: list[str] = []
        pending = set(fibers.keys())
        deadline = time.monotonic() + timeout_s

        try:
            while pending and time.monotonic() < deadline:
                remaining_ms = int((deadline - time.monotonic()) * 1000)
                if remaining_ms <= 0:
                    break
                msg = consumer.poll(timeout=min(remaining_ms / 1000, 1.0))
                if msg is None or msg.error():
                    continue

                topic = msg.topic()
                if topic is None:
                    continue
                # das.raw.carros.params -> carros
                parts = topic.split(".")
                if len(parts) < 4 or parts[-1] != "params":
                    continue
                fiber_id = parts[2]

                if fiber_id not in fibers:
                    continue

                try:
                    data = deserializer(msg.value(), None)
                    params = InstrumentParams.from_kafka_message(data)
                except (SerializationError, KeyError, ValueError) as e:
                    logger.warning(f"Failed to parse params for '{fiber_id}': {e}")
                    continue
                fiber = fibers[fiber_id]
                fiber.total_channels = params.n_channels
                fiber.sampling_rate_hz = params.sampling_rate_hz
                fiber.instrument_params = params
                self._instrument_params[fiber_id] = params
                pending.discard(fiber_id)
                bootstrapped.append(fiber_id)

                logger.info(
                    f"Bootstrapped instrument params for fiber '{fiber_id}': "
                    f"nChannels={params.n_channels}, "
                    f"sampling_rate_hz={params.sampling_rate_hz:.1f}, "
                    f"gaugeLength={params.gauge_length:.3f}m, "
                    f"dx={params.dx:.4f}m"
                )
        finally:
            consumer.close()
            # Delete the ephemeral consumer group so it doesn't linger in Kafka
            try:
                admin = AdminClient({"bootstrap.servers": kafka_bootstrap_servers})
                futures = admin.delete_consumer_groups([group_id])
                for _gid, future in futures.items():
                    future.result(timeout=5)
                logger.debug(f"Deleted consumer group '{group_id}'")
            except Exception as e:
                logger.debug(f"Could not delete consumer group '{group_id}': {e}")

        if pending:
            for fid in pending:
                fiber = fibers[fid]
                if fiber.is_ready:
                    logger.warning(
                        f"No params topic for fiber '{fid}', "
                        f"using fibers.yaml fallback: "
                        f"total_channels={fiber.total_channels}, "
                        f"sampling_rate_hz={fiber.sampling_rate_hz}"
                    )
                else:
                    logger.error(
                        f"No params topic for fiber '{fid}' and no fibers.yaml fallback. "
                        f"Fiber will not process until params are available."
                    )

        logger.info(
            f"Instrument params bootstrap complete: "
            f"{len(bootstrapped)} bootstrapped, {len(pending)} pending"
        )

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
