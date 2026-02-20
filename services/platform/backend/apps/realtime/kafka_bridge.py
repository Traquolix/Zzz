"""
Kafka -> Django Channels bridge for real-time data.

Consumes from Kafka topics (das.speeds, das.counts) and broadcasts
to the same Channels groups as the simulation engine, so the frontend
sees identical data shapes regardless of source.

Data flows:
  das.speeds -> time-shifted replay -> realtime_detections group
  das.counts -> time-shifted replay -> realtime_counts group
  ClickHouse fiber_incidents (polled) -> realtime_incidents group
  Infrastructure SHM (simulated) -> realtime_shm_readings group

Org-scoped: all broadcasts are routed to org-specific Channels groups
via the fiber_org_map from FiberAssignment.

Time-shifted replay:
  AI engine inference produces 30-second windows as bursts. Instead of
  dumping them to the frontend, the ReplayBuffer replays messages at
  the original 10 Hz rate with a fixed ~30s time offset. This creates
  a continuous stream that feels real-time.
"""

import asyncio
import json
import logging
import math
import random
import time

from channels.layers import get_channel_layer
from django.conf import settings

logger = logging.getLogger('sequoia.kafka_bridge')


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
        )


# ============================================================================
# MESSAGE TRANSFORMS
# ============================================================================

def _parse_speed_message(value: dict | None) -> dict | None:
    """Parse Avro-deserialized speed message (already a dict)."""
    if value is None:
        return None
    if not isinstance(value, dict):
        logger.warning('Speed message is not a dict: %s', type(value))
        return None
    return value


def transform_speed_message(data: dict) -> list[dict]:
    """
    Transform a parsed das.speeds message into frontend Detection[] shape.

    Kafka Avro schema (das.speeds):
        { fiber_id, timestamp_ns, speeds: [(channel_number, speed), ...],
          channel_start, ai_metadata }

    Frontend Detection:
        { fiberLine, channel, speed, count, direction, timestamp }

    Speed sign convention: positive = direction 0, negative = direction 1.
    Nearby channels (within 8) are grouped with count > 1.
    """
    fiber_id = data.get('fiber_id', '')
    timestamp_ns = data.get('timestamp_ns', 0)
    speeds = data.get('speeds', [])
    timestamp_ms = timestamp_ns // 1_000_000

    if not speeds:
        return []

    # Group nearby channels (within 8 channels) -- same logic as simulation
    sorted_speeds = sorted(speeds, key=lambda s: s[0] if isinstance(s, (list, tuple)) else s.get('channel_number', 0))
    detections = []
    processed = set()

    for i, entry in enumerate(sorted_speeds):
        if i in processed:
            continue

        if isinstance(entry, (list, tuple)):
            ch, spd = entry[0], entry[1]
        else:
            ch = entry.get('channel_number', 0)
            spd = entry.get('speed', 0.0)

        # Find nearby entries
        group = [(ch, spd)]
        processed.add(i)
        for j in range(i + 1, len(sorted_speeds)):
            if j in processed:
                continue
            other = sorted_speeds[j]
            if isinstance(other, (list, tuple)):
                other_ch, other_spd = other[0], other[1]
            else:
                other_ch = other.get('channel_number', 0)
                other_spd = other.get('speed', 0.0)

            if abs(other_ch - ch) < 8:
                group.append((other_ch, other_spd))
                processed.add(j)
            else:
                break  # sorted, so no more nearby

        avg_ch = sum(g[0] for g in group) / len(group)
        avg_spd = sum(g[1] for g in group) / len(group)

        detections.append({
            'fiberLine': fiber_id,
            'channel': round(avg_ch),
            'speed': round(abs(avg_spd), 1),
            'count': len(group),
            'direction': 0 if avg_spd >= 0 else 1,
            'timestamp': timestamp_ms,
        })

    return detections


