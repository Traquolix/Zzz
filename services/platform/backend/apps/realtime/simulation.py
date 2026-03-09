"""
Traffic simulation engine — physically coherent vehicle simulation.

Generates realistic traffic data (vehicles, detections, incidents, SHM readings)
and broadcasts them through Django Channels groups.

Architecture:
    Vehicle Physics → Detections → Incident Overseer → Incidents
    - Vehicles only see other vehicles (car-following), never incidents directly
    - Road Events (stopped vehicle, slow vehicle, lane closure) cause physical
      obstructions that propagate upstream via car-following
    - The Overseer monitors aggregated speed metrics and declares incidents
      when it detects anomalies — incidents emerge from behavior, not RNG

This runs as a background async loop, started by the `run_simulation` management command.

Org-scoped: broadcasts are sent to org-specific groups via fiber_org_map.
Superuser clients join the __all__ group which always receives all data.
"""

import asyncio
import logging
import math
import random
import time
import uuid
from dataclasses import dataclass
from typing import Optional, TypedDict

from channels.layers import get_channel_layer

from apps.alerting.integration import check_alerts_for_detections, check_alerts_for_incident
from apps.monitoring.section_service import compute_occupancy
from apps.realtime.broadcast import (
    broadcast_to_orgs,
    group_by_org,
    load_fiber_org_map,
    pubsub_broadcast_detections,
    pubsub_broadcast_shm,
)
from apps.shared.constants import MAP_REFRESH_INTERVAL

logger = logging.getLogger("sequoia.simulation")

# Global cache for simulation incidents (used by REST API fallback).
# Written by the async simulation loop, read by sync REST views.
# Uses atomic reference swap (GIL-safe) instead of locks to avoid
# blocking the event loop on contention.
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
_simulation_per_second_buffer: dict[tuple[str, int, int], list[dict]] = {}
_simulation_per_minute_buffer: dict[tuple[str, int, int], list[dict]] = {}


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


def _update_simulation_incidents_cache(incidents: list):
    """Update the global incidents cache from simulation engine."""
    from apps.monitoring.incident_service import transform_simulation_incident

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


def _update_simulation_stats(engine: "SimulationEngine"):
    """Update the global stats cache from the simulation engine."""
    global _simulation_stats
    _simulation_stats = {
        "fiber_count": len(engine.fibers),
        "total_channels": sum(f.channel_count for f in engine.fibers),
        "active_vehicles": len(engine.vehicles),
    }


def _update_simulation_snapshots(snapshots: dict[str, dict]):
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


# ============================================================================
# TYPES
# ============================================================================


@dataclass
class FiberConfig:
    id: str
    name: str
    color: str
    coordinates: list
    channel_count: int
    lanes: int = 4
    speed_limit: float = 110.0
    traffic_density: str = "medium"
    # Per-fiber calibration: typical free-flow speed range [min, max] km/h
    typical_speed_range: tuple[float, float] = (60.0, 90.0)
    # Per-direction channel limits: channels beyond these are off-road / dead fiber.
    # None means use full channel_count.
    max_channel_dir0: int | None = None
    max_channel_dir1: int | None = None
    # Per-fiber daily traffic curve (24 values, 0.0-1.0).
    # None means use the default curve.
    daily_traffic: list[float] | None = None


@dataclass
class Vehicle:
    id: str
    fiber_line: str
    channel: float
    speed: float
    target_speed: float
    direction: int  # 0 or 1
    lane: int
    vehicle_type: str
    aggressiveness: float
    created_at: float
    # Road event: if set, this vehicle is affected by a road event
    # and has a forced target speed override
    forced_speed: float | None = None


@dataclass
class Detection:
    fiber_line: str
    channel: int
    speed: float
    count: int
    n_cars: int
    n_trucks: int
    direction: int
    timestamp: int


@dataclass
class Incident:
    id: str
    type: str
    severity: str
    fiber_line: str
    direction: int
    channel: int
    detected_at: str
    detected_at_ms: float  # Wall-clock ms at creation (avoids UTC/local parsing bugs)
    status: str = "active"
    duration: Optional[float] = None


@dataclass
class RoadEvent:
    """A physical road event that affects vehicle behavior.

    Unlike Incidents (which are *detected* anomalies), RoadEvents are the *causes*:
    a stopped vehicle, a slow vehicle, or a lane closure. The car-following model
    propagates their effects upstream naturally.
    """

    id: str
    fiber_id: str
    direction: int
    channel: float
    event_type: str  # "stopped_vehicle", "slow_vehicle", "lane_closure"
    created_at: float  # wall-clock seconds
    duration_s: float  # how long the event lasts (real-time seconds)
    affected_lane: int
    # For slow_vehicle: the forced speed (km/h). For stopped_vehicle: 0.
    forced_speed: float = 0.0


@dataclass
class SHMReading:
    infrastructure_id: str
    frequency: float
    amplitude: float
    timestamp: int


# ============================================================================
# VEHICLE PHYSICS
# ============================================================================

VEHICLE_PROFILES = {
    "car": {"min_speed": 30, "max_speed": 130, "accel": 3.5, "decel": 6, "length": 1.5},
    "truck": {"min_speed": 30, "max_speed": 90, "accel": 1.5, "decel": 4, "length": 4},
    "motorcycle": {"min_speed": 30, "max_speed": 150, "accel": 5, "decel": 7, "length": 0.8},
    "bus": {"min_speed": 30, "max_speed": 100, "accel": 2, "decel": 5, "length": 3.5},
}

METERS_PER_CHANNEL = 5
SAFE_FOLLOWING_SECONDS = 2
MIN_GAP_CHANNELS = 3
VEHICLE_TYPES = ["car", "car", "car", "car", "truck", "motorcycle", "bus"]

# Default daily traffic curve — generic French urban double-peak
DEFAULT_DAILY_TRAFFIC = [
    0.15,
    0.08,
    0.06,
    0.06,
    0.10,
    0.25,  # 00-05
    0.55,
    0.85,
    1.00,
    0.80,
    0.65,
    0.70,  # 06-11
    0.75,
    0.70,
    0.65,
    0.70,
    0.85,
    1.00,  # 12-17
    0.90,
    0.70,
    0.50,
    0.35,
    0.25,
    0.18,  # 18-23
]

