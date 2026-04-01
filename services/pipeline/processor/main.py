from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid

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
        self._fiber_pipelines: dict[str, dict[str, ProcessingChain]] = {}
        self._fiber_config_hashes: dict[str, str] = {}
        self._fiber_configs: dict[str, FiberConfig] = {}

        super().__init__(service_name, service_config)

        setup_otel(service_name, "1.0.0")
        self.tracer = trace.get_tracer(__name__)

        self.logger.info(
            f"Processor initialized | "
            f"Pattern: {service_config.input_topic_pattern} | "
            f"Outputs: {list(service_config.outputs.keys())}"
        )

    def _get_fiber_pipelines(self, fiber_id: str) -> dict[str, ProcessingChain]:
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
        config_hash = hashlib.md5(  # nosec B324
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

    def _build_fiber_pipelines(self, fiber_cfg: FiberConfig) -> dict[str, ProcessingChain]:
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

    async def transform(self, message: Message) -> list[Message]:
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
                    fiber_id = message.payload.get("fiber_id", "unknown")

                try:
                    fiber_cfg = get_fiber_config(fiber_id)
                    sampling_rate_hz = fiber_cfg.sampling_rate_hz
                except KeyError:
                    sampling_rate_hz = 50.0

                pipelines = self._get_fiber_pipelines(fiber_id)
                fiber_cfg = self._fiber_configs.get(fiber_id)  # type: ignore[assignment]

                if not pipelines or not fiber_cfg:
                    raise ValueError(f"No config for fiber '{fiber_id}'. Add to fibers.yaml.")

                span.set_attribute("fiber_id", fiber_id)

                # Parse raw DAS batch into 2D array (samples, channels) + timestamps
                batch_data, timestamps_ns = self._parse_raw_batch(
                    message.payload, fiber_id, sampling_rate_hz, fiber_cfg.total_channels
                )
                if batch_data is None:
                    return []

                n_samples = batch_data.shape[0]
                n_channels = batch_data.shape[1]
                span.set_attribute("batch.samples", n_samples)

                # Process each section's pipeline on the full batch at once.
                # Pipeline steps handle 2D (samples, channels) arrays, so each
                # raw message produces at most 1 output message per section
                # (containing multiple decimated time samples).
                output_messages = []
                for section in fiber_cfg.sections:
                    section_id = section.name
                    if section_id not in pipelines:
                        continue
                    if n_channels <= section.channel_start:
                        continue

                    # Pass 2D batch through the pipeline
                    batch_measurement = {
                        "fiber_id": fiber_id,
                        "values": batch_data,
                        "timestamps_ns": timestamps_ns,
                        "channel_start": 0,
                        "sampling_rate_hz": sampling_rate_hz,
                    }
                    processed = await pipelines[section_id].process(batch_measurement)
                    if processed is None:
                        continue

                    output = self._build_batch_output(
                        processed, correlation_id, start_time, fiber_cfg, section
                    )
                    if output is None:
                        continue

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

    def _parse_raw_batch(
        self,
        raw: dict,
        fiber_id: str,
        sampling_rate_hz: float,
        total_channels: int,
    ) -> tuple[np.ndarray | None, list[int]]:
        """Parse a raw DAS message into a 2D batch array.

        Returns:
            (data_2d, timestamps_ns) where data_2d has shape (samples, channels)
            and timestamps_ns is a list of nanosecond timestamps per sample.
            Returns (None, []) on parse failure.
        """
        raw_values = raw.get("floatData") or raw.get("longData") or []
        n_values = len(raw_values)

        if n_values == 0:
            return None, []

        if n_values % total_channels != 0:
            self.logger.warning(
                f"floatData length {n_values} not divisible by total_channels "
                f"{total_channels} for fiber '{fiber_id}'. Skipping."
            )
            return None, []

        batch_size = n_values // total_channels
        all_values = np.asarray(raw_values, dtype=np.float64)
        data_2d = all_values.reshape(batch_size, total_channels)

        first_ts = raw.get("timeStampNanoSec", int(time.time() * 1e9))
        sample_interval_ns = int(1e9 / sampling_rate_hz)
        timestamps_ns = [first_ts + i * sample_interval_ns for i in range(batch_size)]

        return data_2d, timestamps_ns

    def _build_batch_output(
        self,
        processed: dict,
        correlation_id: str,
        start_time: float,
        fiber_cfg: FiberConfig,
        section: SectionConfig,
    ) -> dict | None:
        """Build output message from batch-processed data.

        The processed dict contains:
        - values: 2D array (samples, channels) after all pipeline steps
        - timestamps_ns: list of timestamps for kept samples
        """
        values = processed.get("values")
        if values is None:
            return None

        if not isinstance(values, np.ndarray):
            values = np.asarray(values, dtype=np.float64)

        if values.ndim == 2:
            n_samples, n_channels = values.shape
        elif values.ndim == 1:
            n_samples, n_channels = 1, values.shape[0]
            values = values.reshape(1, n_channels)
        else:
            return None

        if n_channels == 0 or n_samples == 0:
            return None

        # Flatten to (samples * channels,) for Avro serialization
        flat_values = values.flatten()

        stats = {
            "min_value": float(flat_values.min()),
            "max_value": float(flat_values.max()),
            "mean_value": float(flat_values.mean()),
            "rms_value": float(np.sqrt(np.mean(flat_values * flat_values))),
        }

        temporal_decimation = processed.get("temporal_decimation_factor", 1)
        spatial_decimation = processed.get("spatial_decimation_factor", 1)

        # Use first kept timestamp as the message timestamp
        timestamps_ns = processed.get("timestamps_ns", [])
        first_ts = timestamps_ns[0] if timestamps_ns else 0

        return {
            "fiber_id": processed.get("fiber_id"),
            "timestamp_ns": first_ts,
            "sampling_rate_hz": processed.get(
                "sampling_rate_hz", fiber_cfg.sampling_rate_hz / temporal_decimation
            ),
            "channel_start": processed.get("channel_start", section.channel_start),
            "channel_count": n_channels,
            "sample_count": n_samples,
            "values": flat_values.tolist(),
            "section": section.name,
            "model_hint": section.model,
            "processing_metadata": {
                "original_sampling_rate_hz": fiber_cfg.sampling_rate_hz,
                "original_channel_count": fiber_cfg.total_channels,
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
                "original_timestamp": None,
            },
            "signal_stats": stats,
        }


async def main():
    processor = DASProcessor()
    await processor.start()


if __name__ == "__main__":
    asyncio.run(main())
