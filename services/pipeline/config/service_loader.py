"""Unified service configuration loader from fibers.yaml + environment variables."""

from __future__ import annotations

import logging
import os

from config.fiber_config import FiberConfigManager
from shared.service_config import OutputConfig, ServiceConfig

logger = logging.getLogger(__name__)


def load_service_config(service_type: str) -> ServiceConfig:
    """Load ServiceConfig for a service type from fibers.yaml + env vars."""
    manager = FiberConfigManager()
    raw = manager.get_raw_config()

    defaults = raw.get("service_defaults", {})
    service_cfg = raw.get("services", {}).get(service_type, {})
    topics = defaults.get("topics", {})
    schemas = defaults.get("schemas", {}).get(service_type, {})
    producer_cfg = defaults.get("producer", {})

    # Topic prefix for environment isolation (default: "das" for backwards compat).
    # Preprod sets TOPIC_PREFIX=preprod so output topics become preprod.processed, etc.
    # Raw input topics (das.raw.*) are always shared — preprod reads the same DAS data.
    topic_prefix = os.getenv("TOPIC_PREFIX", "das")

    kafka_servers = os.getenv(
        "KAFKA_BOOTSTRAP_SERVERS", defaults.get("kafka_bootstrap_servers", "kafka:29092")
    )
    schema_registry = os.getenv(
        "SCHEMA_REGISTRY_URL", defaults.get("schema_registry_url", "http://schema-registry:8081")
    )

    outputs = _build_outputs(service_type, topics, schemas, topic_prefix)
    input_topic, input_pattern = _get_input_config(service_type, topics, topic_prefix)

    max_concurrent = service_cfg.get(
        "max_concurrent_messages", defaults.get("max_concurrent_messages", 50)
    )
    message_timeout = service_cfg.get(
        "message_timeout_seconds", defaults.get("message_timeout_seconds", 30.0)
    )
    buffer_timeout = service_cfg.get("buffer_timeout_seconds", 60.0)
    max_active_buffers = service_cfg.get("max_active_buffers", 10)

    config = ServiceConfig(
        input_topic=input_topic,
        input_topic_pattern=input_pattern,
        outputs=outputs,
        kafka_bootstrap_servers=kafka_servers,
        schema_registry_url=schema_registry,
        max_concurrent_messages=max_concurrent,
        message_timeout=message_timeout,
        buffer_timeout=buffer_timeout,
        max_active_buffers=max_active_buffers,
        producer_flush_threshold=producer_cfg.get("flush_threshold", 10),
        producer_flush_interval=producer_cfg.get("flush_interval", 1.0),
        producer_linger_ms=producer_cfg.get("linger_ms", 100),
        producer_batch_size=producer_cfg.get("batch_size", 131072),
        producer_compression_type=producer_cfg.get("compression_type", "lz4"),
        producer_acks=producer_cfg.get("acks", "all"),
        producer_retries=producer_cfg.get("retries", 3),
        producer_enable_idempotence=producer_cfg.get("enable_idempotence", True),
        dlq_topic=_prefixed_topic(topics.get("dlq", "das.dlq"), topic_prefix),
    )

    logger.info(
        f"Loaded config for {service_type}: "
        f"input={input_topic or input_pattern}, "
        f"outputs={list(outputs.keys())}, "
        f"kafka={kafka_servers}"
    )

    return config


def _prefixed_topic(default_topic: str, prefix: str) -> str:
    """Apply topic prefix for environment isolation.

    Replaces the ``das.`` prefix in topic names with the given prefix.
    If the topic doesn't start with ``das.`` or the prefix is already ``das``,
    returns the topic unchanged.
    """
    if prefix == "das" or not default_topic.startswith("das."):
        return default_topic
    return prefix + default_topic[3:]  # "das.processed" -> "preprod.processed"


def _build_outputs(
    service_type: str, topics: dict, schemas: dict, topic_prefix: str
) -> dict[str, OutputConfig]:
    """Build output configuration based on service type."""
    if service_type == "processor":
        return {
            "default": OutputConfig(
                topic=_prefixed_topic(topics.get("processed", "das.processed"), topic_prefix),
                key_schema_file=schemas.get("output_key"),
                value_schema_file=schemas.get("output_value"),
            )
        }
    elif service_type == "ai_engine":
        return {
            "default": OutputConfig(
                topic=_prefixed_topic(topics.get("detections", "das.detections"), topic_prefix),
                key_schema_file=schemas.get("detection_key"),
                value_schema_file=schemas.get("detection_value"),
            ),
        }
    else:
        raise ValueError(f"Unknown service type: {service_type}")


def _get_input_config(
    service_type: str, topics: dict, topic_prefix: str
) -> tuple[str | None, str | None]:
    """Get input topic or pattern for service type.

    For the processor, subscribes to a regex pattern matching all fiber
    topics (das.raw.*). Raw topics are always shared across environments
    — the DAS interrogator writes to das.raw.*, and both prod and preprod
    read from the same topics (with different consumer groups).

    For the AI engine, the input topic is prefixed (e.g. preprod.processed).
    """
    if service_type == "processor":
        fiber_id = os.getenv("FIBER_ID")
        if fiber_id:
            return f"das.raw.{fiber_id}", None
        # Raw input is always das.raw.* regardless of TOPIC_PREFIX
        return None, topics.get("raw_pattern", "^das\\.raw\\..+$")
    elif service_type == "ai_engine":
        return _prefixed_topic(topics.get("processed", "das.processed"), topic_prefix), None
    else:
        raise ValueError(f"Unknown service type: {service_type}")


def get_ai_engine_fiber_id() -> str | None:
    """Get FIBER_ID for AI engine filtering, if set. Legacy — no longer used."""
    return os.getenv("FIBER_ID")


def get_service_name(service_type: str) -> str:
    """Get service name from config.

    Single instance per service type handles all fibers. The topic prefix
    is appended when non-default (e.g. ``ai-engine-preprod``) so that each
    environment gets a unique consumer group ID.
    """
    manager = FiberConfigManager()
    raw = manager.get_raw_config()
    service_cfg = raw.get("services", {}).get(service_type, {})

    defaults = {
        "processor": "das-processor",
        "ai_engine": "ai-engine",
    }

    name: str = service_cfg.get("name", defaults.get(service_type, service_type))

    if service_type in ("processor", "ai_engine"):
        fiber_id = os.getenv("FIBER_ID")
        if fiber_id:
            name = f"{name}-{fiber_id}"

    # Append topic prefix for environment isolation (e.g. "ai-engine-preprod")
    topic_prefix = os.getenv("TOPIC_PREFIX", "das")
    if topic_prefix != "das":
        name = f"{name}-{topic_prefix}"

    return name
