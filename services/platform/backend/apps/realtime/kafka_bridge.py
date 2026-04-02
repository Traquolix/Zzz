"""
Kafka -> Django Channels bridge for real-time data.

Consumes from Kafka topic (das.detections) and broadcasts to the same
Channels groups as the simulation engine, so the frontend sees identical
data shapes regardless of source.

Data flows:
  das.detections -> time-shifted replay -> realtime_detections group
  ClickHouse fiber_incidents (polled) -> realtime_incidents group
  Infrastructure SHM (simulated) -> realtime_shm_readings group

Org-scoped: all broadcasts are routed to org-specific Channels groups
via the fiber_org_map from FiberAssignment.

Time-shifted replay:
  AI engine inference produces 30-second windows as bursts. Instead of
  dumping them to the frontend, the ReplayBuffer replays messages at
  the original ~10 Hz rate with a fixed ~30s time offset. This creates
  a continuous stream that feels real-time.
"""

import asyncio
import contextlib
import logging
import time

from channels.layers import get_channel_layer
from django.conf import settings
from django.core.cache import cache
from opentelemetry import trace
from opentelemetry.propagate import extract

from apps.alerting.integration import check_alerts_for_detections, check_alerts_for_incident
from apps.realtime.broadcast import (
    broadcast_to_orgs,
    group_by_org,
    load_fiber_org_map,
    pubsub_broadcast_detections,
    pubsub_broadcast_shm,
)
from apps.realtime.shm_generator import generate_shm_readings
from apps.realtime.transforms import transform_detection_message, transform_incident_row
from apps.shared.constants import INFRA_REFRESH_INTERVAL, MAP_REFRESH_INTERVAL

logger = logging.getLogger("sequoia.realtime.kafka_bridge")


def load_infrastructure() -> list[dict]:
    """Load infrastructure from PostgreSQL."""
    from apps.monitoring.models import Infrastructure

    items = []
    for infra in Infrastructure.objects.select_related("organization").all():
        items.append(
            {
                "id": infra.id,
                "type": infra.type,
                "name": infra.name,
                "fiber_id": infra.fiber_id,
                "start_channel": infra.start_channel,
                "end_channel": infra.end_channel,
                "organization_id": str(infra.organization_id),
            }
        )

    if not items:
        logger.warning("No infrastructure in DB — SHM features will be disabled")

    return items


def _try_import_confluent_kafka():
    """Import confluent-kafka with Avro support, raising a clear error if not installed."""
    try:
        from confluent_kafka import DeserializingConsumer, KafkaError
        from confluent_kafka.schema_registry import SchemaRegistryClient
        from confluent_kafka.schema_registry.avro import AvroDeserializer

        return DeserializingConsumer, KafkaError, SchemaRegistryClient, AvroDeserializer
    except ImportError:
        raise ImportError(
            "confluent-kafka[avro] is required for Kafka bridge mode. "
            "Install it with: pip install confluent-kafka[avro]\n"
            "Note: this requires librdkafka C library. "
            "On Debian/Ubuntu: apt-get install librdkafka-dev"
        ) from None


# ============================================================================
# KAFKA MESSAGE HELPERS
# ============================================================================


_tracer = trace.get_tracer(__name__)


def _extract_kafka_headers(msg) -> dict[str, str]:
    """Extract Kafka message headers as a string dict for OTel propagation."""
    raw = msg.headers()
    if not raw:
        return {}
    result: dict[str, str] = {}
    for key, value in raw:
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        result[key] = value
    return result


def _parse_detection_message(value: dict | None) -> dict | None:
    """Parse Avro-deserialized detection message (already a dict)."""
    if value is None:
        return None
    if not isinstance(value, dict):
        logger.warning("Detection message is not a dict: %s", type(value))
        return None
    return value