def transform_count_message(value: dict | None) -> tuple[dict, str, int] | None:
    """
    Transform an Avro-deserialized das.counts message into frontend VehicleCount shape.

    Kafka Avro schema (das.counts):
        { fiber_id, channel_start, channel_end, count_timestamp_ns,
          vehicle_count, engine_version, model_type }

    Frontend VehicleCount:
        { fiberLine, channelStart, channelEnd, vehicleCount, timestamp }

    Returns (count_data, section_key, count_timestamp_ns) or None.
    """
    if value is None or not isinstance(value, dict):
        logger.warning('Count message is not a dict: %s', type(value))
        return None

    data = value

    fiber_id = data.get('fiber_id', '')
    channel_start = data.get('channel_start', 0)
    channel_end = data.get('channel_end', 0)
    count_timestamp_ns = data.get('count_timestamp_ns', 0)
    vehicle_count = data.get('vehicle_count', 0.0)
    timestamp_ms = count_timestamp_ns // 1_000_000

    section_key = f'{fiber_id}:{channel_start}'

    count_data = {
        'fiberLine': fiber_id,
        'channelStart': channel_start,
        'channelEnd': channel_end,
        'vehicleCount': round(float(vehicle_count), 1),
        'timestamp': timestamp_ms,
    }

    return count_data, section_key, count_timestamp_ns


def transform_incident_row(row: dict) -> dict:
    """
    Transform a ClickHouse fiber_incidents row into frontend Incident shape.

    Same transform used by IncidentListView and the simulation engine.
    """
    return {
        'id': row['incident_id'],
        'type': row['incident_type'],
        'severity': row['severity'],
        'fiberLine': row['fiber_id'],
        'channel': row['channel_start'],
        'detectedAt': (
            row['timestamp'].isoformat()
            if hasattr(row['timestamp'], 'isoformat')
            else str(row['timestamp'])
        ),
        'status': row['status'],
        'duration': row['duration_seconds'] * 1000 if row.get('duration_seconds') else None,
    }


# ============================================================================
# SHM GENERATOR (reusable for both simulation and bridge)
# ============================================================================

def generate_shm_readings(infrastructure: list[dict], shm_state: dict) -> list[dict]:
    """
    Generate SHM frequency readings for infrastructure items.

    Uses the same physics model as the simulation engine:
    - Base frequency: bridge ~5Hz, tunnel ~15Hz
    - Periodic + fast oscillation + random noise
    - Amplitude based on traffic load approximation
    """
    now_ms = int(time.time() * 1000)
    t = time.time()
    readings = []

    for infra in infrastructure:
        iid = infra['id']

        if iid not in shm_state:
            infra_type = infra.get('type', 'bridge')
            base = {'bridge': 5.0, 'tunnel': 15.0}.get(infra_type, 10.0)
            shm_state[iid] = {
                'base_freq': base + (random.random() - 0.5) * 2,
                'phase': random.random() * math.pi * 2,
            }

        state = shm_state[iid]
        base_freq = state['base_freq']
        phase = state['phase']

        periodic = math.sin(t * 0.1 + phase) * 0.3
        fast = math.sin(t * 2.5 + phase * 2) * 0.1
        noise = (random.random() - 0.5) * 0.2
        freq = base_freq + periodic + fast + noise

        base_amp = 0.3
        vib_amp = abs(math.sin(t * 5 + phase)) * 0.15
        noise_amp = random.random() * 0.1
        amp = min(1.0, base_amp + vib_amp + noise_amp)

        readings.append({
            'infrastructureId': iid,
            'frequency': round(freq, 2),
            'amplitude': round(amp, 2),
            'timestamp': now_ms,
        })

    return readings


# ============================================================================
# ORG-SCOPED BROADCAST HELPERS
# ============================================================================

def _load_fiber_org_map_sync() -> dict[str, list[str]]:
    """Load fiber->org mapping from DB (sync version)."""
    from apps.fibers.utils import get_fiber_org_map
    return get_fiber_org_map()


async def _load_fiber_org_map() -> dict[str, list[str]]:
    """Load fiber->org mapping from DB (async-safe)."""
    from asgiref.sync import sync_to_async
    return await sync_to_async(_load_fiber_org_map_sync, thread_sensitive=True)()


def _load_infra_org_map(infrastructure: list[dict]) -> dict[str, str]:
    """Build infrastructure_id -> org_id mapping from infrastructure list."""
    return {infra['id']: infra.get('organization_id', '') for infra in infrastructure}