# Per-fiber traffic curves — calibrated to Nice road characteristics
FIBER_DAILY_TRAFFIC: dict[str, list[float]] = {
    # D6202 / Carros: commuter highway, sharp peaks, low overnight
    "carros": [
        0.10,
        0.06,
        0.05,
        0.05,
        0.08,
        0.20,  # 00-05
        0.55,
        0.90,
        1.00,
        0.75,
        0.60,
        0.65,  # 06-11 (morning peak 07-09)
        0.70,
        0.65,
        0.60,
        0.70,
        0.90,
        1.00,  # 12-17 (evening peak 17-18)
        0.85,
        0.60,
        0.40,
        0.25,
        0.18,
        0.12,  # 18-23
    ],
    # Route de Turin / Mathis: urban road, steadier throughout day
    "mathis": [
        0.12,
        0.08,
        0.06,
        0.06,
        0.08,
        0.18,  # 00-05
        0.40,
        0.75,
        0.90,
        0.80,
        0.70,
        0.75,  # 06-11
        0.80,
        0.75,
        0.70,
        0.75,
        0.85,
        0.95,  # 12-17
        1.00,
        0.80,
        0.55,
        0.35,
        0.22,
        0.15,  # 18-23 (evening peak extends later)
    ],
    # Promenade des Anglais: tourist/coastal, late morning buildup, late evening
    "promenade": [
        0.18,
        0.12,
        0.08,
        0.06,
        0.08,
        0.15,  # 00-05
        0.35,
        0.65,
        0.85,
        0.80,
        0.75,
        0.80,  # 06-11
        0.85,
        0.80,
        0.75,
        0.80,
        0.90,
        1.00,  # 12-17
        0.95,
        0.85,
        0.65,
        0.45,
        0.30,
        0.22,  # 18-23 (tourist traffic extends late)
    ],
}

BASE_SPAWN_RATES = {"low": 4, "medium": 10, "high": 20}


class _SpawnPoint(TypedDict):
    fiber: str
    ch: int
    dir: int
    rate: float
    last: float


SEVERITIES = ["low", "medium", "high", "critical"]

SNAPSHOT_CHANNEL_RADIUS = 30  # ±30 channels (~300m) around incident center
SNAPSHOT_WINDOW_S = 60  # Record ±60s around incident detected_at
AVG_VEHICLE_LENGTH_M = 6  # For occupancy estimation

INFRA_BASE_FREQ = {"bridge": 5.0, "tunnel": 15.0}


def _weighted_choice(items: list[str], weights: list[float]) -> str:
    total = sum(weights)
    r = random.random() * total
    for item, w in zip(items, weights):
        r -= w
        if r <= 0:
            return item
    return items[-1]


def _get_max_channel(fiber: FiberConfig, direction: int) -> int:
    """Get the maximum valid channel for a fiber+direction."""
    if direction == 0 and fiber.max_channel_dir0 is not None:
        return fiber.max_channel_dir0
    if direction == 1 and fiber.max_channel_dir1 is not None:
        return fiber.max_channel_dir1
    return fiber.channel_count


def _create_vehicle(fiber: FiberConfig, channel: float, direction: int, lane: int) -> Vehicle:
    vtype = random.choice(VEHICLE_TYPES)
    profile = VEHICLE_PROFILES[vtype]
    # Use fiber's typical speed range for target speed
    low, high = fiber.typical_speed_range
    target = low + random.random() * (high - low)
    # Cap at vehicle profile max and fiber speed limit
    target = min(target, profile["max_speed"], fiber.speed_limit)
    return Vehicle(
        id=f"v-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}",
        fiber_line=fiber.id,
        channel=channel,
        speed=target * (0.7 + random.random() * 0.3),
        target_speed=target,
        direction=direction,
        lane=lane,
        vehicle_type=vtype,
        aggressiveness=random.random(),
        created_at=time.time(),
    )


def _update_vehicle(
    v: Vehicle,
    vehicles: list[Vehicle],
    fiber: FiberConfig,
    delta_s: float,
) -> Optional[Vehicle]:
    """Update a single vehicle's speed and position using car-following physics.

    Vehicles only see other vehicles — they don't know about incidents.
    Road events work by setting forced_speed on the affected vehicle,
    which then naturally slows down traffic behind it via car-following.
    """
    profile = VEHICLE_PROFILES[v.vehicle_type]

    # Bounds check: remove vehicles outside valid channel range
    max_ch = _get_max_channel(fiber, v.direction)
    if v.channel < 0 or v.channel >= max_ch:
        return None
    if time.time() - v.created_at > 600:
        return None

    # Find vehicle ahead in same lane
    ahead = [
        o
        for o in vehicles
        if o.id != v.id
        and o.fiber_line == v.fiber_line
        and o.lane == v.lane
        and o.direction == v.direction
        and (
            (v.direction == 0 and o.channel > v.channel)
            or (v.direction == 1 and o.channel < v.channel)
        )
    ]
    if ahead:
        ahead.sort(key=lambda o: abs(o.channel - v.channel))
        vehicle_ahead = ahead[0]
    else:
        vehicle_ahead = None

    # Use forced_speed if this vehicle is affected by a road event
    effective_target = v.forced_speed if v.forced_speed is not None else v.target_speed

    # Car-following model (IDM-inspired)
    new_speed = v.speed
    if vehicle_ahead:
        gap = abs(vehicle_ahead.channel - v.channel) - profile["length"]
        safe_gap = MIN_GAP_CHANNELS + (v.speed / 3.6) * SAFE_FOLLOWING_SECONDS / METERS_PER_CHANNEL
        if gap < safe_gap:
            rel_speed = v.speed - vehicle_ahead.speed
            braking = min(1.0, (safe_gap - gap) / safe_gap + rel_speed / 50)
            new_speed -= profile["decel"] * delta_s * braking * (2 - v.aggressiveness)
        elif gap < safe_gap * 2:
            target_match = vehicle_ahead.speed * 0.95
            if v.speed > target_match:
                new_speed -= profile["decel"] * delta_s * 0.3
            else:
                new_speed += profile["accel"] * delta_s * 0.5
        else:
            if v.speed < effective_target:
                new_speed += profile["accel"] * delta_s
            elif v.speed > effective_target:
                new_speed -= profile["decel"] * delta_s * 0.5
    else:
        if v.speed < effective_target:
            new_speed += profile["accel"] * delta_s
        elif v.speed > effective_target:
            new_speed -= profile["decel"] * delta_s * 0.3

    new_speed = max(0.0, min(profile["max_speed"], new_speed))

    # Move
    m_per_ms = (new_speed * 1000) / 3_600_000
    ch_per_ms = m_per_ms / METERS_PER_CHANNEL
    ch_delta = ch_per_ms * (delta_s * 1000) * (1 if v.direction == 0 else -1)

    v.speed = new_speed
    v.channel += ch_delta
    return v


