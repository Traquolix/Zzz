"""
Dataclass type definitions for the simulation engine.
"""

from dataclasses import dataclass


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
    glrt_max: float = 0.0
    strain_peak: float = 0.0
    strain_rms: float = 0.0


@dataclass
class Incident:
    id: str
    type: str
    tags: list[str]
    fiber_line: str
    direction: int
    channel: int
    detected_at: str
    detected_at_ms: float  # Wall-clock ms at creation (avoids UTC/local parsing bugs)
    status: str = "active"
    duration: float | None = None


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
