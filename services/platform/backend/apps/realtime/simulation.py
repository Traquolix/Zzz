"""
Traffic simulation engine — Python port of the Node.js simulation server.

Generates realistic traffic data (vehicles, detections, incidents, SHM readings)
and broadcasts them through Django Channels groups.

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
from apps.realtime.broadcast import (
    broadcast_per_org,
    broadcast_shm,
    broadcast_to_orgs,
    group_by_org,
    load_fiber_org_map,
    load_infra_org_map,
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
            flow = b["vehicle_count"]
            speed_ms = avg_speed * (1000 / 3600)
            occupancy = (
                min(100, round((flow * 3600 * AVG_VEHICLE_LENGTH_M) / (speed_ms * 1000)))
                if speed_ms > 0
                else None
            )
            points.append({"time": t, "speed": avg_speed, "flow": flow, "occupancy": occupancy})
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
    channel: int
    detected_at: str
    detected_at_ms: float  # Wall-clock ms at creation (avoids UTC/local parsing bugs)
    status: str = "active"
    duration: Optional[float] = None


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
    "car": {"min_speed": 60, "max_speed": 130, "accel": 3.5, "decel": 6, "length": 1.5},
    "truck": {"min_speed": 40, "max_speed": 90, "accel": 1.5, "decel": 4, "length": 4},
    "motorcycle": {"min_speed": 50, "max_speed": 150, "accel": 5, "decel": 7, "length": 0.8},
    "bus": {"min_speed": 40, "max_speed": 100, "accel": 2, "decel": 5, "length": 3.5},
}

METERS_PER_CHANNEL = 5
SAFE_FOLLOWING_SECONDS = 2
MIN_GAP_CHANNELS = 3
VEHICLE_TYPES = ["car", "car", "car", "car", "truck", "motorcycle", "bus"]

DAILY_TRAFFIC = [
    0.2,
    0.1,
    0.1,
    0.1,
    0.15,
    0.3,
    0.6,
    0.9,
    1.0,
    0.85,
    0.7,
    0.75,
    0.8,
    0.75,
    0.7,
    0.75,
    0.85,
    1.0,
    0.95,
    0.8,
    0.6,
    0.45,
    0.35,
    0.25,
]

BASE_SPAWN_RATES = {"low": 4, "medium": 10, "high": 20}


class _IncidentConfig(TypedDict):
    type: str
    prob: float
    dur: tuple[int, int]
    weights: list[float]


class _SpawnPoint(TypedDict):
    fiber: str
    ch: int
    dir: int
    rate: float
    last: float


INCIDENT_CONFIGS: list[_IncidentConfig] = [
    {
        "type": "slowdown",
        "prob": 0.3,
        "dur": (300_000, 1_800_000),
        "weights": [0.4, 0.4, 0.15, 0.05],
    },
    {
        "type": "congestion",
        "prob": 0.5,
        "dur": (900_000, 3_600_000),
        "weights": [0.3, 0.5, 0.15, 0.05],
    },
    {
        "type": "accident",
        "prob": 0.05,
        "dur": (1_800_000, 7_200_000),
        "weights": [0.1, 0.3, 0.4, 0.2],
    },
    {
        "type": "anomaly",
        "prob": 0.15,
        "dur": (600_000, 3_600_000),
        "weights": [0.5, 0.3, 0.15, 0.05],
    },
]
SEVERITIES = ["low", "medium", "high", "critical"]

SNAPSHOT_CHANNEL_RADIUS = 100  # ±100 channels (~1km) around incident center
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


def _create_vehicle(fiber: FiberConfig, channel: float, direction: int, lane: int) -> Vehicle:
    vtype = random.choice(VEHICLE_TYPES)
    profile = VEHICLE_PROFILES[vtype]
    speed_var = 0.8 + random.random() * 0.4
    target = min(profile["max_speed"], fiber.speed_limit * speed_var)
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
    incidents: list[Incident],
    delta_s: float,
) -> Optional[Vehicle]:
    profile = VEHICLE_PROFILES[v.vehicle_type]

    if v.channel < 0 or v.channel >= fiber.channel_count:
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

    effective_target = v.target_speed

    # Incident slowdown
    for inc in incidents:
        if inc.fiber_line == v.fiber_line and inc.status == "active":
            dist = abs(inc.channel - v.channel)
            if dist < 30:
                effective_target *= 0.3
            elif dist < 50:
                effective_target *= 0.6

    # Car-following
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
# SIMULATION ENGINE
# ============================================================================


class SimulationEngine:
    """Self-contained traffic simulation that broadcasts via Channels."""

    def __init__(self, fibers: list[FiberConfig], infrastructure: list[dict]):
        self.fibers = fibers
        self.infrastructure = infrastructure
        self.vehicles: list[Vehicle] = []
        self.incidents: list[Incident] = []
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
        self.shm_base_freq = {}
        self.shm_phase = {}
        for infra in infrastructure:
            iid = infra["id"]
            self.shm_base_freq[iid] = (
                INFRA_BASE_FREQ.get(infra["type"], 10) + (random.random() - 0.5) * 2
            )
            self.shm_phase[iid] = random.random() * math.pi * 2

        # Spawn points
        self.spawn_points: list[_SpawnPoint] = []
        for fiber in fibers:
            rate = BASE_SPAWN_RATES.get(fiber.traffic_density, 10)
            self.spawn_points.append(
                {"fiber": fiber.id, "ch": 5, "dir": 0, "rate": rate, "last": 0}
            )
            self.spawn_points.append(
                {
                    "fiber": fiber.id,
                    "ch": fiber.channel_count - 5,
                    "dir": 1,
                    "rate": rate,
                    "last": 0,
                }
            )
            if fiber.channel_count > 200:
                mid = fiber.channel_count // 2
                self.spawn_points.append(
                    {"fiber": fiber.id, "ch": mid, "dir": 0, "rate": rate * 0.3, "last": 0}
                )
                self.spawn_points.append(
                    {"fiber": fiber.id, "ch": mid, "dir": 1, "rate": rate * 0.3, "last": 0}
                )

        # Track when simulation started — incidents only spawn after warmup period
        # so snapshot data has time to accumulate
        self._started_at = time.time()
        self._incident_warmup_s = 180  # 3 minutes

    def _density_multiplier(self) -> float:
        h = int(self.simulated_hour) % 24
        h_next = (h + 1) % 24
        frac = self.simulated_hour - int(self.simulated_hour)
        return DAILY_TRAFFIC[h] + (DAILY_TRAFFIC[h_next] - DAILY_TRAFFIC[h]) * frac

    def tick(self, delta_ms: float) -> tuple[list[Detection], list[Incident], list[Incident]]:
        """Run one simulation tick. Returns (detections, new_incidents, resolved_incidents)."""
        delta_s = delta_ms / 1000
        self.tick_count += 1
        now = time.time()
        now_ms = now * 1000

        # Advance time
        hours = (delta_ms / 1000 / 3600) * self.hour_advance_rate
        self.simulated_hour = (self.simulated_hour + hours) % 24

        active_incidents = [i for i in self.incidents if i.status == "active"]

        # Update vehicles
        surviving = []
        for v in self.vehicles:
            fiber = next((f for f in self.fibers if f.id == v.fiber_line), None)
            if fiber:
                result = _update_vehicle(v, self.vehicles, fiber, active_incidents, delta_s)
                if result:
                    surviving.append(result)
        self.vehicles = surviving

        # Spawn new vehicles
        density_mult = self._density_multiplier()
        for sp in self.spawn_points:
            fiber = next((f for f in self.fibers if f.id == sp["fiber"]), None)
            if not fiber:
                continue
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

        # Resolve expired incidents + maybe create new ones
        new_incidents: list[Incident] = []
        resolved_incidents: list[Incident] = []

        for inc in self.incidents:
            if inc.status == "active" and inc.duration:
                if now_ms - inc.detected_at_ms > inc.duration:
                    inc.status = "resolved"
                    resolved_incidents.append(inc)

        # Only generate new incidents after warmup (so snapshot data can accumulate)
        if now - self._started_at < self._incident_warmup_s:
            return detections, new_incidents, resolved_incidents

        if not hasattr(self, "_warmup_logged"):
            self._warmup_logged = True
            logger.info("Warmup complete (%ds), incidents will now spawn", self._incident_warmup_s)

        # Maybe generate new incidents (15x multiplier for dev testing)
        hours_frac = delta_ms / 3_600_000 * 15
        for cfg in INCIDENT_CONFIGS:
            if random.random() > cfg["prob"] * hours_frac:
                continue
            fiber = random.choice(self.fibers)
            # Place incident near an existing vehicle so snapshots have data
            fiber_vehicles = [v for v in self.vehicles if v.fiber_line == fiber.id]
            if fiber_vehicles:
                target = random.choice(fiber_vehicles)
                ch = max(10, min(fiber.channel_count - 10, round(target.channel)))
            else:
                continue  # No vehicles on this fiber — skip
            severity = _weighted_choice(SEVERITIES, cfg["weights"])
            dur = (cfg["dur"][0] + random.random() * (cfg["dur"][1] - cfg["dur"][0])) / 15
            dur = max(dur, 120_000)  # Minimum 2 minutes real-time so incidents are visible
            inc = Incident(
                id=f"inc-{int(now_ms)}-{uuid.uuid4().hex[:4]}",
                type=cfg["type"],
                severity=severity,
                fiber_line=fiber.id,
                channel=ch,
                detected_at=time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(now)),
                detected_at_ms=now_ms,
                status="active",
                duration=dur,
            )
            self.incidents.append(inc)
            self._init_snapshot(inc)  # Seed with pre-incident data from rolling buffer
            new_incidents.append(inc)

        # Prune old resolved — keep ~1 month of history (~360 incidents/day)
        # Each incident + snapshot ≈ 5.5 KB, so 10 000 ≈ 55 MB
        resolved_all = [i for i in self.incidents if i.status == "resolved"]
        if len(resolved_all) > 10_000:
            to_remove = set(id(i) for i in resolved_all[:-10_000])
            removed_ids = {i.id for i in self.incidents if id(i) in to_remove}
            self.incidents = [i for i in self.incidents if id(i) not in to_remove]
            # Clean up snapshots for pruned incidents
            for rid in removed_ids:
                self.incident_snapshots.pop(rid, None)

        return detections, new_incidents, resolved_incidents

    def _generate_detections(self) -> list[Detection]:
        """Group nearby vehicles and produce DAS-like detections."""
        now_ms = int(time.time() * 1000)
        detections = []
        processed = set()

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
            # Noise disabled — keep detections clean and smooth for now
            # ch_noise = (random.random() - 0.5) * 4
            # sp_noise = (random.random() - 0.5) * 10
            ch_noise = 0
            sp_noise = 0
            count = len(nearby)
            detections.append(
                Detection(
                    fiber_line=v.fiber_line,
                    channel=round(avg_ch + ch_noise),
                    speed=max(0.0, avg_sp + sp_noise),
                    count=count,
                    n_cars=count,
                    n_trucks=0,
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
                    "fiberLine": f"{d.fiber_line}:{d.direction}",
                    "channel": d.channel,
                    "speed": round(d.speed, 1),
                    "count": d.count,
                    "nCars": d.n_cars,
                    "nTrucks": d.n_trucks,
                    "direction": d.direction,
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
        # Key: seconds offset from start (0..119) → {speed_sum, speed_count, vehicle_count}
        buckets: dict[int, dict] = {}
        for s in range(SNAPSHOT_WINDOW_S * 2):
            buckets[s] = {"speed_sum": 0.0, "speed_count": 0, "vehicle_count": 0}

        # Seed from rolling buffer: detections near this incident's channel
        ring = self._detection_ring.get(inc.fiber_line, [])
        for det in ring:
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
            "channel": inc.channel,
        }

    def _record_incident_detections(self, detections: list[Detection], now_ms: float):
        """Aggregate detections into 1-second snapshot buckets.

        Each snapshot has a fixed window: detected_at ± SNAPSHOT_WINDOW_S.
        Pre-incident data is seeded from the rolling detection buffer.
        Once now_ms exceeds end_ms, the snapshot is marked complete.
        """
        # Always update the rolling buffer (needed for pre-incident seeding)
        self._update_detection_ring(detections, now_ms)

        if not detections:
            return

        # Only scan incomplete snapshots — avoids iterating all 10k+ resolved incidents
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
                if abs(d.channel - snap["channel"]) > SNAPSHOT_CHANNEL_RADIUS:
                    continue
                if d.timestamp < start_ms or d.timestamp > snap["end_ms"]:
                    continue
                s = int((d.timestamp - start_ms) / 1000)
                if 0 <= s < SNAPSHOT_WINDOW_S * 2:
                    buckets[s]["speed_sum"] += d.speed
                    buckets[s]["speed_count"] += 1
                    buckets[s]["vehicle_count"] += d.count

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
    infra_org_map = load_infra_org_map(infrastructure)
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

    tick_interval = 0.05  # 50ms ticks (20 Hz physics)
    shm_counter = 0
    incident_counter = 0
    snapshot_counter = 0
    count_counter = 0
    last_detection_broadcast = time.time()
    detection_broadcast_interval = 0.1  # 100ms (10 Hz)
    pending_detections: list[Detection] = []  # Accumulate detections between broadcasts
    pending_new_incidents: list[Incident] = []  # Accumulate new incidents between broadcasts
    pending_resolved_incidents: list[
        Incident
    ] = []  # Accumulate resolved incidents between broadcasts

    while True:
        tick_start = time.time()

        # Refresh fiber→org mapping periodically
        if tick_start - last_map_refresh > MAP_REFRESH_INTERVAL:
            fiber_org_map = await load_fiber_org_map()
            infra_org_map = load_infra_org_map(infrastructure)
            last_map_refresh = tick_start

        detections, new_incidents, resolved_incidents = engine.tick(tick_interval * 1000)
        shm_counter += 1
        incident_counter += 1
        snapshot_counter += 1
        count_counter += 1

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
                    "fiberLine": f"{d.fiber_line}:{d.direction}",
                    "channel": d.channel,
                    "speed": round(d.speed, 1),
                    "count": d.count,
                    "nCars": d.n_cars,
                    "nTrucks": d.n_trucks,
                    "direction": d.direction,
                    "timestamp": d.timestamp,
                }
                for d in pending_detections
            ]
            pending_detections.clear()
            await broadcast_per_org(
                channel_layer,
                "detections",
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
                        "frequency": r.frequency,
                        "amplitude": r.amplitude,
                        "timestamp": r.timestamp,
                    }
                    for r in readings
                ]
                await broadcast_shm(channel_layer, shm_dicts, infra_org_map, flow="sim")

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
                directional_fid = inc_data["fiberLine"]
                await broadcast_to_orgs(
                    channel_layer,
                    "incidents",
                    inc_data,
                    fiber_org_map,
                    fiber_ids={directional_fid},
                    flow="sim",
                )
                # Check alerts for incident
                await check_alerts_for_incident(inc_data, fiber_org_map)
            pending_new_incidents.clear()
            pending_resolved_incidents.clear()

        # Broadcast vehicle counts every 100 ticks (5 seconds) — per-org
        if count_counter >= 100:
            count_counter = 0
            counts = _compute_section_counts(engine)
            if counts:
                await broadcast_per_org(
                    channel_layer,
                    "counts",
                    counts,
                    fiber_org_map,
                    flow="sim",
                )

        # Log stats periodically
        if engine.tick_count % 400 == 0:
            active = sum(1 for i in engine.incidents if i.status == "active")
            logger.info(
                "[%.1fh] Vehicles: %d | Active incidents: %d",
                engine.simulated_hour,
                len(engine.vehicles),
                active,
            )

        # Sleep for remaining tick time (minimum 1ms to allow event loop I/O)
        elapsed = time.time() - tick_start
        sleep_time = max(0.001, tick_interval - elapsed)
        await asyncio.sleep(sleep_time)


def _compute_section_counts(engine: SimulationEngine) -> list[dict]:
    """
    Compute section-level vehicle counts from simulation state.

    Divides each fiber into sections and counts vehicles within each direction.
    Produces the same shape as transform_count_message output (VehicleCount).
    """
    now_ms = int(time.time() * 1000)
    counts = []
    section_size = 300  # channels per section (~1.5 km at 5m/channel)

    for fiber in engine.fibers:
        for direction in (0, 1):
            for start_ch in range(0, fiber.channel_count, section_size):
                end_ch = min(start_ch + section_size - 1, fiber.channel_count - 1)

                vehicle_count = sum(
                    1
                    for v in engine.vehicles
                    if v.fiber_line == fiber.id
                    and v.direction == direction
                    and start_ch <= v.channel <= end_ch
                )

                if vehicle_count > 0:
                    counts.append(
                        {
                            "fiberLine": f"{fiber.id}:{direction}",
                            "channelStart": start_ch,
                            "channelEnd": end_ch,
                            "vehicleCount": float(vehicle_count),
                            "timestamp": now_ms,
                        }
                    )

    return counts