# ============================================================================
# INCIDENT OVERSEER — detects incidents from vehicle behavior
# ============================================================================


@dataclass
class _SectionMetrics:
    """Rolling EMA metrics for a (fiber, direction) channel window."""

    # Exponential moving average of speed (initialized to free-flow)
    ema_speed: float = 80.0
    # Minimum speed seen in recent ticks (decays toward ema_speed)
    recent_min_speed: float = 999.0
    # Baseline free-flow speed for comparison
    free_flow_speed: float = 80.0
    # How long the anomaly has persisted (real-time seconds)
    anomaly_duration_s: float = 0.0
    # Whether we already declared an incident for this anomaly
    incident_declared: bool = False
    incident_id: str | None = None
    # Track when last detection was seen
    last_detection_time: float = 0.0

    @property
    def speed_drop_pct(self) -> float:
        if self.free_flow_speed <= 0:
            return 0.0
        return max(0.0, (1.0 - self.ema_speed / self.free_flow_speed) * 100)


class IncidentOverseer:
    """Monitors detection metrics and declares incidents when speed anomalies are detected.

    Uses per-detection EMA (exponential moving average) instead of per-tick window
    averaging. Each detection updates the EMA for the nearest monitoring point.
    This means a single stopped vehicle at 0 km/h will quickly pull the local
    EMA down, triggering incident detection.

    Monitoring points are spaced every WINDOW_STEP channels. Each detection
    updates the nearest point's EMA. Smaller spacing = more granular detection.
    """

    WINDOW_STEP = 30  # Monitoring points every 30 channels (~150m)
    EMA_ALPHA = 0.15  # EMA smoothing factor (higher = more responsive)
    MIN_SPEED_DECAY = 0.05  # recent_min_speed decays toward ema_speed per tick
    # Thresholds for incident detection
    SPEED_DROP_PCT_THRESHOLD = 40  # 40% drop from free-flow triggers incident
    MIN_ANOMALY_DURATION_S = 15  # Anomaly must persist 15s before declaring incident
    RECOVERY_PCT = 75  # Speed must recover to 75% of free-flow
    RECOVERY_DURATION_S = 20  # Must stay recovered for 20s
    # Spatial deduplication: no new incident within this many channels of an existing one
    INCIDENT_MIN_SPACING_CH = 120  # ~600m between incidents on same fiber/direction

    def __init__(self, fibers: list[FiberConfig]):
        # Per-point metrics: keyed by (fiber_id, direction, channel_point)
        self._metrics: dict[tuple[str, int, int], _SectionMetrics] = {}
        self._recovery_timers: dict[str, float] = {}
        for fiber in fibers:
            for direction in (0, 1):
                max_ch = _get_max_channel(fiber, direction)
                low, high = fiber.typical_speed_range
                free_flow = (low + high) / 2
                for ch in range(0, max_ch, self.WINDOW_STEP):
                    key = (fiber.id, direction, ch)
                    self._metrics[key] = _SectionMetrics(
                        ema_speed=free_flow,
                        free_flow_speed=free_flow,
                    )

    def _nearest_point(self, channel: int) -> int:
        """Snap a channel to the nearest monitoring point."""
        return round(channel / self.WINDOW_STEP) * self.WINDOW_STEP

    def ingest_detections(self, detections: list[Detection], delta_s: float):
        """Update EMA speed at monitoring points from detections."""
        now = time.time()

        # Update EMA for each detection at its nearest monitoring point
        for d in detections:
            pt = self._nearest_point(d.channel)
            key = (d.fiber_line, d.direction, pt)
            m = self._metrics.get(key)
            if m is None:
                continue
            # EMA update: new_ema = alpha * observation + (1 - alpha) * old_ema
            m.ema_speed = self.EMA_ALPHA * d.speed + (1 - self.EMA_ALPHA) * m.ema_speed
            m.recent_min_speed = min(m.recent_min_speed, d.speed)
            m.last_detection_time = now

        # Update anomaly durations and decay min_speed
        for m in self._metrics.values():
            # Only track anomalies at points that have recent detections
            if now - m.last_detection_time > 10:
                m.anomaly_duration_s = max(0, m.anomaly_duration_s - delta_s)
                continue
            # Decay recent_min_speed toward ema_speed
            m.recent_min_speed += (m.ema_speed - m.recent_min_speed) * self.MIN_SPEED_DECAY
            if m.speed_drop_pct >= self.SPEED_DROP_PCT_THRESHOLD:
                m.anomaly_duration_s += delta_s
            else:
                m.anomaly_duration_s = max(0, m.anomaly_duration_s - delta_s * 2)

    def check_for_incidents(
        self,
        now: float,
        now_ms: float,
        fibers: list[FiberConfig],
        existing_incidents: list[Incident] | None = None,
    ) -> list[Incident]:
        """Check all monitoring points for new incidents."""
        new_incidents: list[Incident] = []
        # Build set of active incident locations for spatial dedup
        active_locations: list[tuple[str, int, int]] = []
        for inc in existing_incidents or []:
            if inc.status == "active":
                active_locations.append((inc.fiber_line, inc.direction, inc.channel))
        # Include newly declared incidents in this tick too
        for inc in new_incidents:
            active_locations.append((inc.fiber_line, inc.direction, inc.channel))

        for (fiber_id, direction, ch), m in self._metrics.items():
            if m.incident_declared:
                continue
            if m.anomaly_duration_s < self.MIN_ANOMALY_DURATION_S:
                continue
            if m.speed_drop_pct < self.SPEED_DROP_PCT_THRESHOLD:
                continue

            # Spatial dedup: skip if too close to an existing active incident
            too_close = any(
                fid == fiber_id and d == direction and abs(c - ch) < self.INCIDENT_MIN_SPACING_CH
                for fid, d, c in active_locations
            )
            if too_close:
                continue

            # Determine incident type and severity
            ema = m.ema_speed
            drop_pct = m.speed_drop_pct

            if ema < 5:
                inc_type = "accident"
            elif drop_pct > 70:
                inc_type = "congestion"
            elif drop_pct > 50:
                inc_type = "slowdown"
            else:
                inc_type = "anomaly"

            if drop_pct > 80 or ema < 5:
                severity = "critical"
            elif drop_pct > 60:
                severity = "high"
            elif drop_pct > 50:
                severity = "medium"
            else:
                severity = "low"

            fiber = next((f for f in fibers if f.id == fiber_id), None)
            inc_ch = min(ch, _get_max_channel(fiber, direction) - 1) if fiber else ch

            inc_id = f"inc-{int(now_ms)}-{uuid.uuid4().hex[:4]}"
            inc = Incident(
                id=inc_id,
                type=inc_type,
                severity=severity,
                fiber_line=fiber_id,
                channel=inc_ch,
                detected_at=time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(now)),
                detected_at_ms=now_ms,
                direction=direction,
                status="active",
            )
            m.incident_declared = True
            m.incident_id = inc_id
            new_incidents.append(inc)
            active_locations.append((fiber_id, direction, inc_ch))
            logger.info(
                "Incident detected: %s %s on %s dir %d ch %d (EMA=%.1f, drop=%.0f%%)",
                inc_type,
                severity,
                fiber_id,
                direction,
                inc_ch,
                ema,
                drop_pct,
            )

        return new_incidents

    def check_for_resolutions(self, incidents: list[Incident], now: float) -> list[Incident]:
        """Check if any active incidents should be resolved (speed recovered)."""
        resolved: list[Incident] = []
        for inc in incidents:
            if inc.status != "active":
                continue
            # Find the monitoring point that declared this incident
            point_key = None
            for key, m in self._metrics.items():
                if m.incident_id == inc.id:
                    point_key = key
                    break
            if point_key is None:
                continue

            m = self._metrics[point_key]
            recovered = m.ema_speed >= m.free_flow_speed * (self.RECOVERY_PCT / 100)
            if recovered:
                if inc.id not in self._recovery_timers:
                    self._recovery_timers[inc.id] = now
                elif now - self._recovery_timers[inc.id] >= self.RECOVERY_DURATION_S:
                    inc.status = "resolved"
                    m.incident_declared = False
                    m.incident_id = None
                    m.anomaly_duration_s = 0
                    self._recovery_timers.pop(inc.id, None)
                    resolved.append(inc)
                    logger.info("Incident resolved: %s on %s", inc.id, inc.fiber_line)
            else:
                self._recovery_timers.pop(inc.id, None)
                # Escalate severity if anomaly deepens
                drop_pct = m.speed_drop_pct
                if drop_pct > 80 and inc.severity != "critical":
                    inc.severity = "critical"
                elif drop_pct > 60 and inc.severity in ("low", "medium"):
                    inc.severity = "high"

        return resolved


