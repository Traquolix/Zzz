from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import uuid

import numpy as np
from confluent_kafka import KafkaError
from confluent_kafka.serialization import MessageField, SerializationContext
from opentelemetry import trace

# Unified config loader
from config import (
    FiberConfig,
    FiberConfigManager,
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
from shared.message import KafkaMessage, Message
from shared.otel_setup import get_correlation_id, setup_otel
from shared.processor_metrics import ProcessorMetrics


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

        # Try initial bootstrap (may succeed if DAS is already running)
        self._manager = FiberConfigManager()
        self._kafka_servers = service_config.kafka_bootstrap_servers
        self._schema_registry = service_config.schema_registry_url
        self._manager.bootstrap_instrument_params(
            kafka_bootstrap_servers=self._kafka_servers,
            schema_registry_url=self._schema_registry,
        )

        # Pipelines built per-fiber dynamically from fibers.yaml
        self._fiber_pipelines: dict[str, dict[str, ProcessingChain]] = {}
        self._fiber_config_hashes: dict[str, str] = {}
        self._fiber_configs: dict[str, FiberConfig] = {}

        # Message-based stagger: skip the first N messages before producing
        # output. This offsets preprod's data flow so AI engine inference
        # bursts don't overlap with prod on the GPU.
        self._skip_messages = int(os.environ.get("STARTUP_SKIP_MESSAGES", "0"))
        self._messages_consumed = 0

        super().__init__(service_name, service_config)

        setup_otel(service_name, "1.0.0")
        self.tracer = trace.get_tracer(__name__)
        self.processor_metrics = ProcessorMetrics(service_name)

        if self._skip_messages > 0:
            self.logger.info(f"Message stagger: skipping first {self._skip_messages} messages")

        self.logger.info(
            f"Processor initialized | "
            f"Pattern: {service_config.input_topic_pattern} | "
            f"Outputs: {list(service_config.outputs.keys())}"
        )

    async def _retry_params_bootstrap(self) -> None:
        """Background task: retry instrument params bootstrap until all fibers are ready."""
        while self._running:
            pending = self._manager.pending_fibers()
            if not pending:
                return
            self.logger.info(f"Waiting for instrument params: {pending}. Retrying in 5s...")
            await asyncio.sleep(5)
            self._manager.bootstrap_instrument_params(
                kafka_bootstrap_servers=self._kafka_servers,
                schema_registry_url=self._schema_registry,
                timeout_s=5.0,
            )

    async def _start_service_loops(self):
        # Override MultiTransformer's default _poll_loop with batch polling.
        # Don't call super() — MultiTransformer would start the single-message
        # poll loop which we're replacing. ServiceBase's version is a no-op.
        self._tasks.append(asyncio.create_task(self._batch_poll_loop()))
        if self._manager.pending_fibers():
            self._tasks.append(asyncio.create_task(self._retry_params_bootstrap()))

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
                processor_metrics=self.processor_metrics,
            )

            self.logger.debug(
                f"Built pipeline for {fiber_cfg.fiber_id}:{section.name} "
                f"with {len(section.pipeline)} steps"
            )

        return pipelines

    def _extract_fiber_id(self, topic: str) -> str:
        """Extract fiber_id from topic name: das.raw.carros -> carros"""
        return topic.split(".")[-1]

    # --- Batch polling (replaces MultiTransformer's single-message poll loop) ---

    _POLL_BATCH_SIZE = 50
    _POLL_TIMEOUT = 0.1  # seconds

    def _poll_batch(self) -> list[KafkaMessage]:
        """Poll + deserialize a batch of messages in one thread-pool call.

        Runs entirely in the Kafka executor thread. Returns deserialized
        messages ready for dispatch. Errors on individual messages are
        logged and skipped — one bad message doesn't kill the batch.
        """
        raw_messages = self.consumer.consume(self._POLL_BATCH_SIZE, self._POLL_TIMEOUT)
        results: list[KafkaMessage] = []

        for raw in raw_messages:
            if raw.error():
                if raw.error().code() == KafkaError._PARTITION_EOF:
                    continue
                self.logger.error(f"Consumer error: {raw.error()}")
                continue
            try:
                topic = raw.topic() or ""
                key_ctx = SerializationContext(topic, MessageField.KEY)
                val_ctx = SerializationContext(topic, MessageField.VALUE)

                key = (
                    self.key_deserializer(raw.key(), key_ctx)
                    if raw.key() and hasattr(self, "key_deserializer")
                    else None
                )
                value = (
                    self.value_deserializer(raw.value(), val_ctx)
                    if raw.value() and hasattr(self, "value_deserializer")
                    else None
                )

                results.append(
                    KafkaMessage(
                        id=key if key is not None else "",
                        payload=value,
                        headers=dict(raw.headers()) if raw.headers() else None,
                        _kafka_message=raw,
                    )
                )
            except Exception as e:
                self.logger.error(f"Deserialization failed for message on {raw.topic()}: {e}")
                self.metrics.record_error("deserialization_error")

        return results

    async def _batch_poll_loop(self) -> None:
        """Poll Kafka in batches and dispatch concurrently.

        Replaces the base class _poll_loop for the processor. One thread-pool
        hop fetches and deserializes up to _POLL_BATCH_SIZE messages. Each
        message is dispatched as a concurrent task. Back-pressure is applied
        per message via the semaphore.
        """
        dispatch_tasks: set[asyncio.Task] = set()
        loop = asyncio.get_running_loop()
        self.logger.info(
            f"Batch poll loop starting (batch_size={self._POLL_BATCH_SIZE}, "
            f"timeout={self._POLL_TIMEOUT}s)"
        )

        while self._running:
            try:
                messages = await loop.run_in_executor(self._kafka_executor, self._poll_batch)

                if not messages:
                    continue

                for message in messages:
                    # Back-pressure: if at concurrency limit, wait for a slot
                    while self._semaphore.locked():
                        await asyncio.sleep(0.001)

                    task = asyncio.create_task(self._safe_dispatch(message, "batch_processor"))
                    dispatch_tasks.add(task)
                    task.add_done_callback(dispatch_tasks.discard)

            except Exception as e:
                self.logger.error(f"Error in batch poll loop: {e}")
                self.metrics.record_error("batch_poll_loop")
                await asyncio.sleep(self.config.error_backoff_delay)

        # Drain in-flight tasks on shutdown
        if dispatch_tasks:
            await asyncio.gather(*dispatch_tasks, return_exceptions=True)

    async def transform(self, message: Message) -> list[Message]:
        with self.tracer.start_as_current_span("transform_measurement") as span:
            fiber_id = "unknown"
            try:
                # Message-based stagger: consume but don't produce for the first N messages
                if self._skip_messages > 0:
                    self._messages_consumed += 1
                    if self._messages_consumed <= self._skip_messages:
                        if self._messages_consumed == self._skip_messages:
                            self.logger.info(
                                f"Stagger complete: skipped {self._skip_messages} messages, "
                                f"now producing output"
                            )
                        return []

                t_total = time.perf_counter()
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
                except KeyError:
                    self.logger.warning(f"Unknown fiber '{fiber_id}'. Skipping.")
                    return []

                if not fiber_cfg.is_ready:
                    return []

                sampling_rate_hz = fiber_cfg.sampling_rate_hz

                pipelines = self._get_fiber_pipelines(fiber_id)
                fiber_cfg = self._fiber_configs.get(fiber_id)  # type: ignore[assignment]

                if not pipelines or not fiber_cfg:
                    raise ValueError(f"No config for fiber '{fiber_id}'. Add to fibers.yaml.")

                span.set_attribute("fiber_id", fiber_id)

                # Parse raw DAS batch into 2D array (samples, channels) + timestamps
                t_parse = time.perf_counter()
                batch_data, timestamps_ns = self._parse_raw_batch(
                    message.payload, fiber_id, sampling_rate_hz, fiber_cfg.total_channels
                )
                if batch_data is None:
                    return []
                self.processor_metrics.record_phase(
                    "parse", time.perf_counter() - t_parse, fiber_id
                )

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
                    t_pipeline = time.perf_counter()
                    processed = await pipelines[section_id].process(
                        batch_measurement, fiber_id=fiber_id, section=section_id
                    )
                    self.processor_metrics.record_phase(
                        "pipeline", time.perf_counter() - t_pipeline, fiber_id
                    )
                    if processed is None:
                        continue

                    t_send = time.perf_counter()
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
                    self.processor_metrics.record_phase(
                        "send", time.perf_counter() - t_send, fiber_id
                    )
                    span.set_attribute(f"section.{section_id}", True)

                self.processor_metrics.record_phase(
                    "total", time.perf_counter() - t_total, fiber_id
                )
                self.processor_metrics.sections_produced.add(
                    len(output_messages), {"fiber_id": fiber_id}
                )
                span.set_attribute("sections_produced", len(output_messages))
                return output_messages

            except Exception as e:
                span.record_exception(e)
                self.processor_metrics.record_error("transform_error", fiber_id)
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

        The DAS hardware sends floatData with Package Size samples concatenated:
        Layout: [ch0_t0, ch1_t0, ..., chN_t0, ch0_t1, ..., chN_t1, ...]
        i.e. row-major with shape (package_size, total_channels).

        Package Size must be divisible by the temporal decimation factor so
        each batch produces a consistent number of output samples.

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

        # Use processor wall clock instead of instrument timestamp.
        # The DAS instrument clock drifts when GPS is not locked, but the
        # processor host is NTP-synced. Relative sample spacing is preserved.
        first_ts = time.time_ns()
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

        # Flatten to (samples * channels,) and serialize as raw float32 bytes.
        # Using float32 (not float64) halves message size and matches the Avro
        # schema. The AI engine decodes with np.frombuffer(v, dtype=np.float32).
        flat_values = values.flatten().astype(np.float32)

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
            "values": flat_values.tobytes(),
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
