"""
Centralized incident query and transform — single source of truth.

Every path that reads incidents (REST, WebSocket initial, Kafka bridge polling,
simulation cache) uses this service so the shape, field names, and query
parameters are defined exactly once.
"""

import logging
from typing import Optional

from apps.shared.clickhouse import query

logger = logging.getLogger("sequoia.incidents")


# ---------------------------------------------------------------------------
# Fiber ID normalization
# ---------------------------------------------------------------------------


def _ensure_directional_fiber_id(fiber_id: str) -> str:
    """
    Ensure ``fiber_id`` has a directional suffix (e.g. ``"carros"`` → ``"carros:0"``).

    ClickHouse ``fiber_incidents.fiber_id`` may store either ``"carros"`` (plain)
    or ``"carros:0"`` (directional) depending on the producer. The frontend
    ``FiberLine.id`` is always directional (``"carros:0"``), so incident lookup
    via ``fibers.find(f => f.id === incident.fiberLine)`` fails if the suffix
    is missing. Default to direction ``0`` when absent.
    """
    if ":" not in fiber_id:
        return f"{fiber_id}:0"
    return fiber_id


def strip_directional_suffix(fiber_id: str) -> str:
    """
    Strip directional suffix to get the parent/physical fiber ID.

    ``"carros:0"`` → ``"carros"``, ``"carros"`` → ``"carros"``.

    Used by org-scoped routing: ``fiber_org_map`` keys are plain fiber IDs
    from ``FiberAssignment.fiber_id``.
    """
    return fiber_id.rsplit(":", 1)[0] if ":" in fiber_id else fiber_id


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

    ``fiber_id`` is normalized to always include a directional suffix
    so frontend ``FiberLine.id`` lookups work correctly.
    """
    ts = row["timestamp"]
    detected_at = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
    dur = row.get("duration_seconds")

    return {
        "id": row["incident_id"],
        "type": row["incident_type"],
        "severity": row["severity"],
        "fiberLine": _ensure_directional_fiber_id(row["fiber_id"]),
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

    The simulation engine uses ``fiber_line`` (not ``fiber_id``) and appends
    ``:0`` for the direction suffix.
    """
    return {
        "id": incident.id,
        "type": incident.type,
        "severity": incident.severity,
        "fiberLine": f"{incident.fiber_line}:0",
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

_ACTIVE_SQL_SCOPED = """
    SELECT incident_id, incident_type, severity, fiber_id,
           channel_start, channel_end, timestamp, status, duration_seconds,
           speed_before_kmh, speed_during_kmh, speed_drop_percent
    FROM sequoia.fiber_incidents
    FINAL
    WHERE status = 'active'
      AND fiber_id IN {fids:Array(String)}
    ORDER BY timestamp DESC
    LIMIT {lim:UInt32}
"""

_ACTIVE_SQL_ALL = """
    SELECT incident_id, incident_type, severity, fiber_id,
           channel_start, channel_end, timestamp, status, duration_seconds,
           speed_before_kmh, speed_during_kmh, speed_drop_percent
    FROM sequoia.fiber_incidents
    FINAL
    WHERE status = 'active'
    ORDER BY timestamp DESC
    LIMIT {lim:UInt32}
"""

_RECENT_SQL_SCOPED = """
    SELECT incident_id, incident_type, severity, fiber_id,
           channel_start, channel_end, timestamp, status, duration_seconds,
           speed_before_kmh, speed_during_kmh, speed_drop_percent
    FROM sequoia.fiber_incidents
    FINAL
    WHERE timestamp >= now() - INTERVAL {hours:UInt32} HOUR
      AND fiber_id IN {fids:Array(String)}
    ORDER BY timestamp DESC
    LIMIT {lim:UInt32}
"""

_RECENT_SQL_ALL = """
    SELECT incident_id, incident_type, severity, fiber_id,
           channel_start, channel_end, timestamp, status, duration_seconds,
           speed_before_kmh, speed_during_kmh, speed_drop_percent
    FROM sequoia.fiber_incidents
    FINAL
    WHERE timestamp >= now() - INTERVAL {hours:UInt32} HOUR
    ORDER BY timestamp DESC
    LIMIT {lim:UInt32}
"""


def query_active(
    fiber_ids: Optional[list[str]] = None,
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
    fiber_ids: Optional[list[str]] = None,
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

    Returns a minimal dict with incident_id, fiber_id, status — or None.
    """
    rows = query(
        """
        SELECT incident_id, incident_type, severity, fiber_id,
               channel_start, timestamp, status, duration_seconds
        FROM sequoia.fiber_incidents
        FINAL
        WHERE incident_id = {iid:String}
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
        "status": row["status"],
    }


def query_active_raw(
    fiber_ids: Optional[list[str]] = None,
    limit: int = 200,
) -> list[dict]:
    """
    Return raw ClickHouse rows (not transformed) for active incidents.

    Used by Kafka bridge which needs both the raw ``incident_id`` for
    tracking and the transformed shape for broadcast.
    """
    if fiber_ids is not None:
        return query(_ACTIVE_SQL_SCOPED, parameters={"fids": fiber_ids, "lim": limit})
    return query(_ACTIVE_SQL_ALL, parameters={"lim": limit})
