"""
SimulationEngine — self-contained traffic simulation with emergent incidents.
"""

import logging
import math
import random
import time
from collections import deque

from .cache import _MIN_BUFFER_MAXLEN, _SEC_BUFFER_MAXLEN
from .constants import (
    _DETECTION_RING_MAXLEN,
    BASE_SPAWN_RATES,
    INFRA_BASE_FREQ,
    SNAPSHOT_CHANNEL_RADIUS,
    SNAPSHOT_WINDOW_S,
    _SpawnPoint,
)
from .incidents import IncidentOverseer, RoadEventManager
from .types import Detection, FiberConfig, Incident, SHMReading
from .vehicles import _create_vehicle, _get_density_multiplier, _get_max_channel, _update_vehicle

logger = logging.getLogger("sequoia.realtime.simulation")


class SimulationEngine:
    """Self-contained traffic simulation with emergent incidents."""

    def __init__(self, fibers: list[FiberConfig], infrastructure: list[dict]):
        self.fibers = fibers
        self.infrastructure = infrastructure
        self.vehicles: list = []
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

        # Rolling detection buffer per fiber — always keeps last SNAPSHOT_WINDOW_S seconds.
        # Used to seed snapshots with pre-incident data when a new incident spawns.
        # maxlen caps memory even if time-based eviction misses entries.
        self._detection_ring: dict[str, deque[dict]] = {
            f.id: deque(maxlen=_DETECTION_RING_MAXLEN) for f in fibers
        }

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
            to_remove = {id(i) for i in resolved_all[:-10_000]}
            removed_ids = {i.id for i in self.incidents if id(i) in to_remove}
            self.incidents = [i for i in self.incidents if id(i) not in to_remove]
            for rid in removed_ids:
                self.incident_snapshots.pop(rid, None)

        # Evict completed snapshots older than 12 hours — long enough for
        # demos/presentations, short enough to bound memory over multi-day runs.
        snapshot_ttl_ms = 12 * 60 * 60 * 1000
        stale_ids = [
            iid
            for iid, snap in self.incident_snapshots.items()
            if snap["complete"] and now_ms - snap["end_ms"] > snapshot_ttl_ms
        ]
        for iid in stale_ids:
            del self.incident_snapshots[iid]

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

        # Evict old entries from all rings (deque is ordered, pop from left)
        for ring in self._detection_ring.values():
            while ring and ring[0]["timestamp"] < cutoff_ms:
                ring.popleft()

    def _init_snapshot(self, inc: Incident):
        """Initialize a snapshot for a new incident, seeding with pre-incident data from the ring."""
        start_ms = inc.detected_at_ms - SNAPSHOT_WINDOW_S * 1000
        end_ms = inc.detected_at_ms + SNAPSHOT_WINDOW_S * 1000

        # Pre-fill all 120 one-second buckets so the time axis is always complete
        buckets: dict[int, dict] = {}
        for s in range(SNAPSHOT_WINDOW_S * 2):
            buckets[s] = {"speed_sum": 0.0, "speed_count": 0, "vehicle_count": 0}

        # Seed from rolling buffer: detections near this incident's channel and direction
        ring: deque[dict] | list[dict] = self._detection_ring.get(inc.fiber_line, [])
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
        import apps.realtime.simulation.cache as _cache

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
            if key not in _cache._simulation_per_second_buffer:
                _cache._simulation_per_second_buffer[key] = deque(maxlen=_SEC_BUFFER_MAXLEN)
            buf = _cache._simulation_per_second_buffer[key]
            buf.append(entry)

            # Evict old entries (deque is ordered, pop from left)
            while buf and buf[0]["time"] < cutoff_ms:
                buf.popleft()

        self._sec_accum.clear()

    def rollup_minute_buffer(self, now: float):
        """Roll up per-second buffer into per-minute buffer every 60 seconds."""
        if now - self._last_minute_rollup < 60:
            return
        self._last_minute_rollup = now

        import apps.realtime.simulation.cache as _cache

        now_ms = int(now * 1000)
        minute_ms = int(now_ms // 60_000) * 60_000 - 60_000  # Previous completed minute
        cutoff_ms = now_ms - 60 * 60 * 1000  # 60 min retention

        for key, entries in _cache._simulation_per_second_buffer.items():
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

            if key not in _cache._simulation_per_minute_buffer:
                _cache._simulation_per_minute_buffer[key] = deque(maxlen=_MIN_BUFFER_MAXLEN)
            buf = _cache._simulation_per_minute_buffer[key]
            buf.append(entry)

            # Evict old entries (deque is ordered, pop from left)
            while buf and buf[0]["time"] < cutoff_ms:
                buf.popleft()

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