async def run_kafka_bridge_loop(infrastructure: list[dict]):
    """
    Main async loop -- consumes from Kafka and broadcasts via Channels.

    Uses a ReplayBuffer to time-shift AI engine inference bursts into
    continuous 10 Hz streams. Three data streams:
    1. Detections: das.detections -> replay buffer -> realtime_detections (10 Hz)
    2. Incidents: polled from ClickHouse fiber_incidents (every 5s)
    3. SHM: generated from infrastructure config (every 1s)
    """
    from apps.realtime.replay_buffer import ReplayBuffer

    DeserializingConsumer, KafkaError, SchemaRegistryClient, AvroDeserializer = (
        _try_import_confluent_kafka()
    )

    bootstrap_servers = settings.KAFKA_BOOTSTRAP_SERVERS
    if not bootstrap_servers:
        raise ValueError(
            "KAFKA_BOOTSTRAP_SERVERS is not configured. "
            "Set it in settings or use --source sim for simulation mode."
        )

    schema_registry_url = getattr(settings, "SCHEMA_REGISTRY_URL", "http://schema-registry:8081")

    channel_layer = get_channel_layer()

    # Load fiber->org mapping (refreshed periodically)
    fiber_org_map = await load_fiber_org_map()
    last_map_refresh = time.time()

    # Org-aware broadcast helper for the replay buffer drain
    async def broadcast(_channel: str, data):
        nonlocal fiber_org_map
        await pubsub_broadcast_detections(data, fiber_org_map, flow="live")
        # Check alerts for detections (per-org)
        if isinstance(data, list):
            for org_id, org_dets in group_by_org(data, fiber_org_map).items():
                await check_alerts_for_detections(org_dets, org_id)

    # Create replay buffer and Kafka consumer with Avro deserialization
    replay_buffer = ReplayBuffer()

    # Setup Schema Registry client and Avro deserializer
    schema_registry_client = SchemaRegistryClient({"url": schema_registry_url})
    avro_deserializer = AvroDeserializer(schema_registry_client)

    consumer = DeserializingConsumer(
        {
            "bootstrap.servers": bootstrap_servers,
            "group.id": "sequoia-realtime-bridge",
            "auto.offset.reset": "latest",
            "enable.auto.commit": True,
            "session.timeout.ms": 10000,
            "value.deserializer": avro_deserializer,
        }
    )
    consumer.subscribe(["das.detections"])

    # Bounded TTL so a crashed bridge is detected within 10s.
    # Refreshed every 5s; cost is negligible for Redis.
    KAFKA_AVAILABLE_TTL = 10
    cache.set("kafka_available", True, timeout=KAFKA_AVAILABLE_TTL)
    logger.info(
        "Kafka bridge started (time-shifted replay): %s, topic: das.detections, %d org mappings",
        bootstrap_servers,
        len(fiber_org_map),
    )

    # State for incident polling and SHM
    shm_state: dict[str, dict] = {}
    last_incident_check = time.time()
    known_incident_ids: dict[str, tuple[str, int]] = {}  # {incident_id: (fiberId, direction)}
    last_shm_broadcast: float = 0
    last_batch_cleanup: float = 0
    last_kafka_flag_refresh: float = time.time()
    last_infra_refresh: float = time.time()

    # Start the replay drain task
    drain_task = asyncio.create_task(replay_buffer.drain(broadcast))

    try:
        while True:
            loop_start = time.time()

            # Refresh fiber->org mapping periodically
            if loop_start - last_map_refresh > MAP_REFRESH_INTERVAL:
                fiber_org_map = await load_fiber_org_map()
                last_map_refresh = loop_start

            # Refresh infrastructure periodically (picks up added/removed sensors)
            if loop_start - last_infra_refresh > INFRA_REFRESH_INTERVAL:
                new_infra = await asyncio.to_thread(load_infrastructure)
                if new_infra:
                    new_ids = {i["id"] for i in new_infra}
                    old_ids = {i["id"] for i in infrastructure}
                    # Prune SHM state for removed infrastructure
                    for removed_id in old_ids - new_ids:
                        shm_state.pop(removed_id, None)
                    if new_ids != old_ids:
                        logger.info(
                            "Infrastructure refreshed: %d items (+%d, -%d)",
                            len(new_infra),
                            len(new_ids - old_ids),
                            len(old_ids - new_ids),
                        )
                    infrastructure = new_infra
                last_infra_refresh = loop_start

            # Refresh bounded TTL every 5s so the flag expires if we crash
            if loop_start - last_kafka_flag_refresh > 5:
                cache.set("kafka_available", True, timeout=KAFKA_AVAILABLE_TTL)
                last_kafka_flag_refresh = loop_start

            # --- Poll Kafka (non-blocking) ---
            try:
                msg = consumer.poll(timeout=0.05)
            except Exception as poll_err:
                # Transient deserialization errors (e.g. Schema Registry
                # temporarily unreachable) should not kill the bridge.
                logger.warning("Kafka poll error (will retry): %s", poll_err)
                await asyncio.sleep(2)
                continue
            if msg is not None:
                if msg.error():
                    if msg.error().code() != KafkaError._PARTITION_EOF:
                        logger.error("Kafka error: %s", msg.error())
                        try:
                            import sentry_sdk

                            sentry_sdk.capture_message(
                                f"Kafka consumer error: {msg.error()}",
                                level="error",
                            )
                        except Exception:
                            pass
                else:
                    topic = msg.topic()
                    from apps.shared.metrics import KAFKA_MESSAGES_CONSUMED

                    KAFKA_MESSAGES_CONSUMED.add(1, {"topic": topic})
                    if topic == "das.detections":
                        # Extract W3C trace context from Kafka headers so
                        # the detection processing span links to the pipeline trace.
                        headers = _extract_kafka_headers(msg)
                        ctx = extract(headers)
                        with _tracer.start_as_current_span("kafka.consume.detections", context=ctx):
                            _handle_detection_message(msg.value(), replay_buffer)

            now = time.time()

            # --- Poll ClickHouse for incidents every 5 seconds ---
            if (now - last_incident_check) >= 5:
                last_incident_check = now
                await _poll_incidents(channel_layer, known_incident_ids, fiber_org_map)

            # --- Broadcast SHM at 1 Hz (org-scoped) ---
            if infrastructure and (now - last_shm_broadcast) >= 1:
                last_shm_broadcast = now
                readings = generate_shm_readings(infrastructure, shm_state)
                if readings:
                    await pubsub_broadcast_shm(readings, fiber_org_map, flow="live")

            # --- Cleanup stale batch trackers every 30s ---
            if (now - last_batch_cleanup) >= 30:
                last_batch_cleanup = now
                replay_buffer.cleanup_stale_batches()
                if replay_buffer.queue_size > 0:
                    logger.debug(
                        "Replay buffer: %d queued, %d active batches",
                        replay_buffer.queue_size,
                        replay_buffer.active_batches,
                    )

            # Yield to event loop
            elapsed = time.time() - loop_start
            await asyncio.sleep(max(0, 0.01 - elapsed))

    except KeyboardInterrupt:
        logger.info("Kafka bridge shutting down...")
    finally:
        cache.set("kafka_available", False, timeout=None)
        replay_buffer.stop()
        drain_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await drain_task
        consumer.close()
        logger.info("Kafka consumer closed.")


