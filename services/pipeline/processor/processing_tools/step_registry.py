"""Processing step registry - maps step names to classes.

This module provides a registry that maps step names (as used in fibers.yaml)
to their corresponding ProcessingStep classes. This enables config-driven
pipeline construction.

Usage:
    from processor.processing_tools.step_registry import create_step

    # Create a step from config
    step = create_step("bandpass_filter", {
        "low_freq_hz": 0.1,
        "high_freq_hz": 2.0,
        "order": 4,
    })

    # Or build a full pipeline
    pipeline = build_pipeline_from_config(section_config.pipeline)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Type

from processor.processing_tools.processing_chain import ProcessingChain
from processor.processing_tools.processing_steps.bandpass_filter import BandpassFilter
from processor.processing_tools.processing_steps.base_step import ProcessingStep
from processor.processing_tools.processing_steps.common_mode_removal import (
    CommonModeRemoval,
)
from processor.processing_tools.processing_steps.scale import Scale
from processor.processing_tools.processing_steps.spatial_decimation import (
    SpatialDecimation,
)
from processor.processing_tools.processing_steps.temporal_decimation import (
    TemporalDecimation,
)

logger = logging.getLogger(__name__)


# Registry mapping step names to (class, param_mapper)
# param_mapper converts config params to constructor args
_STEP_REGISTRY: Dict[str, Dict[str, Any]] = {
    "bandpass_filter": {
        "class": BandpassFilter,
        "param_map": {
            # config param -> constructor arg
            "low_freq_hz": "low_freq",
            "high_freq_hz": "high_freq",
            # order is not currently supported, but could be added
        },
        "defaults": {
            "low_freq": 0.1,
            "high_freq": 2.0,
        },
    },
    "common_mode_removal": {
        "class": CommonModeRemoval,
        "param_map": {
            "warmup_seconds": "warmup_seconds",
            "method": "method",
        },
        "defaults": {
            "warmup_seconds": 5.0,
            "method": "median",
        },
    },
    "scale": {
        "class": Scale,
        "param_map": {
            "factor": "factor",
        },
        "defaults": {
            "factor": 1.0,
        },
    },
    "temporal_decimation": {
        "class": TemporalDecimation,
        "param_map": {
            "factor": "factor",
        },
        "defaults": {
            "factor": 5,
        },
    },
    "spatial_decimation": {
        "class": SpatialDecimation,
        "param_map": {
            "factor": "factor",
            "channel_start": "channel_start",
            "channel_stop": "channel_stop",
        },
        "defaults": {
            "factor": 2,
        },
    },
}


def get_available_steps() -> List[str]:
    """Get list of available step names."""
    return list(_STEP_REGISTRY.keys())


def create_step(
    step_name: str,
    params: Dict[str, Any],
    fiber_sampling_rate_hz: float = 50.0,
) -> ProcessingStep:
    """Create a processing step from config.

    Args:
        step_name: Name of the step (e.g., "bandpass_filter")
        params: Parameters from config
        fiber_sampling_rate_hz: Fiber's sampling rate (needed for some steps)

    Returns:
        Configured ProcessingStep instance

    Raises:
        ValueError: If step_name is not in registry
    """
    if step_name not in _STEP_REGISTRY:
        available = get_available_steps()
        raise ValueError(f"Unknown processing step '{step_name}'. " f"Available: {available}")

    registry_entry = _STEP_REGISTRY[step_name]
    step_class: Type[ProcessingStep] = registry_entry["class"]
    param_map: Dict[str, str] = registry_entry["param_map"]
    defaults: Dict[str, Any] = registry_entry["defaults"]

    # Build constructor arguments
    constructor_args = defaults.copy()

    # Map config params to constructor args
    for config_key, constructor_key in param_map.items():
        if config_key in params:
            constructor_args[constructor_key] = params[config_key]

    # Special handling for steps that need sampling rate
    if step_name == "bandpass_filter":
        constructor_args["sampling_rate"] = fiber_sampling_rate_hz

    logger.debug(f"Creating {step_name} with args: {constructor_args}")
    return step_class(**constructor_args)


def build_pipeline_from_config(
    pipeline_config: List[Dict[str, Any]],
    fiber_sampling_rate_hz: float = 50.0,
    section_channels: tuple = None,
) -> ProcessingChain:
    """Build a ProcessingChain from pipeline config.

    Args:
        pipeline_config: List of step configs from fibers.yaml
        fiber_sampling_rate_hz: Fiber's sampling rate
        section_channels: (start, stop) channel range for this section

    Returns:
        Configured ProcessingChain

    Example config:
        [
            {"step": "bandpass_filter", "params": {"low_freq_hz": 0.1, "high_freq_hz": 2.0}},
            {"step": "spatial_decimation", "params": {"factor": 2}},
            {"step": "temporal_decimation", "params": {"factor": 5}},
        ]
    """
    steps = []

    # Optimization: move spatial_decimation before signal processing steps
    # (scale, bandpass) so they operate on the section's channels only
    # (e.g., 70 channels) instead of the full fiber (e.g., 5427 channels).
    # This is safe because spatial_decimation is a pure channel selection/slice
    # with no dependency on the signal processing steps.
    spatial_first = []
    other_steps = []
    for step_config in pipeline_config:
        if step_config.get("step") == "spatial_decimation":
            spatial_first.append(step_config)
        else:
            other_steps.append(step_config)
    reordered_config = spatial_first + other_steps

    for step_config in reordered_config:
        step_name = step_config.get("step")
        params = dict(step_config.get("params", {}))  # Copy to avoid mutating config

        if not step_name:
            raise ValueError(f"Pipeline step missing 'step' field: {step_config}")

        # Inject section channel bounds for spatial decimation if provided
        if step_name == "spatial_decimation" and section_channels:
            if "channel_start" not in params:
                params["channel_start"] = section_channels[0]
            if "channel_stop" not in params:
                params["channel_stop"] = section_channels[1]

        step = create_step(step_name, params, fiber_sampling_rate_hz)
        steps.append(step)

    logger.info(f"Built pipeline with {len(steps)} steps: " f"{[s.name for s in steps]}")

    return ProcessingChain(steps)


def register_step(
    name: str,
    step_class: Type[ProcessingStep],
    param_map: Dict[str, str],
    defaults: Dict[str, Any] = None,
) -> None:
    """Register a custom processing step.

    This allows extensions to add new step types without modifying this module.

    Args:
        name: Step name to use in config
        step_class: ProcessingStep subclass
        param_map: Mapping from config param names to constructor arg names
        defaults: Default values for constructor args
    """
    _STEP_REGISTRY[name] = {
        "class": step_class,
        "param_map": param_map,
        "defaults": defaults or {},
    }
    logger.info(f"Registered custom processing step: {name}")
