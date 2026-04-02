"""
Incident detection (IncidentOverseer) and road event management (RoadEventManager).
"""

import logging
import random
import time
import uuid
from dataclasses import dataclass

from .constants import DEFAULT_TAGS  # noqa: F401
from .types import FiberConfig, Incident, RoadEvent, Vehicle
from .vehicles import _get_density_multiplier, _get_max_channel

logger = logging.getLogger("sequoia.realtime.simulation")


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
    EMA_ALPHA = 0.3  # EMA smoothing factor (higher = more responsive to stopped vehicles)
    MIN_SPEED_DECAY = 0.05  # recent_min_speed decays toward ema_speed per tick
    # Thresholds for incident detection
    SPEED_DROP_PCT_THRESHOLD = 40  # 40% drop from free-flow triggers incident
    MIN_ANOMALY_DURATION_S = 8  # Anomaly must persist 8s before declaring incident
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

    def ingest_detections(self, detections: list, delta_s: float):
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

            # Determine incident type and tags
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
                tags = ["critical"]
            elif drop_pct > 60:
                tags = ["high"]
            elif drop_pct > 50:
                tags = ["medium"]
            else:
                tags = ["low"]

            fiber = next((f for f in fibers if f.id == fiber_id), None)
            inc_ch = min(ch, _get_max_channel(fiber, direction) - 1) if fiber else ch

            inc_id = f"inc-{int(now_ms)}-{uuid.uuid4().hex[:4]}"
            inc = Incident(
                id=inc_id,
                type=inc_type,
                tags=tags,
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
                tags,
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
                # Escalate tags if anomaly deepens
                drop_pct = m.speed_drop_pct
                if drop_pct > 80 and "critical" not in inc.tags:
                    inc.tags = ["critical"]
                elif drop_pct > 60 and inc.tags[0] in ("low", "medium"):
                    inc.tags = ["high"]

        return resolved


class RoadEventManager:
    """Spawns and manages road events that create physical obstructions.

    Events are the *causes* — stopped vehicles, slow vehicles, lane closures.
    They affect specific vehicles, which then propagate slowdowns upstream
    through the car-following model. The Overseer detects the resulting
    speed anomalies and declares incidents.
    """

    # Probabilities per sim-hour (scaled by traffic density)
    EVENT_RATES: dict[str, float] = {
        "stopped_vehicle": 0.8,  # Per sim-hour
        "slow_vehicle": 1.0,
        "lane_closure": 0.3,
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
                # Only release if this vehicle is near the event
                if (
                    v.fiber_line == e.fiber_id
                    and v.forced_speed is not None
                    and abs(v.channel - e.channel) < 60
                ):
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
        for event_type, base_rate in self.EVENT_RATES.items():
            # Pick a fiber first so we use its per-fiber traffic curve
            fiber = random.choice(fibers)
            density = _get_density_multiplier(sim_hour, fiber)
            # Real-time probability per tick
            rate = base_rate * density * hour_advance_rate
            prob_per_tick = rate * delta_s / 3600
            if random.random() > prob_per_tick:
                continue
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
            dur_real = max(dur_real, 90)  # Minimum 90s real-time for EMA to respond

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
