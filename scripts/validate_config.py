#!/usr/bin/env python3
"""Validate fibers.yaml configuration for physics and consistency.

Checks:
- Pipeline step names are in the step registry
- Bandpass cutoffs respect post-decimation Nyquist frequency
- Section channel ranges are valid (start < stop, non-overlapping per fiber)
- Referenced model weight files exist
- Temporal decimation factor divides DAS package size evenly
- Inference parameters are consistent with pipeline config

Usage:
    python scripts/validate_config.py
    # or via Makefile:
    make validate-config

Exit code 0 = valid, 1 = errors found.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

PIPELINE_ROOT = Path(__file__).resolve().parent.parent / "services" / "pipeline"
CONFIG_PATH = PIPELINE_ROOT / "config" / "fibers.yaml"

VALID_STEPS = {
    "scale",
    "common_mode_removal",
    "bandpass_filter",
    "temporal_decimation",
    "spatial_decimation",
}

# DAS instrument default (samples per Kafka message)
DEFAULT_PACKAGE_SIZE = 24
DEFAULT_ORIGINAL_FS = 125.0


class ConfigError:
    def __init__(self, path: str, message: str):
        self.path = path
        self.message = message

    def __str__(self):
        return f"  {self.path}: {self.message}"


def validate(config: dict) -> list[ConfigError]:
    errors: list[ConfigError] = []

    defaults = config.get("defaults", {})
    default_pipeline = defaults.get("pipeline", [])
    model_defaults = config.get("model_defaults", {})
    models = config.get("models", {})
    fibers = config.get("fibers", {})

    # --- Validate default pipeline ---
    errors.extend(_validate_pipeline(default_pipeline, "defaults.pipeline"))

    # --- Validate pipeline physics ---
    errors.extend(
        _validate_pipeline_physics(default_pipeline, "defaults.pipeline", DEFAULT_ORIGINAL_FS)
    )

    # --- Validate fibers ---
    for fiber_id, fiber_cfg in fibers.items():
        sections = fiber_cfg.get("sections", [])
        channel_ranges = []

        for i, section in enumerate(sections):
            path = f"fibers.{fiber_id}.sections[{i}]"

            name = section.get("name")
            if not name:
                errors.append(ConfigError(path, "missing 'name' field"))

            channels = section.get("channels")
            if not channels or len(channels) != 2:
                errors.append(ConfigError(path, "channels must be [start, stop]"))
                continue

            ch_start, ch_stop = channels
            if ch_start >= ch_stop:
                errors.append(
                    ConfigError(path, f"channel_start ({ch_start}) >= channel_stop ({ch_stop})")
                )

            if ch_start < 0:
                errors.append(ConfigError(path, f"channel_start ({ch_start}) is negative"))

            channel_ranges.append((ch_start, ch_stop, name or f"section[{i}]"))

            # Validate per-section pipeline override if present
            section_pipeline = section.get("pipeline")
            if section_pipeline is not None and section_pipeline:  # not empty list
                errors.extend(_validate_pipeline(section_pipeline, f"{path}.pipeline"))

            # Validate model reference
            model = section.get("model", defaults.get("model"))
            if model and model not in models:
                errors.append(ConfigError(path, f"model '{model}' not defined in models section"))

        # Check for overlapping sections within a fiber
        for i, (s1_start, s1_stop, s1_name) in enumerate(channel_ranges):
            for s2_start, s2_stop, s2_name in channel_ranges[i + 1 :]:
                if s1_start < s2_stop and s2_start < s1_stop:
                    errors.append(
                        ConfigError(
                            f"fibers.{fiber_id}",
                            f"sections '{s1_name}' [{s1_start}:{s1_stop}] and "
                            f"'{s2_name}' [{s2_start}:{s2_stop}] overlap",
                        )
                    )

    # --- Validate model weight files ---
    model_base = model_defaults.get("path", "")
    exp_name = model_defaults.get("exp_name", "")
    version = model_defaults.get("version", "")
    if model_base and exp_name and version:
        weight_file = PIPELINE_ROOT / model_base / f"{exp_name}_parameters_{version}.pth"
        if not weight_file.exists():
            errors.append(
                ConfigError("model_defaults", f"weight file not found: {weight_file.name}")
            )

    counting = model_defaults.get("counting", {})
    for key in ("model_path", "thresholds_path", "mean_std_path"):
        rel_path = counting.get(key)
        if rel_path:
            full_path = PIPELINE_ROOT / model_base / rel_path.replace("models_parameters/", "")
            if not full_path.exists():
                errors.append(
                    ConfigError(f"model_defaults.counting.{key}", f"file not found: {rel_path}")
                )

    # --- Validate inference consistency ---
    inference = model_defaults.get("inference", {})
    temporal_factor = _get_temporal_factor(default_pipeline)
    spatial_factor = _get_spatial_factor(default_pipeline)

    if temporal_factor:
        expected_rate = DEFAULT_ORIGINAL_FS / temporal_factor
        configured_rate = inference.get("sampling_rate_hz")
        if configured_rate and abs(configured_rate - expected_rate) > 0.01:
            errors.append(
                ConfigError(
                    "model_defaults.inference.sampling_rate_hz",
                    f"configured {configured_rate} Hz but pipeline produces "
                    f"{expected_rate:.4f} Hz ({DEFAULT_ORIGINAL_FS}/{temporal_factor})",
                )
            )

        if DEFAULT_PACKAGE_SIZE % temporal_factor != 0:
            errors.append(
                ConfigError(
                    "defaults.pipeline.temporal_decimation",
                    f"factor {temporal_factor} does not divide package_size "
                    f"{DEFAULT_PACKAGE_SIZE} evenly",
                )
            )

        expected_spm = DEFAULT_PACKAGE_SIZE // temporal_factor
        configured_spm = inference.get("samples_per_message")
        if configured_spm and configured_spm != expected_spm:
            errors.append(
                ConfigError(
                    "model_defaults.inference.samples_per_message",
                    f"configured {configured_spm} but pipeline produces "
                    f"{expected_spm} (package_size {DEFAULT_PACKAGE_SIZE} / "
                    f"temporal_factor {temporal_factor})",
                )
            )

    if spatial_factor:
        gauge_raw = 5.1282051282  # DAS instrument dx
        expected_gauge = gauge_raw * spatial_factor
        configured_gauge = inference.get("gauge_meters")
        if configured_gauge and abs(configured_gauge - expected_gauge) > 0.01:
            errors.append(
                ConfigError(
                    "model_defaults.inference.gauge_meters",
                    f"configured {configured_gauge} m but spatial_decimation factor "
                    f"{spatial_factor} x dx {gauge_raw:.4f} = {expected_gauge:.4f} m",
                )
            )

    return errors


def _validate_pipeline(pipeline: list[dict], path: str) -> list[ConfigError]:
    errors = []
    for i, step in enumerate(pipeline):
        step_name = step.get("step")
        if not step_name:
            errors.append(ConfigError(f"{path}[{i}]", "missing 'step' field"))
        elif step_name not in VALID_STEPS:
            errors.append(
                ConfigError(
                    f"{path}[{i}]",
                    f"unknown step '{step_name}'. Valid: {sorted(VALID_STEPS)}",
                )
            )
    return errors


def _validate_pipeline_physics(
    pipeline: list[dict], path: str, original_fs: float
) -> list[ConfigError]:
    errors = []

    temporal_factor = _get_temporal_factor(pipeline)
    bp_params = _get_step_params(pipeline, "bandpass_filter")

    if bp_params and temporal_factor:
        high_freq = bp_params.get("high_freq_hz", 2.0)
        post_decim_fs = original_fs / temporal_factor
        post_decim_nyquist = post_decim_fs / 2.0

        if high_freq >= post_decim_nyquist:
            errors.append(
                ConfigError(
                    f"{path}.bandpass_filter",
                    f"high_freq_hz ({high_freq} Hz) >= post-decimation Nyquist "
                    f"({post_decim_nyquist:.2f} Hz = {original_fs}/{temporal_factor}/2). "
                    f"This causes aliasing.",
                )
            )

        low_freq = bp_params.get("low_freq_hz", 0.3)
        if low_freq >= high_freq:
            errors.append(
                ConfigError(
                    f"{path}.bandpass_filter",
                    f"low_freq_hz ({low_freq}) >= high_freq_hz ({high_freq})",
                )
            )

    return errors


def _get_step_params(pipeline: list[dict], step_name: str) -> dict | None:
    for step in pipeline:
        if step.get("step") == step_name:
            return step.get("params", {})
    return None


def _get_temporal_factor(pipeline: list[dict]) -> int | None:
    params = _get_step_params(pipeline, "temporal_decimation")
    return params.get("factor") if params else None


def _get_spatial_factor(pipeline: list[dict]) -> int | None:
    params = _get_step_params(pipeline, "spatial_decimation")
    return params.get("factor") if params else None


def main():
    if not CONFIG_PATH.exists():
        print(f"ERROR: Config not found: {CONFIG_PATH}")
        sys.exit(1)

    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    errors = validate(config)

    if errors:
        print(f"CONFIG VALIDATION FAILED ({len(errors)} errors):\n")
        for err in errors:
            print(err)
        sys.exit(1)
    else:
        print(f"Config validation passed: {CONFIG_PATH.name}")
        sys.exit(0)


if __name__ == "__main__":
    main()
