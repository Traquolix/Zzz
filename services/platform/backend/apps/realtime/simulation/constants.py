"""
Simulation constants — vehicle profiles, traffic curves, detection parameters.
"""

from typing import TypedDict

from apps.shared.constants import SNAPSHOT_CHANNEL_RADIUS, SNAPSHOT_WINDOW_S  # noqa: F401

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


DEFAULT_TAGS = ["low", "medium", "high", "critical"]

AVG_VEHICLE_LENGTH_M = 6  # For occupancy estimation

INFRA_BASE_FREQ = {"bridge": 5.0, "tunnel": 15.0}

_DETECTION_RING_MAXLEN = 20_000  # ~60s × 20Hz × 15 detections/tick + headroom
