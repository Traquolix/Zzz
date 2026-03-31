"""
Backward-compatibility re-export — simulation cache moved to ``apps.shared.simulation_cache``.
"""

from apps.shared.simulation_cache import (  # noqa: F401
    _MIN_BUFFER_MAXLEN,
    _SEC_BUFFER_MAXLEN,
    _buckets_to_points,
    _simulation_incidents_cache,
    _simulation_per_minute_buffer,
    _simulation_per_second_buffer,
    _simulation_snapshots,
    _simulation_stats,
    _update_simulation_incidents_cache,
    _update_simulation_snapshots,
    _update_simulation_stats,
    get_simulation_incidents,
    get_simulation_section_history,
    get_simulation_snapshot,
    get_simulation_stats,
    transform_simulation_incident,
)

__all__ = [
    "_update_simulation_incidents_cache",
    "_update_simulation_snapshots",
    "_update_simulation_stats",
    "get_simulation_incidents",
    "get_simulation_section_history",
    "get_simulation_snapshot",
    "get_simulation_stats",
    "transform_simulation_incident",
]
