"""
Simulation package — re-exports all public names so external imports stay unchanged.

    from apps.realtime.simulation import X

continues to work as before.
"""

from .cache import (
    get_simulation_incidents,
    get_simulation_section_history,
    get_simulation_snapshot,
    get_simulation_stats,
)
from .loop import run_simulation_loop
from .types import Detection, FiberConfig, Incident, RoadEvent, SHMReading, Vehicle

__all__ = [
    "Detection",
    "FiberConfig",
    "Incident",
    "RoadEvent",
    "SHMReading",
    "Vehicle",
    "get_simulation_incidents",
    "get_simulation_section_history",
    "get_simulation_snapshot",
    "get_simulation_stats",
    "run_simulation_loop",
]
