"""Central configuration module for fiber/section/model settings.

Exports:
    Service Configuration:
    - load_service_config: Load ServiceConfig for a service type
    - get_service_name: Get service name from config

    Fiber Configuration:
    - get_fiber_config: Get fiber config by ID
    - get_model_spec: Get model spec by name
    - get_all_fiber_configs: Get all fiber configs
    - get_all_model_specs: Get all model specs
    - get_input_topics: Get list of input topics
    - get_fiber_by_topic: Get fiber config by topic name
    - extract_fiber_id: Extract fiber_id from topic
    - get_raw_config: Get raw YAML config dict
    - get_default_model_name: Get default model name

    Data Classes:
    - FiberConfig, SectionConfig, ModelSpec, etc.
"""

from config.fiber_config import (
    CountingConfig,
    FiberConfig,
    FiberConfigManager,
    InferenceConfig,
    ModelSpec,
    PipelineStepConfig,
    SectionConfig,
    SpeedDetectionConfig,
    extract_fiber_id,
    get_all_fiber_configs,
    get_all_model_specs,
    get_default_model_name,
    get_fiber_by_topic,
    get_fiber_config,
    get_input_topics,
    get_model_spec,
    get_raw_config,
)
from config.service_loader import (
    get_ai_engine_fiber_id,
    get_service_name,
    load_service_config,
)

__all__ = [
    # Service configuration
    "load_service_config",
    "get_service_name",
    "get_ai_engine_fiber_id",
    # Fiber configuration
    "CountingConfig",
    "FiberConfig",
    "FiberConfigManager",
    "InferenceConfig",
    "ModelSpec",
    "PipelineStepConfig",
    "SectionConfig",
    "SpeedDetectionConfig",
    "extract_fiber_id",
    "get_all_fiber_configs",
    "get_all_model_specs",
    "get_default_model_name",
    "get_fiber_by_topic",
    "get_fiber_config",
    "get_input_topics",
    "get_model_spec",
    "get_raw_config",
]