def _handle_detection_message(value: dict, replay_buffer) -> None:
    """Parse detection message, transform, and ingest into replay buffer.

    Each detection is ingested individually with its own timestamp so that
    the replay buffer spreads them over the original time window instead of
    dumping them all at once.
    """
    data = _parse_detection_message(value)
    if data is None:
        return

    fiber_id = data.get("fiber_id", "")
    detections = transform_detection_message(data)

    for det in detections:
        section_key = f"{fiber_id}:{det['channel']}"
        timestamp_ns = det["timestamp"] * 1_000_000
        replay_buffer.ingest_detection(section_key, timestamp_ns, [det])


async def _poll_incidents(
    channel_layer, known_incidents: dict, fiber_org_map: dict[str, list[str]]
):
    """
    Poll ClickHouse for active incidents and broadcast changes (org-scoped).

    Compares current active incidents against known set to detect
    new incidents and resolutions.

    Args:
        known_incidents: Dict of {incident_id: (fiberId, direction)} for currently
            tracked incidents. Stores both so resolved notifications include the
            correct direction for frontend placement.
    """
    from apps.shared.exceptions import ClickHouseUnavailableError
    from apps.shared.incident_service import query_active_raw

    try:
        rows = query_active_raw(fiber_ids=None, limit=200)
    except ClickHouseUnavailableError:
        logger.debug("ClickHouse unavailable for incident polling")
        return

    current_incidents: dict[str, tuple[str, int]] = {}
    for row in rows:
        iid = row["incident_id"]
        inc_data = transform_incident_row(row)
        current_incidents[iid] = (inc_data["fiberId"], inc_data.get("direction", 0))

        if iid not in known_incidents:
            # New incident -- broadcast to owning orgs
            await broadcast_to_orgs(
                channel_layer,
                "incidents",
                inc_data,
                fiber_org_map,
                fiber_ids={inc_data["fiberId"]},
                flow="live",
            )
            # Check alerts for incident
            await check_alerts_for_incident(inc_data, fiber_org_map)

    # Detect resolved incidents (were known, no longer active)
    resolved_ids = set(known_incidents) - set(current_incidents)
    for rid in resolved_ids:
        fiber_id, direction = known_incidents[rid]
        resolved_data = {
            "id": rid,
            "status": "resolved",
            "type": "",
            "tags": [],
            "fiberId": fiber_id,
            "direction": direction,
            "channel": 0,
            "detectedAt": "",
            "duration": None,
        }
        await broadcast_to_orgs(
            channel_layer,
            "incidents",
            resolved_data,
            fiber_org_map,
            fiber_ids={fiber_id},
            flow="live",
        )

    known_incidents.clear()
    known_incidents.update(current_incidents)
