"""
Backward-compatibility re-export — incident_service moved to ``apps.shared``.
"""

from apps.shared.incident_service import (
    query_active,
    query_active_raw,
    query_by_date,
    query_by_id,
    query_daily_counts,
    query_recent,
    transform_row,
    transform_simulation_incident,
)

__all__ = [
    "query_active",
    "query_active_raw",
    "query_by_date",
    "query_by_id",
    "query_daily_counts",
    "query_recent",
    "transform_row",
    "transform_simulation_incident",
]
