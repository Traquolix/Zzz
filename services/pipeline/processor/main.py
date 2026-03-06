from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from typing import Dict, List

import numpy as np
from opentelemetry import trace

# Unified config loader
from config import (
    FiberConfig,
    SectionConfig,
    get_fiber_config,
    get_service_name,
    load_service_config,
)
from processor.processing_tools import (
    ProcessingChain,
    build_pipeline_from_config,
)
from shared import MultiTransformer
from shared.message import Message
from shared.otel_setup import get_correlation_id, setup_otel


class DASProcessor(MultiTransformer):
    """DAS signal processor with config-driven processing pipelines.

    Config-driven processing:
        - Subscribes to topic pattern das.raw.*
        - Extracts fiber_id from topic name (das.raw.carros -> carros)
        - Loads section config from fibers.yaml (hot-reloaded)
        - Builds processing pipeline from config (bandpass, decimation, etc.)
        - Tags all messages with fiber_id, section, model_hint
    """

    def __init__(self):
        # Load config from unified loader (fibers.yaml + env vars)
        service_name = get_service_name("processor")
        service_config = load_service_config("processor")

        # Pipelines built per-fiber dynamically from fibers.yaml
        self._fiber_pipelines: Dict[str, Dict[str, ProcessingChain]] = {}
        self._fiber_config_hashes: Dict[str, str] = {}
        self._fiber_configs: Dict[str, FiberConfig] = {}

        super().__init__(service_name, service_config)

        setup_otel(service_name, "1.0.0")
        self.tracer = trace.get_tracer(__name__)

        self.logger.info(
            f"Processor initialized | "
            f"Pattern: {service_config.input_topic_pattern} | "
            f"Outputs: {list(service_config.outputs.keys())}"
        )

    def _get_fiber_pipelines(self, fiber_id: str) -> Dict[str, ProcessingChain]:
        """Get or build pipelines for a fiber.

        Pipelines are cached per fiber_id. Config is reloaded from fibers.yaml
        on each call to support hot-reload.
        """
        # Load fiber config from fibers.yaml.
        try:
            fiber_cfg = get_fiber_config(fiber_id)
        except KeyError:
            return {}

        # Check if config content changed (not identity — objects may be recreated on reload)
        config_hash = hashlib.md5(
            json.dumps(fiber_cfg.__dict__, default=str, sort_keys=True).encode()
        ).hexdigest()
        cached_hash = self._fiber_config_hashes.get(fiber_id)
        if cached_hash != config_hash:
            # Config changed or first time — rebuild pipelines
            self._fiber_config_hashes[fiber_id] = config_hash
            self._fiber_configs[fiber_id] = fiber_cfg
            self._fiber_pipelines[fiber_id] = self._build_fiber_pipelines(fiber_cfg)
            self.logger.info(
                f"Built pipelines for fiber '{fiber_id}': {len(fiber_cfg.sections)} sections"
                + (" (config changed)" if cached_hash is not None else "")
            )

        return self._fiber_pipelines.get(fiber_id, {})

    def _build_fiber_pipelines(self, fiber_cfg: FiberConfig) -> Dict[str, ProcessingChain]:
        """Build processing pipelines from fiber YAML config.

        Each section's pipeline is built from its config using the step registry.
        """
        pipelines = {}
        for section in fiber_cfg.sections:
            # Convert PipelineStepConfig list to dict list for build_pipeline_from_config
            pipeline_config = [
                {"step": step.step, "params": step.params} for step in section.pipeline
            ]

            pipelines[section.name] = build_pipeline_from_config(
                pipeline_config,
                fiber_sampling_rate_hz=fiber_cfg.sampling_rate_hz,
                section_channels=(section.channel_start, section.channel_stop),
            )

            self.logger.debug(
                f"Built pipeline for {fiber_cfg.fiber_id}:{section.name} "
                f"with {len(section.pipeline)} steps"
            )

        return pipelines

    def _extract_fiber_id(self, topic: str) -> str:
        """Extract fiber_id from topic name: das.raw.carros -> carros"""
        return topic.split(".")[-1]

    async def transform(self, message: Message) -> List[Message]:
        with self.tracer.start_as_current_span("transform_measurement") as span:
            try:
                start_time = time.time()
                correlation_id = get_correlation_id() or str(uuid.uuid4())
                span.set_attribute("correlation_id", correlation_id)

                # Extract fiber_id from topic name (das.raw.carros -> carros)
                if hasattr(message, "_kafka_message") and message._kafka_message:
                    topic = message._kafka_message.topic()
                    fiber_id = self._extract_fiber_id(topic)
                    span.set_attribute("source_topic", topic)
                else:
                    # Fallback for testing - extract from payload if available
                    fiber_id = message.payload.get("fiber_id", "unknown")

                # Get fiber config for sampling rate.
                try:
                    fiber_cfg = get_fiber_config(fiber_id)
                    sampling_rate_hz = fiber_cfg.sampling_rate_hz
                except KeyError:
                    sampling_rate_hz = 50.0  # Default DAS hardware sampling rate.

                # Get fiber-specific pipelines and sections from fibers.yaml.
                pipelines = self._get_fiber_pipelines(fiber_id)
                fiber_cfg = self._fiber_configs.get(fiber_id)

                if not pipelines or not fiber_cfg:
                    raise ValueError(f"No config for fiber '{fiber_id}'. Add to fibers.yaml.")

                span.set_attribute("fiber_id", fiber_id)

                # Unbatch: split batched DAS message (Package Size > 1) into
                # individual per-timestamp measurements
                measurements = self._unbatch_raw_message(
                    message.payload, fiber_id, sampling_rate_hz, fiber_cfg.total_channels
                )
                span.set_attribute("batch.size", len(measurements))

                output_messages = []
                for measurement in measurements:
                    values = measurement.get("values", [])
                    msg_start = measurement.get("channel_start", 0)
                    msg_end = msg_start + len(values)

                    for section in fiber_cfg.sections:
                        section_id = section.name
                        if msg_end <= section.channel_start or msg_start >= section.channel_stop:
                            continue

                        if section_id not in pipelines:
                            continue

                        processed = await pipelines[section_id].process(measurement)
                        if processed is None:
                            continue

                        output = self._build_output(
                            measurement, processed, correlation_id, start_time, fiber_cfg, section
                        )
                        output_messages.append(
                            Message(
                                id=f"{fiber_id}:{section_id}",
                                payload=output,
                                headers={
                                    "source": self.service_name,
                                    "fiber_id": fiber_id,
                                    "section": section_id,
                                    "model_hint": section.model,
                                    "timestamp": str(output["timestamp_ns"]),
                                    "original_message_id": message.id,
                                    **(message.headers or {}),
                                },
                                output_id="default",
                            )
                        )
                        span.set_attribute(f"section.{section_id}", True)

                span.set_attribute("sections_produced", len(output_messages))
                return output_messages

            except Exception as e:
                span.record_exception(e)
                self.logger.error(f"Error processing message {message.id}: {e}")
                raise

    def _unbatch_raw_message(
        self, raw: dict, fiber_id: str, sampling_rate_hz: float, total_channels: int
    ) -> list:
        """Split a batched DAS message into per-timestamp measurements.

        The DAS Package Size setting controls how many timestamps are concatenated
        in floatData. With Package Size=25 and 5427 channels:
          floatData has 5427*25 = 135,675 floats
          Layout: [ch0_t0, ch1_t0, ..., ch5426_t0, ch0_t1, ..., ch5426_t24]
        """
        raw_values = raw.get("floatData") or raw.get("longData") or []
        n_values = len(raw_values)

        # Single timestamp (Package Size=1) — existing path
        if n_values <= total_channels:
            return [self._adapt_message(raw, fiber_id, sampling_rate_hz)]

        if n_values % total_channels != 0:
            self.logger.warning(
                f"floatData length {n_values} not divisible by total_channels "
                f"{total_channels} for fiber '{fiber_id}'. Using single-sample fallback."
            )
            return [self._adapt_message(raw, fiber_id, sampling_rate_hz)]

        batch_size = n_values // total_channels
        all_values = np.asarray(raw_values, dtype=np.float64)
        data_2d = all_values.reshape(batch_size, total_channels)

        first_ts = raw.get("timeStampNanoSec", int(time.time() * 1e9))
        sample_interval_ns = int(1e9 / sampling_rate_hz)

        measurements = []
        for i in range(batch_size):
            measurements.append(
                {
                    "fiber_id": fiber_id,
                    "values": data_2d[i],
                    "timestamp_ns": first_ts + i * sample_interval_ns,
                    "channel_start": 0,
                    "sampling_rate_hz": sampling_rate_hz,
                }
            )
        return measurements

    def _adapt_message(self, raw: dict, fiber_id: str, sampling_rate_hz: float) -> dict:
        """Convert raw DAS format (floatData/longData) to internal format."""
        if "floatData" not in raw and "longData" not in raw:
            # Already in internal format, return copy with fiber_id set
            result = raw.copy()
            result["fiber_id"] = fiber_id
            return result
        raw_values = raw.get("floatData") or raw.get("longData") or []
        return {
            "fiber_id": fiber_id,
            "values": np.asarray(raw_values, dtype=np.float64),
            "timestamp_ns": raw.get("timeStampNanoSec", int(time.time() * 1e9)),
            "channel_start": 0,
            "sampling_rate_hz": sampling_rate_hz,
        }

    def _build_output(
        self,
        original: dict,
        processed: dict,
        correlation_id: str,
        start_time: float,
        fiber_cfg: FiberConfig,
        section: SectionConfig,
    ) -> dict:
        """Build output message with fiber_id, section, and model_hint tags."""
        values = processed.get("values", [])
        n = len(values)

        # Signal stats (required by schema) — use numpy for speed
        if n > 0:
            if isinstance(values, np.ndarray):
                stats = {
                    "min_value": float(values.min()),
                    "max_value": float(values.max()),
                    "mean_value": float(values.mean()),
                    "rms_value": float(np.sqrt(np.mean(values * values))),
                }
                values = values.tolist()  # Convert to list for Avro serialization
            else:
                stats = {
                    "min_value": min(values),
                    "max_value": max(values),
                    "mean_value": sum(values) / n,
                    "rms_value": (sum(v * v for v in values) / n) ** 0.5,
                }
        else:
            stats = {"min_value": 0.0, "max_value": 0.0, "mean_value": 0.0, "rms_value": 0.0}

        # Extract decimation factors from processed message or defaults
        temporal_decimation = processed.get("temporal_decimation_factor", 5)
        spatial_decimation = processed.get("spatial_decimation_factor", 1)

        return {
            # Core data
            "fiber_id": processed.get("fiber_id"),
            "timestamp_ns": processed.get("timestamp_ns"),
            "sampling_rate_hz": processed.get(
                "sampling_rate_hz", fiber_cfg.sampling_rate_hz / temporal_decimation
            ),
            "channel_start": processed.get("channel_start", section.channel_start),
            "channel_count": n,
            "values": values,
            # Section routing info (for AI engine)
            "section": section.name,
            "model_hint": section.model,
            # Metadata (required by schema, useful for debugging)
            "processing_metadata": {
                "original_sampling_rate_hz": fiber_cfg.sampling_rate_hz,
                "original_channel_count": len(original.get("values", [])),
                "temporal_decimation_factor": temporal_decimation,
                "spatial_decimation_factor": spatial_decimation,
                "channel_selection": {
                    "start": section.channel_start,
                    "stop": section.channel_stop,
                    "step": spatial_decimation,
                },
                "processing_timestamp_ns": time.time_ns(),
                "correlation_id": correlation_id,
                "processing_duration_ms": (time.time() - start_time) * 1000,
                "original_timestamp": original.get("timestamp_ns"),
            },
            "signal_stats": stats,
        }


async def main():
    processor = DASProcessor()
    await processor.start()


if __name__ == "__main__":
    asyncio.run(main())