# ============================================================================
# ROAD EVENT SYSTEM — physical causes that trigger incidents
# ============================================================================


class RoadEventManager:
    """Spawns and manages road events that create physical obstructions.

    Events are the *causes* — stopped vehicles, slow vehicles, lane closures.
    They affect specific vehicles, which then propagate slowdowns upstream
    through the car-following model. The Overseer detects the resulting
    speed anomalies and declares incidents.
    """

    # Probabilities per sim-hour (scaled by traffic density)
    EVENT_RATES: dict[str, float] = {
        "stopped_vehicle": 0.4,  # Per sim-hour
        "slow_vehicle": 0.6,
        "lane_closure": 0.15,
    }

    # Duration ranges in sim-seconds
    EVENT_DURATIONS: dict[str, tuple[float, float]] = {
        "stopped_vehicle": (120, 600),  # 2-10 min sim time
        "slow_vehicle": (60, 300),  # 1-5 min sim time
        "lane_closure": (300, 1800),  # 5-30 min sim time
    }

    def __init__(self):
        self.events: list[RoadEvent] = []

    def tick(
        self,
        delta_s: float,
        sim_hour: float,
        vehicles: list[Vehicle],
        fibers: list[FiberConfig],
        hour_advance_rate: float,
        now: float,
    ) -> None:
        """Possibly spawn new events and update existing ones."""
        # Remove expired events and release affected vehicles
        expired = [e for e in self.events if now - e.created_at > e.duration_s]
        for e in expired:
            for v in vehicles:
                if v.fiber_line == e.fiber_id and v.forced_speed is not None:
                    # Only release if this vehicle is near the event
                    if abs(v.channel - e.channel) < 60:
                        v.forced_speed = None
        self.events = [e for e in self.events if now - e.created_at <= e.duration_s]

        # Enforce road events on nearby vehicles.
        # Track which vehicles are currently in any event's zone so we can
        # release those that have moved past all zones.
        affected_vehicle_ids: set[str] = set()
        for e in self.events:
            for v in vehicles:
                if v.fiber_line != e.fiber_id or v.direction != e.direction:
                    continue
                dist = abs(v.channel - e.channel)
                # Check if vehicle is upstream of the event (would approach it)
                upstream = (v.direction == 0 and v.channel < e.channel) or (
                    v.direction == 1 and v.channel > e.channel
                )
                if e.event_type == "stopped_vehicle":
                    if v.lane == e.affected_lane and dist < 5:
                        v.forced_speed = 0.0
                        affected_vehicle_ids.add(v.id)
                    elif dist < 40 and upstream:
                        # All lanes slow in the upstream approach zone
                        # Closer = slower (linear gradient)
                        approach_speed = 5.0 + (dist / 40) * 25.0  # 5-30 km/h
                        v.forced_speed = min(v.forced_speed or 999, approach_speed)
                        affected_vehicle_ids.add(v.id)
                    elif dist < 15:
                        # Downstream/adjacent rubbernecking
                        v.forced_speed = min(v.forced_speed or 999, 25.0)
                        affected_vehicle_ids.add(v.id)
                elif e.event_type == "slow_vehicle":
                    if v.lane == e.affected_lane and dist < 10:
                        v.forced_speed = e.forced_speed
                        affected_vehicle_ids.add(v.id)
                    elif dist < 30 and upstream:
                        approach_speed = e.forced_speed + (dist / 30) * 15.0
                        v.forced_speed = min(v.forced_speed or 999, approach_speed)
                        affected_vehicle_ids.add(v.id)
                elif e.event_type == "lane_closure":
                    if v.lane == e.affected_lane and dist < 10:
                        v.forced_speed = 0.0
                        affected_vehicle_ids.add(v.id)
                    elif dist < 50 and upstream:
                        approach_speed = 5.0 + (dist / 50) * 25.0
                        v.forced_speed = min(v.forced_speed or 999, approach_speed)
                        affected_vehicle_ids.add(v.id)
                    elif dist < 20:
                        v.forced_speed = min(v.forced_speed or 999, 15.0)
                        affected_vehicle_ids.add(v.id)

        # Release vehicles that have moved past all event zones
        for v in vehicles:
            if v.forced_speed is not None and v.id not in affected_vehicle_ids:
                v.forced_speed = None

        # Maybe spawn new events (probability per sim-hour, scaled by density)
        density = _get_density_multiplier(sim_hour, None)
        for event_type, base_rate in self.EVENT_RATES.items():
            # Real-time probability per tick
            rate = base_rate * density * hour_advance_rate
            prob_per_tick = rate * delta_s / 3600
            if random.random() > prob_per_tick:
                continue
            # Pick a fiber and find a vehicle to affect
            fiber = random.choice(fibers)
            fiber_vehicles = [
                v for v in vehicles if v.fiber_line == fiber.id and v.forced_speed is None
            ]
            if not fiber_vehicles:
                continue
            target = random.choice(fiber_vehicles)
            max_ch = _get_max_channel(fiber, target.direction)
            if target.channel < 10 or target.channel > max_ch - 10:
                continue

            # Duration in real-time seconds (divide by hour_advance_rate)
            dur_range = self.EVENT_DURATIONS[event_type]
            dur_sim = dur_range[0] + random.random() * (dur_range[1] - dur_range[0])
            dur_real = dur_sim / hour_advance_rate
            dur_real = max(dur_real, 30)  # Minimum 30s real-time

            forced_speed = 0.0
            if event_type == "slow_vehicle":
                forced_speed = 10 + random.random() * 20  # 10-30 km/h

            event = RoadEvent(
                id=f"evt-{int(now * 1000)}-{uuid.uuid4().hex[:4]}",
                fiber_id=fiber.id,
                direction=target.direction,
                channel=target.channel,
                event_type=event_type,
                created_at=now,
                duration_s=dur_real,
                affected_lane=target.lane,
                forced_speed=forced_speed,
            )
            self.events.append(event)

            # Immediately affect the target vehicle
            if event_type == "stopped_vehicle":
                target.forced_speed = 0.0
            elif event_type == "slow_vehicle":
                target.forced_speed = forced_speed

            logger.debug(
                "Road event: %s on %s dir %d ch %.0f lane %d (%.0fs real)",
                event_type,
                fiber.id,
                target.direction,
                target.channel,
                target.lane,
                dur_real,
            )


