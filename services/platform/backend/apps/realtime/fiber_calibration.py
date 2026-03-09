"""
Per-fiber calibration constants for the Nice DAS deployment.

Shared by both the simulation engine and the Kafka/live data path.
Speed limits, typical free-flow ranges, channel limits, and traffic density
match the real road characteristics.

Channel limits: beyond these channels the fiber runs off-road or has dead coupling.
  - promenade dir A (0): valid up to channel 4177
  - promenade dir B (1): valid up to channel 4178
  - mathis dir A (0) & B (1): valid up to channel 687
  - carros: full fiber is on-road (no limit)
"""

FIBER_CONFIGS: dict[str, dict] = {
    "carros": {
        "lanes": 6,
        "speed_limit": 110,
        "traffic_density": "high",
        "typical_speed_range": (80, 110),
        "max_channel_dir0": None,
        "max_channel_dir1": None,
    },
    "promenade": {
        "lanes": 4,
        "speed_limit": 50,
        "traffic_density": "medium",
        "typical_speed_range": (30, 50),
        "max_channel_dir0": 4177,
        "max_channel_dir1": 4178,
    },
    "mathis": {
        "lanes": 4,
        "speed_limit": 50,
        "traffic_density": "low",
        "typical_speed_range": (35, 50),
        "max_channel_dir0": 687,
        "max_channel_dir1": 687,
    },
}
