"""
Centralized incident query and transform — single source of truth.

Every path that reads incidents (REST, WebSocket initial, Kafka bridge polling,
simulation cache) uses this service so the shape, field names, and query
parameters are defined exactly once.

Moved to ``apps.shared`` because it depends only on ``apps.shared.clickhouse``
and ``apps.shared.constants`` — no monitoring-specific imports.
"""

import logging

from apps.shared.clickhouse import query
from apps.shared.constants import CH_INCIDENTS

logger = logging.getLogger("sequoia.monitoring.incident_service")


# ---------------------------------------------------------------------------
# Transform — ONE implementation for all paths
# ---------------------------------------------------------------------------


def transform_row(row: dict) -> dict:
    """
    Transform a ClickHouse ``fiber_incidents`` row into the frontend
    Incident shape consumed by REST, WebSocket, and Kafka bridge.

    Handles both datetime objects and bare strings for ``timestamp``.
    Uses ``.get()`` for ``duration_seconds`` because simulation-generated
    rows may omit it.
    """
    ts = row["timestamp"]
    detected_at = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
    dur = row.get("duration_seconds")

    return {
        "id": row["incident_id"],
        "type": row["incident_type"],
        "severity": row["severity"],
        "fiberId": row["fiber_id"],
        "direction": row.get("direction", 0),
        "channel": row["channel_start"],
        "channelEnd": row.get("channel_end", row["channel_start"]),
        "detectedAt": detected_at,
        "status": row["status"],
        "duration": dur * 1000 if dur else None,
        "speedBefore": row.get("speed_before_kmh"),
        "speedDuring": row.get("speed_during_kmh"),
        "speedDropPercent": row.get("speed_drop_percent"),
    }


def transform_simulation_incident(incident) -> dict:
    """
    Transform a simulation ``Incident`` dataclass into the same frontend shape.

    The simulation engine uses ``fiber_line`` for the plain fiber ID
    and ``direction`` for the direction (0 or 1).
    """
    return {
        "id": incident.id,
        "type": incident.type,
        "severity": incident.severity,
        "fiberId": incident.fiber_line,
        "direction": incident.direction,
        "channel": incident.channel,
        "channelEnd": incident.channel,
        "detectedAt": incident.detected_at,
        "status": incident.status,
        "duration": incident.duration,
        "speedBefore": None,
        "speedDuring": None,
        "speedDropPercent": None,
    }


# ---------------------------------------------------------------------------
# Queries — parameterized, org-scoped, consistent limits
# ---------------------------------------------------------------------------

_ACTIVE_SQL_SCOPED = f"""
    SELECT incident_id, incident_type, severity, fiber_id, direction,
           channel_start, channel_end, timestamp, status, duration_seconds,
           speed_before_kmh, speed_during_kmh, speed_drop_percent
    FROM {CH_INCIDENTS}
    FINAL
    WHERE status = 'active'
      AND fiber_id IN {{fids:Array(String)}}
    ORDER BY timestamp DESC
    LIMIT {{lim:UInt32}}
"""

_ACTIVE_SQL_ALL = f"""
    SELECT incident_id, incident_type, severity, fiber_id, direction,
           channel_start, channel_end, timestamp, status, duration_seconds,
           speed_before_kmh, speed_during_kmh, speed_drop_percent
    FROM {CH_INCIDENTS}
    FINAL
    WHERE status = 'active'
    ORDER BY timestamp DESC
    LIMIT {{lim:UInt32}}
"""

_RECENT_SQL_SCOPED = f"""
    SELECT incident_id, incident_type, severity, fiber_id, direction,
           channel_start, channel_end, timestamp, status, duration_seconds,
           speed_before_kmh, speed_during_kmh, speed_drop_percent
    FROM {CH_INCIDENTS}
    FINAL
    WHERE timestamp >= now() - INTERVAL {{hours:UInt32}} HOUR
      AND fiber_id IN {{fids:Array(String)}}
    ORDER BY timestamp DESC
    LIMIT {{lim:UInt32}}
"""

_RECENT_SQL_ALL = f"""
    SELECT incident_id, incident_type, severity, fiber_id, direction,
           channel_start, channel_end, timestamp, status, duration_seconds,
           speed_before_kmh, speed_during_kmh, speed_drop_percent
    FROM {CH_INCIDENTS}
    FINAL
    WHERE timestamp >= now() - INTERVAL {{hours:UInt32}} HOUR
    ORDER BY timestamp DESC
    LIMIT {{lim:UInt32}}
"""


def query_active(
    fiber_ids: list[str] | None = None,
    limit: int = 200,
) -> list[dict]:
    """
    Return currently active incidents, transformed to frontend shape.

    Args:
        fiber_ids: Restrict to these fibers. ``None`` = all (superuser).
        limit: Max rows.

    Raises:
        ClickHouseUnavailableError — caller decides fallback strategy.
    """
    if fiber_ids is not None:
        rows = query(_ACTIVE_SQL_SCOPED, parameters={"fids": fiber_ids, "lim": limit})
    else:
        rows = query(_ACTIVE_SQL_ALL, parameters={"lim": limit})
    return [transform_row(r) for r in rows]


def query_recent(
    fiber_ids: list[str] | None = None,
    hours: int = 24,
    limit: int = 500,
) -> list[dict]:
    """
    Return recent incidents (all statuses) within a time window.

    Args:
        fiber_ids: Restrict to these fibers. ``None`` = all (superuser).
        hours: How far back to look.
        limit: Max rows.

    Raises:
        ClickHouseUnavailableError — caller decides fallback strategy.
    """
    if fiber_ids is not None:
        rows = query(
            _RECENT_SQL_SCOPED, parameters={"fids": fiber_ids, "hours": hours, "lim": limit}
        )
    else:
        rows = query(_RECENT_SQL_ALL, parameters={"hours": hours, "lim": limit})
    return [transform_row(r) for r in rows]


def query_by_id(incident_id: str) -> dict | None:
    """
    Fetch a single incident by ID from ClickHouse.

    Returns a minimal dict with incident_id, fiber_id, direction, status — or None.
    """
    rows = query(
        f"""
        SELECT incident_id, incident_type, severity, fiber_id, direction,
               channel_start, timestamp, status, duration_seconds
        FROM {CH_INCIDENTS}
        FINAL
        WHERE incident_id = {{iid:String}}
        LIMIT 1
        """,
        parameters={"iid": incident_id},
    )
    if not rows:
        return None
    row = rows[0]
    return {
        "incident_id": row["incident_id"],
        "fiber_id": row["fiber_id"],
        "direction": row.get("direction", 0),
        "status": row["status"],
    }


def query_active_raw(
    fiber_ids: list[str] | None = None,
    limit: int = 200,
) -> list[dict]:
    """
    Return raw ClickHouse rows (not transformed) for active incidents.

    Used by Kafka bridge which needs both the raw ``incident_id`` for
    tracking and the transformed shape for broadcast.
    """
    if fiber_ids is not None:
        return list(query(_ACTIVE_SQL_SCOPED, parameters={"fids": fiber_ids, "lim": limit}))
    return list(query(_ACTIVE_SQL_ALL, parameters={"lim": limit}))