def _get_density_multiplier(sim_hour: float, fiber: FiberConfig | None) -> float:
    """Get traffic density multiplier for the current simulated hour."""
    curve = DEFAULT_DAILY_TRAFFIC
    if fiber is not None and fiber.daily_traffic is not None:
        curve = fiber.daily_traffic
    elif fiber is not None:
        curve = FIBER_DAILY_TRAFFIC.get(fiber.id, DEFAULT_DAILY_TRAFFIC)
    h = int(sim_hour) % 24
    h_next = (h + 1) % 24
    frac = sim_hour - int(sim_hour)
    return curve[h] + (curve[h_next] - curve[h]) * frac


# ============================================================================
# SIMULATION ENGINE
# ============================================================================


class SimulationEngine:
    """Self-contained traffic simulation with emergent incidents."""

    def __init__(self, fibers: list[FiberConfig], infrastructure: list[dict]):
        self.fibers = fibers
        self.infrastructure = infrastructure
        self.vehicles: list[Vehicle] = []
        self.incidents: list[Incident] = []
        # Real-clock mode: uncomment below for demos to sync with wall clock time.
        # import datetime
        # _now = datetime.datetime.now()
        # self.simulated_hour = _now.hour + _now.minute / 60 + _now.second / 3600
        # self.hour_advance_rate = 1
        self.simulated_hour = 8.0
        self.hour_advance_rate = 30  # 30x speed
        self.tick_count = 0

        # Recorded detections near each incident: incident_id → {detections, complete, start_ms, end_ms}
        # Fixed window: detected_at ± SNAPSHOT_WINDOW_S, capped at SNAPSHOT_MAX_DETECTIONS
        self.incident_snapshots: dict[str, dict] = {}

        # Rolling detection buffer per fiber — always keeps last SNAPSHOT_WINDOW_S seconds
        # Used to seed snapshots with pre-incident data when a new incident spawns
        self._detection_ring: dict[str, list[dict]] = {f.id: [] for f in fibers}

        # SHM state
        self.shm_base_freq: dict[str, float] = {}
        self.shm_phase: dict[str, float] = {}
        for infra in infrastructure:
            iid = infra["id"]
            self.shm_base_freq[iid] = (
                INFRA_BASE_FREQ.get(infra["type"], 10) + (random.random() - 0.5) * 2
            )
            self.shm_phase[iid] = random.random() * math.pi * 2

        # Spawn points — use per-direction channel limits
        self.spawn_points: list[_SpawnPoint] = []
        for fiber in fibers:
            rate = BASE_SPAWN_RATES.get(fiber.traffic_density, 10)
            max_ch_0 = _get_max_channel(fiber, 0)
            max_ch_1 = _get_max_channel(fiber, 1)
            # Direction 0: spawn at low channel end
            self.spawn_points.append(
                {"fiber": fiber.id, "ch": 5, "dir": 0, "rate": rate, "last": 0}
            )
            # Direction 1: spawn at high channel end (within valid range)
            self.spawn_points.append(
                {"fiber": fiber.id, "ch": max_ch_1 - 5, "dir": 1, "rate": rate, "last": 0}
            )
            # Mid-point spawners for long fibers
            if max_ch_0 > 200:
                mid = max_ch_0 // 2
                self.spawn_points.append(
                    {"fiber": fiber.id, "ch": mid, "dir": 0, "rate": rate * 0.3, "last": 0}
                )
            if max_ch_1 > 200:
                mid = max_ch_1 // 2
                self.spawn_points.append(
                    {"fiber": fiber.id, "ch": mid, "dir": 1, "rate": rate * 0.3, "last": 0}
                )

        # Road event manager (physical causes)
        self._road_events = RoadEventManager()

        # Incident overseer (detects anomalies from behavior)
        self._overseer = IncidentOverseer(fibers)

        # Section history: per-channel per-second accumulator
        # Keyed by (fiber_id, direction, channel), accumulates within the current second
        self._sec_accum: dict[tuple[str, int, int], dict] = {}
        self._sec_accum_bucket: int = 0  # Current second bucket (epoch_ms, floored)
        self._last_minute_rollup: float = 0.0  # Last time we rolled up per-minute data

        # Track when simulation started — incidents only spawn after warmup period
        # so snapshot data has time to accumulate
        self._started_at = time.time()
        self._incident_warmup_s = 120  # 2 minutes

    def tick(self, delta_ms: float) -> tuple[list[Detection], list[Incident], list[Incident]]:
        """Run one simulation tick. Returns (detections, new_incidents, resolved_incidents)."""
        delta_s = delta_ms / 1000
        self.tick_count += 1
        now = time.time()
        now_ms = now * 1000

        # Advance simulated time
        # Real-clock mode: uncomment below to sync with wall clock.
        # import datetime
        # _now = datetime.datetime.now()
        # self.simulated_hour = _now.hour + _now.minute / 60 + _now.second / 3600
        hours = (delta_ms / 1000 / 3600) * self.hour_advance_rate
        self.simulated_hour = (self.simulated_hour + hours) % 24

        # Update road events (spawn new ones, expire old ones, enforce on vehicles)
        past_warmup = now - self._started_at >= self._incident_warmup_s
        if past_warmup:
            self._road_events.tick(
                delta_s,
                self.simulated_hour,
                self.vehicles,
                self.fibers,
                self.hour_advance_rate,
                now,
            )

        # Update vehicles (pure car-following, no incident awareness)
        surviving = []
        for v in self.vehicles:
            fiber = next((f for f in self.fibers if f.id == v.fiber_line), None)
            if fiber:
                result = _update_vehicle(v, self.vehicles, fiber, delta_s)
                if result:
                    surviving.append(result)
        self.vehicles = surviving

        # Spawn new vehicles
        for sp in self.spawn_points:
            fiber = next((f for f in self.fibers if f.id == sp["fiber"]), None)
            if not fiber:
                continue
            density_mult = _get_density_multiplier(self.simulated_hour, fiber)
            eff_rate = sp["rate"] * density_mult
            ms_per_vehicle = 60_000 / max(eff_rate, 0.1)
            if (now_ms - sp["last"]) < ms_per_vehicle:
                continue
            too_close = any(
                v.fiber_line == sp["fiber"]
                and v.direction == sp["dir"]
                and abs(v.channel - sp["ch"]) < 15
                for v in self.vehicles
            )
            if too_close:
                continue
            lanes_per_dir = fiber.lanes // 2
            base_lane = 0 if sp["dir"] == 0 else lanes_per_dir
            lane = base_lane + random.randint(0, max(0, lanes_per_dir - 1))
            self.vehicles.append(_create_vehicle(fiber, sp["ch"], sp["dir"], lane))
            sp["last"] = now_ms

        # Generate detections (group nearby vehicles)
        detections = self._generate_detections()

        # Record detections near active incidents for snapshot queries
        self._record_incident_detections(detections, now_ms)

        # Feed detections to the overseer
        new_incidents: list[Incident] = []
        resolved_incidents: list[Incident] = []

        if past_warmup:
            self._overseer.ingest_detections(detections, delta_s)

            if not hasattr(self, "_warmup_logged"):
                self._warmup_logged = True
                logger.info(
                    "Warmup complete (%ds), incident detection active",
                    self._incident_warmup_s,
                )

            # Check for new incidents
            new_incs = self._overseer.check_for_incidents(now, now_ms, self.fibers, self.incidents)
            for inc in new_incs:
                self.incidents.append(inc)
                self._init_snapshot(inc)
                new_incidents.append(inc)

            # Check for resolved incidents
            resolved_incs = self._overseer.check_for_resolutions(self.incidents, now)
            resolved_incidents.extend(resolved_incs)

        # Prune old resolved — keep ~1 month of history (~360 incidents/day)
        resolved_all = [i for i in self.incidents if i.status == "resolved"]
        if len(resolved_all) > 10_000:
            to_remove = set(id(i) for i in resolved_all[:-10_000])
            removed_ids = {i.id for i in self.incidents if id(i) in to_remove}
            self.incidents = [i for i in self.incidents if id(i) not in to_remove]
            for rid in removed_ids:
                self.incident_snapshots.pop(rid, None)

        return detections, new_incidents, resolved_incidents

    def _generate_detections(self) -> list[Detection]:
        """Group nearby vehicles and produce DAS-like detections."""
        now_ms = int(time.time() * 1000)
        detections = []
        processed: set[str] = set()

        sorted_v = sorted(self.vehicles, key=lambda v: (v.fiber_line, v.direction, v.channel))
        for v in sorted_v:
            if v.id in processed:
                continue
            nearby = [
                o
                for o in sorted_v
                if o.id not in processed
                and o.fiber_line == v.fiber_line
                and o.direction == v.direction
                and abs(o.channel - v.channel) < 8
            ]
            if not nearby:
                continue
            avg_ch = sum(o.channel for o in nearby) / len(nearby)
            avg_sp = sum(o.speed for o in nearby) / len(nearby)
            for o in nearby:
                processed.add(o.id)
            count = len(nearby)
            n_trucks = sum(1 for o in nearby if o.vehicle_type == "truck")
            detections.append(
                Detection(
                    fiber_line=v.fiber_line,
                    channel=round(avg_ch),
                    speed=max(0.0, avg_sp),
                    count=count,
                    n_cars=count - n_trucks,
                    n_trucks=n_trucks,
                    direction=v.direction,
                    timestamp=now_ms,
                )
            )
        return detections

    def _update_detection_ring(self, detections: list[Detection], now_ms: float):
        """Maintain a rolling buffer of recent detections per fiber (last SNAPSHOT_WINDOW_S)."""
        cutoff_ms = now_ms - SNAPSHOT_WINDOW_S * 1000

        for d in detections:
            ring = self._detection_ring.get(d.fiber_line)
            if ring is None:
                continue
            ring.append(
                {
                    "fiberId": d.fiber_line,
                    "direction": d.direction,
                    "channel": d.channel,
                    "speed": round(d.speed, 1),
                    "count": d.count,
                    "nCars": d.n_cars,
                    "nTrucks": d.n_trucks,
                    "timestamp": d.timestamp,
                }
            )

        # Evict old entries from all rings
        for fid in self._detection_ring:
            ring = self._detection_ring[fid]
            if ring and ring[0]["timestamp"] < cutoff_ms:
                self._detection_ring[fid] = [det for det in ring if det["timestamp"] >= cutoff_ms]

    def _init_snapshot(self, inc: Incident):
        """Initialize a snapshot for a new incident, seeding with pre-incident data from the ring."""
        start_ms = inc.detected_at_ms - SNAPSHOT_WINDOW_S * 1000
        end_ms = inc.detected_at_ms + SNAPSHOT_WINDOW_S * 1000

        # Pre-fill all 120 one-second buckets so the time axis is always complete
        buckets: dict[int, dict] = {}
        for s in range(SNAPSHOT_WINDOW_S * 2):
            buckets[s] = {"speed_sum": 0.0, "speed_count": 0, "vehicle_count": 0}

        # Seed from rolling buffer: detections near this incident's channel and direction
        ring = self._detection_ring.get(inc.fiber_line, [])
        for det in ring:
            if det["direction"] != inc.direction:
                continue
            if abs(det["channel"] - inc.channel) > SNAPSHOT_CHANNEL_RADIUS:
                continue
            if det["timestamp"] < start_ms:
                continue
            s = int((det["timestamp"] - start_ms) / 1000)
            if 0 <= s < SNAPSHOT_WINDOW_S * 2:
                buckets[s]["speed_sum"] += det["speed"]
                buckets[s]["speed_count"] += 1
                buckets[s]["vehicle_count"] += det["count"]

        self.incident_snapshots[inc.id] = {
            "buckets": buckets,
            "complete": False,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "fiber_line": inc.fiber_line,
            "direction": inc.direction,
            "channel": inc.channel,
        }

    def _record_incident_detections(self, detections: list[Detection], now_ms: float):
        """Aggregate detections into 1-second snapshot buckets."""
        # Always update the rolling buffer (needed for pre-incident seeding)
        self._update_detection_ring(detections, now_ms)

        if not detections:
            return

        # Only scan incomplete snapshots
        for snap in self.incident_snapshots.values():
            if snap["complete"]:
                continue

            if now_ms > snap["end_ms"]:
                snap["complete"] = True
                continue

            buckets = snap["buckets"]
            start_ms = snap["start_ms"]

            for d in detections:
                if d.fiber_line != snap["fiber_line"]:
                    continue
                if d.direction != snap["direction"]:
                    continue
                if abs(d.channel - snap["channel"]) > SNAPSHOT_CHANNEL_RADIUS:
                    continue
                if d.timestamp < start_ms or d.timestamp > snap["end_ms"]:
                    continue
                s = int((d.timestamp - start_ms) / 1000)
                if 0 <= s < SNAPSHOT_WINDOW_S * 2:
                    buckets[s]["speed_sum"] += d.speed
                    buckets[s]["speed_count"] += 1
                    buckets[s]["vehicle_count"] += d.count

    def accumulate_detections_for_history(self, detections: list[Detection], now_ms: float):
        """Accumulate detections into per-second buckets for section history."""
        bucket_ms = int(now_ms // 1000) * 1000

        # Second boundary crossed — flush previous accumulator
        if bucket_ms != self._sec_accum_bucket and self._sec_accum:
            self._flush_second_buffer()

        self._sec_accum_bucket = bucket_ms

        for d in detections:
            key = (d.fiber_line, d.direction, d.channel)
            if key not in self._sec_accum:
                self._sec_accum[key] = {
                    "speed_sum": 0.0,
                    "speed_max": 0.0,
                    "count": 0,
                    "vehicle_count": 0,
                }
            acc = self._sec_accum[key]
            acc["speed_sum"] += d.speed
            acc["speed_max"] = max(acc["speed_max"], d.speed)
            acc["count"] += 1
            acc["vehicle_count"] += d.count

    def _flush_second_buffer(self):
        """Flush accumulated per-second data to the global buffer and evict old entries."""
        global _simulation_per_second_buffer
        bucket_ms = self._sec_accum_bucket
        cutoff_ms = bucket_ms - 5 * 60 * 1000  # 5 min retention

        for key, acc in self._sec_accum.items():
            if acc["count"] == 0:
                continue
            entry = {
                "time": bucket_ms,
                "speed": round(acc["speed_sum"] / acc["count"], 1),
                "speedMax": round(acc["speed_max"], 1),
                "vehicle_count": acc["vehicle_count"],
            }
            if key not in _simulation_per_second_buffer:
                _simulation_per_second_buffer[key] = []
            buf = _simulation_per_second_buffer[key]
            buf.append(entry)

            # Evict old entries
            if buf and buf[0]["time"] < cutoff_ms:
                _simulation_per_second_buffer[key] = [e for e in buf if e["time"] >= cutoff_ms]

        self._sec_accum.clear()

    def rollup_minute_buffer(self, now: float):
        """Roll up per-second buffer into per-minute buffer every 60 seconds."""
        if now - self._last_minute_rollup < 60:
            return
        self._last_minute_rollup = now

        global _simulation_per_minute_buffer
        now_ms = int(now * 1000)
        minute_ms = int(now_ms // 60_000) * 60_000 - 60_000  # Previous completed minute
        cutoff_ms = now_ms - 60 * 60 * 1000  # 60 min retention

        for key, entries in _simulation_per_second_buffer.items():
            # Aggregate all per-second entries in the previous minute
            speed_sum = 0.0
            speed_max = 0.0
            speed_count = 0
            total_vehicle_count = 0
            for e in entries:
                e_minute = int(e["time"] // 60_000) * 60_000
                if e_minute == minute_ms:
                    speed_sum += e["speed"]
                    speed_max = max(speed_max, e["speedMax"])
                    speed_count += 1
                    total_vehicle_count += e["vehicle_count"]

            if speed_count == 0:
                continue

            entry = {
                "time": minute_ms,
                "speed": round(speed_sum / speed_count, 1),
                "speedMax": round(speed_max, 1),
                "vehicle_count": total_vehicle_count,
            }

            if key not in _simulation_per_minute_buffer:
                _simulation_per_minute_buffer[key] = []
            buf = _simulation_per_minute_buffer[key]
            buf.append(entry)

            # Evict old entries
            if buf and buf[0]["time"] < cutoff_ms:
                _simulation_per_minute_buffer[key] = [e for e in buf if e["time"] >= cutoff_ms]

    def generate_shm_readings(self) -> list[SHMReading]:
        """Generate SHM frequency readings for all infrastructure."""
        now_ms = int(time.time() * 1000)
        t = time.time()
        readings = []
        vehicle_count = len(self.vehicles)

        for infra in self.infrastructure:
            iid = infra["id"]
            base_freq = self.shm_base_freq.get(iid, 10.0)
            phase = self.shm_phase.get(iid, 0)
            load_factor = 1 - (vehicle_count / 2000) * 0.05
            periodic = math.sin(t * 0.1 + phase) * 0.3
            fast = math.sin(t * 2.5 + phase * 2) * 0.1
            noise = (random.random() - 0.5) * 0.2
            freq = base_freq * load_factor + periodic + fast + noise

            base_amp = 0.3
            traffic_amp = (vehicle_count / 500) * 0.2
            vib_amp = abs(math.sin(t * 5 + phase)) * 0.15
            noise_amp = random.random() * 0.1
            amp = min(1.0, base_amp + traffic_amp + vib_amp + noise_amp)

            readings.append(
                SHMReading(
                    infrastructure_id=iid,
                    frequency=round(freq, 2),
                    amplitude=round(amp, 2),
                    timestamp=now_ms,
                )
            )
        return readings


# ============================================================================
# ASYNC BROADCAST LOOP
# ============================================================================


async def run_simulation_loop(fibers: list[FiberConfig], infrastructure: list[dict]):
    """Main async loop — runs the simulation and broadcasts via Channels."""
    channel_layer = get_channel_layer()
    engine = SimulationEngine(fibers, infrastructure)

    # Load fiber→org mapping (refreshed every 5 minutes)
    fiber_org_map = await load_fiber_org_map()
    infra_fiber = {i["id"]: i.get("fiber_id", "") for i in infrastructure}
    last_map_refresh = time.time()

    logger.info(
        "Simulation started: %d fibers, %d infrastructure, hour=%.1f, %d org mappings",
        len(fibers),
        len(infrastructure),
        engine.simulated_hour,
        len(fiber_org_map),
    )

    from apps.monitoring.incident_service import transform_simulation_incident

    # No initial incidents — they spawn after the warmup period so
    # snapshot data has time to accumulate from the vehicle simulation
    _update_simulation_incidents_cache(engine.incidents)

    # Clear stale history buffers from any previous simulation run
    global _simulation_per_second_buffer, _simulation_per_minute_buffer
    _simulation_per_second_buffer = {}
    _simulation_per_minute_buffer = {}

    tick_interval = 0.05  # 50ms ticks (20 Hz physics)
    shm_counter = 0
    incident_counter = 0
    snapshot_counter = 0
    last_detection_broadcast = time.time()
    detection_broadcast_interval = 0.1  # 100ms (10 Hz)
    pending_detections: list[Detection] = []  # Accumulate detections between broadcasts
    pending_new_incidents: list[Incident] = []  # Accumulate new incidents between broadcasts
    pending_resolved_incidents: list[Incident] = []

    while True:
        tick_start = time.time()

        # Refresh fiber→org mapping periodically
        if tick_start - last_map_refresh > MAP_REFRESH_INTERVAL:
            fiber_org_map = await load_fiber_org_map()
            last_map_refresh = tick_start

        detections, new_incidents, resolved_incidents = engine.tick(tick_interval * 1000)
        engine.accumulate_detections_for_history(detections, tick_start * 1000)
        engine.rollup_minute_buffer(tick_start)
        shm_counter += 1
        incident_counter += 1
        snapshot_counter += 1
        # Accumulate detections
        pending_detections.extend(detections)
        # Accumulate incidents (broadcast happens every 100 ticks)
        pending_new_incidents.extend(new_incidents)
        pending_resolved_incidents.extend(resolved_incidents)

        # Broadcast detections at 10 Hz (time-based, not tick-based)
        time_since_last_broadcast = tick_start - last_detection_broadcast
        if time_since_last_broadcast >= detection_broadcast_interval and pending_detections:
            last_detection_broadcast = tick_start
            detection_dicts = [
                {
                    "fiberId": d.fiber_line,
                    "direction": d.direction,
                    "channel": d.channel,
                    "speed": round(d.speed, 1),
                    "count": d.count,
                    "nCars": d.n_cars,
                    "nTrucks": d.n_trucks,
                    "timestamp": d.timestamp,
                }
                for d in pending_detections
            ]
            pending_detections.clear()
            await pubsub_broadcast_detections(
                detection_dicts,
                fiber_org_map,
                flow="sim",
            )
            # Check alerts for detections (per-org)
            for org_id, org_dets in group_by_org(detection_dicts, fiber_org_map).items():
                await check_alerts_for_detections(org_dets, org_id)

        # Broadcast SHM every 20 ticks (1 Hz) — per-org via infrastructure ownership
        if shm_counter >= 20:
            shm_counter = 0
            readings = engine.generate_shm_readings()
            if readings:
                shm_dicts = [
                    {
                        "infrastructureId": r.infrastructure_id,
                        "fiberId": infra_fiber.get(r.infrastructure_id, ""),
                        "frequency": r.frequency,
                        "amplitude": r.amplitude,
                        "timestamp": r.timestamp,
                    }
                    for r in readings
                ]
                await pubsub_broadcast_shm(shm_dicts, fiber_org_map, flow="sim")

        # Sync snapshot cache every 20 ticks (1s) so frontend polling gets fresh data
        if snapshot_counter >= 20:
            snapshot_counter = 0
            _update_simulation_snapshots(engine.incident_snapshots)

        # Broadcast incidents every 100 ticks (5 seconds) — per-org
        if incident_counter >= 100:
            incident_counter = 0
            # Update caches for REST API fallback
            _update_simulation_incidents_cache(engine.incidents)
            _update_simulation_stats(engine)
            for inc in pending_new_incidents + pending_resolved_incidents:
                inc_data = transform_simulation_incident(inc)
                await broadcast_to_orgs(
                    channel_layer,
                    "incidents",
                    inc_data,
                    fiber_org_map,
                    fiber_ids={inc_data["fiberId"]},
                    flow="sim",
                )
                # Check alerts for incident
                await check_alerts_for_incident(inc_data, fiber_org_map)
            pending_new_incidents.clear()
            pending_resolved_incidents.clear()

        # Log stats periodically
        if engine.tick_count % 400 == 0:
            active = sum(1 for i in engine.incidents if i.status == "active")
            events = len(engine._road_events.events)
            logger.info(
                "[%.1fh] Vehicles: %d | Active incidents: %d | Road events: %d",
                engine.simulated_hour,
                len(engine.vehicles),
                active,
                events,
            )

        # Sleep for remaining tick time (minimum 1ms to allow event loop I/O)
        elapsed = time.time() - tick_start
        sleep_time = max(0.001, tick_interval - elapsed)
        await asyncio.sleep(sleep_time)
