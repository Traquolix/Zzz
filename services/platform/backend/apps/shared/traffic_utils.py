"""
Shared traffic metric utilities — used by monitoring and simulation.
"""

import math

_AVG_VEHICLE_LENGTH_M = 6  # meters, for occupancy estimation


def compute_occupancy(speed_kmh: float, flow_vph: float) -> int:
    """Compute road occupancy percentage.

    Args:
        speed_kmh: Average speed in km/h.
        flow_vph: Flow in vehicles per hour.

    Uses: occupancy = (flow_vph * vehicle_length) / (speed_m_s * 1000)
    """
    if speed_kmh < 1.0:
        # Below 1 km/h treat as stationary — occupancy is 100% if vehicles present
        return 100 if flow_vph > 0 else 0
    speed_ms = speed_kmh * (1000 / 3600)
    return min(100, math.ceil((flow_vph * _AVG_VEHICLE_LENGTH_M) / (speed_ms * 1000)))
