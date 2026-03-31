"""
Module-level simulation caches and their accessors/updaters.

Written by the async simulation loop, read by sync REST views.
Uses atomic reference swap (GIL-safe) instead of locks to avoid
blocking the event loop on contention.

Moved to ``apps.shared`` so that ``apps.monitoring`` views can read
simulation state without importing from ``apps.realtime``.
"""

import time
from collections import deque

from apps.shared.constants import SNAPSHOT_CHANNEL_RADIUS, SNAPSHOT_WINDOW_S
from apps.shared.incident_service import transform_simulation_incident
from apps.shared.traffic_utils import compute_occupancy

# Global cache for simulation incidents (used by REST API fallback).
_simulation_incidents_cache: list = []

# Global cache for incident snapshots — recorded detections near each incident.
# Each entry: {"points": [...], "complete": bool}
_simulation_snapshots: dict[str, dict] = {}

# Global cache for simulation-wide stats (fiber/channel/vehicle counts).
_simulation_stats: dict[str, int] = {}

# Section history buffers — keyed by (fiber_id, direction, channel).
# Per-second: 5 min retention, aggregated once per second.
# Per-minute: 60 min retention, aggregated from per-second every 60s.
# Each entry: {time: epoch_ms, speed: float, speedMax: float, samples: int}
# maxlen caps memory even if time-based eviction misses entries.
_simulation_per_second_buffer: dict[tuple[str, int, int], deque[dict]] = {}
_simulation_per_minute_buffer: dict[tuple[str, int, int], deque[dict]] = {}
_SEC_BUFFER_MAXLEN = 400  # 5 min + headroom
_MIN_BUFFER_MAXLEN = 70  # 60 min + headroom


# ---------------------------------------------------------------------------
# Public accessors
# ---------------------------------------------------------------------------


def get_simulation_incidents() -> list:
    """Get current simulation incidents for REST API fallback."""
    return list(_simulation_incidents_cache)


def get_simulation_snapshot(incident_id: str) -> dict | None:
    """Get recorded snapshot for a simulated incident, or None.

    Returns {"points": [...], "complete": bool} or None.
    Each point: {"time": epoch_ms, "speed": float|null, "flow": int|null, "occupancy": float|null}
    """
    entry = _simulation_snapshots.get(incident_id)
    if entry is not None:
        return {"points": list(entry["points"]), "complete": entry["complete"]}
    return None


def get_simulation_stats() -> dict[str, int]:
    """Get simulation-wide stats (fiber count, channel count, active vehicles)."""
    return dict(_simulation_stats)


def get_simulation_section_history(
    fiber_id: str,
    direction: int,
    channel_start: int,
    channel_end: int,
    minutes: int,
    since_ms: int | None = None,
) -> list[dict]:
    """Query in-memory simulation buffers for section history.

    - ≤5 min → per-second buffer (1s resolution)
    - >5 min → per-minute buffer (1min resolution)

    Args:
        since_ms: If provided, only return points after this timestamp (ms epoch).

    Returns ``[{time, speed, speedMax, samples, flow, occupancy}, ...]``.
    """
    if minutes <= 5:
        buf = _simulation_per_second_buffer
        bucket_seconds = 1
    else:
        buf = _simulation_per_minute_buffer
        bucket_seconds = 60

    if not buf:
        return []

    now_ms = int(time.time() * 1000)
    cutoff_ms = now_ms - minutes * 60 * 1000
    if since_ms is not None:
        cutoff_ms = max(cutoff_ms, since_ms)
    points: list[dict] = []

    for (fid, d, ch), entries in buf.items():
        if fid != fiber_id or d != direction:
            continue
        if ch < channel_start or ch > channel_end:
            continue
        for entry in entries:
            if entry["time"] <= cutoff_ms:
                continue
            points.append(entry)

    # Aggregate by time bucket (multiple channels contribute to the same second/minute)
    # Divide total vehicle detections by total section channels to get the average
    # flow at a single point — this avoids inflating flow by the section length.
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
        # Flow (veh/h) = total detections / total channels * (3600 / bucket_seconds)
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


# ---------------------------------------------------------------------------
# Internal updaters (called by the simulation loop)
# ---------------------------------------------------------------------------


def _update_simulation_incidents_cache(incidents: list) -> None:
    """Update the global incidents cache from simulation engine."""
    global _simulation_incidents_cache
    _simulation_incidents_cache = [transform_simulation_incident(i) for i in incidents]


def _buckets_to_points(snap: dict, now_ms: float) -> list[dict]:
    """Convert aggregation buckets to time-series points.

    Skips the bucket currently being filled (partial second) to avoid
    showing artificially low values that get corrected on the next poll.
    """
    start_ms = snap["start_ms"]
    # Bucket index of the current (incomplete) second
    current_bucket = int((now_ms - start_ms) / 1000) if not snap["complete"] else -1
    points = []
    for s in range(SNAPSHOT_WINDOW_S * 2):
        b = snap["buckets"][s]
        t = start_ms + s * 1000
        if s == current_bucket or b["speed_count"] == 0:
            points.append({"time": t, "speed": None, "flow": None, "occupancy": None})
        else:
            avg_speed = round(b["speed_sum"] / b["speed_count"])
            # flow: raw vehicle count across ±SNAPSHOT_CHANNEL_RADIUS window per 1s bucket
            # Normalize to per-channel then scale to veh/h (same as section history)
            total_ch = max(1, SNAPSHOT_CHANNEL_RADIUS * 2)
            flow_vph = round(b["vehicle_count"] / total_ch * 3600)
            occupancy = compute_occupancy(avg_speed, flow_vph)
            points.append({"time": t, "speed": avg_speed, "flow": flow_vph, "occupancy": occupancy})
    return points


def _update_simulation_stats(engine) -> None:
    """Update the global stats cache from the simulation engine."""
    global _simulation_stats
    _simulation_stats = {
        "fiber_count": len(engine.fibers),
        "total_channels": sum(f.channel_count for f in engine.fibers),
        "active_vehicles": len(engine.vehicles),
    }


def _update_simulation_snapshots(snapshots: dict[str, dict]) -> None:
    """Replace the global snapshots cache with the engine's aggregated points."""
    global _simulation_snapshots
    now_ms = time.time() * 1000
    converted = {}
    for iid, snap in snapshots.items():
        converted[iid] = {
            "points": _buckets_to_points(snap, now_ms),
            "complete": snap["complete"],
        }
    _simulation_snapshots = converted
