"""
Redis-backed simulation state store.

Replaces module-level globals with Redis cache so that simulation state
is accessible across processes (simulation subprocess → gunicorn workers).

Write side: called by the simulation loop to persist state.
Read side: called by REST views and WebSocket consumers to query state.

Uses Django's cache framework (Redis backend) with short TTLs — if the
simulation stops, stale data expires automatically.
"""

import logging
import time

from django.core.cache import cache

logger = logging.getLogger("sequoia.simulation")

# Redis key prefix — all simulation state lives under this namespace
_PREFIX = "sim:"

# TTLs (seconds) — data expires if the simulation stops writing
_INCIDENTS_TTL = 30
_SNAPSHOTS_TTL = 30
_STATS_TTL = 30
_HISTORY_TTL = 600  # 10 min — simulation overwrites every 1s, TTL is the only eviction
_STATUS_TTL = 15


# ---------------------------------------------------------------------------
# Write side (called from simulation subprocess)
# ---------------------------------------------------------------------------


def store_incidents(incidents: list) -> None:
    """Store transformed simulation incidents."""
    cache.set(f"{_PREFIX}incidents", incidents, _INCIDENTS_TTL)


def store_snapshots(snapshots: dict[str, dict]) -> None:
    """Store incident snapshot data (pre-converted to points)."""
    cache.set(f"{_PREFIX}snapshots", snapshots, _SNAPSHOTS_TTL)


def store_stats(stats: dict[str, int]) -> None:
    """Store simulation-wide stats."""
    cache.set(f"{_PREFIX}stats", stats, _STATS_TTL)


def store_section_history(
    per_second: dict[str, list[dict]],
    per_minute: dict[str, list[dict]],
) -> None:
    """Store section history buffers, sharded by fiber+direction.

    Input keys are "fiber_id:direction:channel" strings.  We group by
    fiber+direction and store each shard in its own Redis key so that
    reads only deserialize the channels they need.
    """
    _store_history_shards(f"{_PREFIX}history:sec", per_second)
    _store_history_shards(f"{_PREFIX}history:min", per_minute)


def _store_history_shards(prefix: str, buf: dict[str, list[dict]]) -> None:
    """Group channel entries by fiber+direction and store each shard."""
    shards: dict[str, dict[str, list[dict]]] = {}
    shard_keys: set[str] = set()

    for key_str, entries in buf.items():
        fid, d_str, ch_str = key_str.split(":", maxsplit=2)
        shard_key = f"{prefix}:{fid}:{d_str}"
        shard_keys.add(shard_key)
        if shard_key not in shards:
            shards[shard_key] = {}
        shards[shard_key][ch_str] = entries

    for shard_key, data in shards.items():
        cache.set(shard_key, data, _HISTORY_TTL)

    # Store index of active shard keys so readers know what exists
    cache.set(f"{prefix}:_index", list(shard_keys), _HISTORY_TTL)


def store_status(running: bool) -> None:
    """Store simulation running status."""
    cache.set(f"{_PREFIX}status", {"running": running, "ts": time.time()}, _STATUS_TTL)


# ---------------------------------------------------------------------------
# Read side (called from gunicorn workers / REST views)
# ---------------------------------------------------------------------------


def get_incidents() -> list:
    """Get current simulation incidents."""
    return cache.get(f"{_PREFIX}incidents") or []


def get_snapshot(incident_id: str) -> dict | None:
    """Get snapshot for a specific incident."""
    snapshots = cache.get(f"{_PREFIX}snapshots") or {}
    return snapshots.get(incident_id)


def get_stats() -> dict[str, int]:
    """Get simulation-wide stats."""
    return cache.get(f"{_PREFIX}stats") or {}


def get_section_history(
    fiber_id: str,
    direction: int,
    channel_start: int,
    channel_end: int,
    minutes: int,
    since_ms: int | None = None,
) -> list[dict]:
    """Query section history from Redis-cached simulation buffers.

    Uses sharded Redis keys (one per fiber+direction) so only the
    relevant channels are deserialized.

    Resolution:
        - <=5 min -> per-second buffer (1s buckets)
        - >5 min  -> per-minute buffer (60s buckets)

    Returns ``[{time, speed, speedMax, samples, flow, occupancy}, ...]``.
    """
    from apps.monitoring.section_service import compute_occupancy

    if minutes <= 5:
        prefix = f"{_PREFIX}history:sec"
        bucket_seconds = 1
    else:
        prefix = f"{_PREFIX}history:min"
        bucket_seconds = 60

    # Read only the shard for this fiber+direction
    shard_key = f"{prefix}:{fiber_id}:{direction}"
    shard: dict[str, list[dict]] = cache.get(shard_key) or {}

    if not shard:
        return []

    now_ms = int(time.time() * 1000)
    cutoff_ms = now_ms - minutes * 60 * 1000
    if since_ms is not None:
        cutoff_ms = max(cutoff_ms, since_ms)

    points: list[dict] = []
    for ch_str, entries in shard.items():
        ch = int(ch_str)
        if ch < channel_start or ch > channel_end:
            continue
        for entry in entries:
            if entry["time"] <= cutoff_ms:
                continue
            points.append(entry)

    # Aggregate by time bucket
    total_channels = max(1, channel_end - channel_start + 1)
    buckets: dict[int, dict] = {}
    for p in points:
        t = p["time"]
        if t not in buckets:
            buckets[t] = {
                "speed_sum": 0.0,
                "speed_max": 0.0,
                "n_channels": 0,
                "vehicle_count": 0,
            }
        b = buckets[t]
        b["speed_sum"] += p["speed"]
        b["speed_max"] = max(b["speed_max"], p["speedMax"])
        b["n_channels"] += 1
        b["vehicle_count"] += p["vehicle_count"]

    result = []
    for t in sorted(buckets):
        b = buckets[t]
        avg_speed = b["speed_sum"] / b["n_channels"] if b["n_channels"] > 0 else 0
        avg_per_channel = b["vehicle_count"] / total_channels
        flow = round(avg_per_channel * (3600 / bucket_seconds))
        occupancy = compute_occupancy(avg_speed, flow)
        result.append(
            {
                "time": t,
                "speed": round(avg_speed, 1),
                "speedMax": round(b["speed_max"], 1),
                "samples": b["vehicle_count"],
                "flow": flow,
                "occupancy": occupancy,
            }
        )
    return result


def is_running() -> bool:
    """Check if simulation is currently running."""
    status: dict | None = cache.get(f"{_PREFIX}status")
    if not status:
        return False
    # Consider stale if no update in 2x TTL
    running: bool = status.get("running", False)
    fresh = (time.time() - status.get("ts", 0)) < _STATUS_TTL * 2
    return running and fresh