async def _org_broadcast(channel_layer, channel: str, data, fiber_org_map: dict[str, list[str]]):
    """
    Broadcast data to org-scoped groups based on fiberLine field.

    For list data: groups items by fiber_id, sends each org only their items.
    For dict data (single item): sends to orgs that own the fiber.
    Always sends full data to __all__ group.
    """
    # Always send to superuser group
    await channel_layer.group_send(f'realtime_{channel}_org___all__', {
        'type': 'broadcast_message',
        'channel': channel,
        'data': data,
    })

    if isinstance(data, list):
        # Group items by org
        org_items: dict[str, list[dict]] = {}
        for item in data:
            fid = item.get('fiberLine', '')
            for org_id in fiber_org_map.get(fid, []):
                org_items.setdefault(org_id, []).append(item)

        for org_id, org_data in org_items.items():
            await channel_layer.group_send(f'realtime_{channel}_org_{org_id}', {
                'type': 'broadcast_message',
                'channel': channel,
                'data': org_data,
            })
    elif isinstance(data, dict):
        fid = data.get('fiberLine', '')
        for org_id in fiber_org_map.get(fid, []):
            await channel_layer.group_send(f'realtime_{channel}_org_{org_id}', {
                'type': 'broadcast_message',
                'channel': channel,
                'data': data,
            })


# ============================================================================
# KAFKA BRIDGE LOOP (time-shifted replay)
# ============================================================================

async def run_kafka_bridge_loop(infrastructure: list[dict]):
    """
    Main async loop -- consumes from Kafka and broadcasts via Channels.

    Uses a ReplayBuffer to time-shift AI engine inference bursts into
    continuous 10 Hz streams. Four data streams:
    1. Detections: das.speeds -> replay buffer -> realtime_detections (10 Hz)
    2. Counts: das.counts -> replay buffer -> realtime_counts (per inference)
    3. Incidents: polled from ClickHouse fiber_incidents (every 5s)
    4. SHM: generated from infrastructure config (every 1s)
    """
    from apps.realtime.replay_buffer import ReplayBuffer

    DeserializingConsumer, KafkaError, SchemaRegistryClient, AvroDeserializer = _try_import_confluent_kafka()

    bootstrap_servers = settings.KAFKA_BOOTSTRAP_SERVERS
    if not bootstrap_servers:
        raise ValueError(
            "KAFKA_BOOTSTRAP_SERVERS is not configured. "
            "Set it in settings or use --source sim for simulation mode."
        )

    schema_registry_url = getattr(settings, 'SCHEMA_REGISTRY_URL', 'http://schema-registry:8081')

    channel_layer = get_channel_layer()

    # Load fiber->org mapping (refreshed periodically)
    fiber_org_map = await _load_fiber_org_map()
    infra_org_map = _load_infra_org_map(infrastructure)
    last_map_refresh = time.time()
    MAP_REFRESH_INTERVAL = 300  # 5 minutes

    # Org-aware broadcast helper for the replay buffer drain
    async def broadcast(channel: str, data):
        await _org_broadcast(channel_layer, channel, data, fiber_org_map)

    # Create replay buffer and Kafka consumer with Avro deserialization
    replay_buffer = ReplayBuffer()

    # Setup Schema Registry client and Avro deserializer
    schema_registry_client = SchemaRegistryClient({'url': schema_registry_url})
    avro_deserializer = AvroDeserializer(schema_registry_client)

    consumer = DeserializingConsumer({
        'bootstrap.servers': bootstrap_servers,
        'group.id': 'sequoia-realtime-bridge',
        'auto.offset.reset': 'latest',
        'enable.auto.commit': True,
        'session.timeout.ms': 10000,
        'value.deserializer': avro_deserializer,
    })
    consumer.subscribe(['das.speeds', 'das.counts'])

    logger.info(
        'Kafka bridge started (time-shifted replay): %s, topics: das.speeds, das.counts, %d org mappings',
        bootstrap_servers, len(fiber_org_map),
    )

    # State for incident polling and SHM
    shm_state = {}
    last_incident_check = time.time()
    known_incident_ids = set()
    last_shm_broadcast = 0
    last_batch_cleanup = 0

    # Start the replay drain task
    drain_task = asyncio.create_task(replay_buffer.drain(broadcast))

    try:
        while True:
            loop_start = time.time()

            # Refresh fiber->org mapping periodically
            if loop_start - last_map_refresh > MAP_REFRESH_INTERVAL:
                fiber_org_map = await _load_fiber_org_map()
                infra_org_map = _load_infra_org_map(infrastructure)
                last_map_refresh = loop_start

            # --- Poll Kafka (non-blocking) ---
            msg = consumer.poll(timeout=0.05)
            if msg is not None:
                if msg.error():
                    if msg.error().code() != KafkaError._PARTITION_EOF:
                        logger.error('Kafka error: %s', msg.error())
                else:
                    topic = msg.topic()
                    if topic == 'das.speeds':
                        _handle_speed_message(msg.value(), replay_buffer)
                    elif topic == 'das.counts':
                        _handle_count_message(msg.value(), replay_buffer)

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
                    # Group by org via infrastructure ownership
                    org_shm: dict[str, list[dict]] = {}
                    for shm in readings:
                        org_id = infra_org_map.get(shm['infrastructureId'], '')
                        if org_id:
                            org_shm.setdefault(org_id, []).append(shm)

                    # Superuser group gets all
                    await channel_layer.group_send(
                        'realtime_shm_readings_org___all__',
                        {'type': 'broadcast_message', 'channel': 'shm_readings', 'data': readings},
                    )
                    # Per-org
                    for org_id, org_readings in org_shm.items():
                        await channel_layer.group_send(
                            f'realtime_shm_readings_org_{org_id}',
                            {'type': 'broadcast_message', 'channel': 'shm_readings', 'data': org_readings},
                        )

            # --- Cleanup stale batch trackers every 30s ---
            if (now - last_batch_cleanup) >= 30:
                last_batch_cleanup = now
                replay_buffer.cleanup_stale_batches()
                if replay_buffer.queue_size > 0:
                    logger.debug(
                        'Replay buffer: %d queued, %d active batches',
                        replay_buffer.queue_size, replay_buffer.active_batches,
                    )

            # Yield to event loop
            elapsed = time.time() - loop_start
            await asyncio.sleep(max(0, 0.01 - elapsed))

    except KeyboardInterrupt:
        logger.info('Kafka bridge shutting down...')
    finally:
        replay_buffer.stop()
        drain_task.cancel()
        try:
            await drain_task
        except asyncio.CancelledError:
            pass
        consumer.close()
        logger.info('Kafka consumer closed.')


