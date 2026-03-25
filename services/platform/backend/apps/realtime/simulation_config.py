"""
Simulation calibration data per fiber deployment.

Used exclusively by the simulation engine to generate physically realistic
traffic. Not read by the live data path, REST API, or detection pipeline.

These values describe the road each fiber monitors (not the fiber itself):
lanes, speed limits, traffic density, and per-direction channel boundaries.
"""

# Keyed by fiber_id (must match FiberCable.id / JSON file stem).
FIBER_CALIBRATION: dict[str, dict] = {
    "carros": {
        "lanes": 6,
        "speed_limit": 110,
        "traffic_density": "high",
        "typical_speed_min": 80.0,
        "typical_speed_max": 110.0,
        "max_channel_dir0": None,
        "max_channel_dir1": None,
    },
    "promenade": {
        "lanes": 4,
        "speed_limit": 50,
        "traffic_density": "medium",
        "typical_speed_min": 30.0,
        "typical_speed_max": 50.0,
        "max_channel_dir0": 4177,
        "max_channel_dir1": 4178,
    },
    "mathis": {
        "lanes": 4,
        "speed_limit": 50,
        "traffic_density": "low",
        "typical_speed_min": 35.0,
        "typical_speed_max": 50.0,
        "max_channel_dir0": 687,
        "max_channel_dir1": 687,
    },
}