def _handle_speed_message(value: bytes, replay_buffer) -> None:
    """Parse speed message, transform, and ingest into replay buffer."""
    data = _parse_speed_message(value)
    if data is None:
        return

    fiber_id = data.get('fiber_id', '')
    timestamp_ns = data.get('timestamp_ns', 0)
    channel_start = data.get('channel_start', 0)
    ai_metadata = data.get('ai_metadata', {})
    time_index = ai_metadata.get('time_index', -1)

    section_key = f'{fiber_id}:{channel_start}'

    detections = transform_speed_message(data)
    if detections:
        replay_buffer.ingest_speed(section_key, timestamp_ns, time_index, detections)


def _handle_count_message(value: bytes, replay_buffer) -> None:
    """Parse count message, transform, and ingest into replay buffer."""
    result = transform_count_message(value)
    if result is not None:
        count_data, section_key, count_timestamp_ns = result
        replay_buffer.ingest_count(section_key, count_timestamp_ns, count_data)


async def _poll_incidents(channel_layer, known_incident_ids: set, fiber_org_map: dict[str, list[str]]):
    """
    Poll ClickHouse for active incidents and broadcast changes (org-scoped).

    Compares current active incidents against known set to detect
    new incidents and resolutions.
    """
    from apps.shared.clickhouse import query
    from apps.shared.exceptions import ClickHouseUnavailableError

    try:
        rows = query("""
            SELECT
                incident_id, incident_type, severity, fiber_id,
                channel_start, timestamp, status, duration_seconds
            FROM sequoia.fiber_incidents
            FINAL
            WHERE status = 'active'
            ORDER BY timestamp DESC
            LIMIT 200
        """)
    except ClickHouseUnavailableError:
        logger.debug('ClickHouse unavailable for incident polling')
        return

    current_ids = set()
    for row in rows:
        iid = row['incident_id']
        current_ids.add(iid)

        if iid not in known_incident_ids:
            # New incident -- broadcast to owning orgs
            inc_data = transform_incident_row(row)
            await _org_broadcast(channel_layer, 'incidents', inc_data, fiber_org_map)

    # Detect resolved incidents (were known, no longer active)
    resolved_ids = known_incident_ids - current_ids
    for rid in resolved_ids:
        resolved_data = {
            'id': rid,
            'status': 'resolved',
            'type': '', 'severity': '', 'fiberLine': '',
            'channel': 0, 'detectedAt': '', 'duration': None,
        }
        # Resolved incidents have empty fiberLine, so broadcast to all orgs
        await _org_broadcast(channel_layer, 'incidents', resolved_data, fiber_org_map)

    known_incident_ids.clear()
    known_incident_ids.update(current_ids)
