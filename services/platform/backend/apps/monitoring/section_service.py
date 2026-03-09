"""
Section CRUD via Django ORM (PostgreSQL) and history queries from ClickHouse.

Sections are config data stored in PostgreSQL. Time-series history
(detection_hires, detection_1m) stays in ClickHouse.
"""

from __future__ import annotations

import logging
import math
import uuid
from typing import TYPE_CHECKING

from apps.shared.clickhouse import query

if TYPE_CHECKING:
    from apps.monitoring.models import Section

logger = logging.getLogger("sequoia.sections")


def query_sections(
    organization_id: int | None = None,
    fiber_ids: list[str] | None = None,
) -> list[dict]:
    """
    Return active monitored sections from PostgreSQL.

    Args:
        organization_id: Filter by org. ``None`` = all (superuser).
        fiber_ids: Restrict to these fibers. ``None`` = all visible to org.
    """
    from apps.monitoring.models import Section

    qs = Section.objects.filter(is_active=True)

    if organization_id is not None:
        qs = qs.filter(organization_id=organization_id)

    if fiber_ids is not None:
        qs = qs.filter(fiber_id__in=fiber_ids)

    return [_section_to_dict(s) for s in qs]


def insert_section(
    fiber_id: str,
    name: str,
    channel_start: int,
    channel_end: int,
    direction: int,
    organization_id: int,
    user_id: int | None = None,
) -> dict:
    """
    Create a new monitored section in PostgreSQL.

    Returns the transformed section dict.
    """
    from apps.monitoring.models import Section

    section_id = f"section-{uuid.uuid4().hex[:12]}"

    section = Section.objects.create(
        id=section_id,
        organization_id=organization_id,
        fiber_id=fiber_id,
        direction=direction,
        name=name,
        channel_start=channel_start,
        channel_end=channel_end,
        created_by_id=user_id,
    )

    return _section_to_dict(section)


def delete_section(section_id: str, organization_id: int | None = None) -> bool:
    """
    Delete a section. Returns True if found and deleted.

    Args:
        organization_id: Restrict to this org. ``None`` = any (superuser).
    """
    from apps.monitoring.models import Section

    qs = Section.objects.filter(id=section_id)
    if organization_id is not None:
        qs = qs.filter(organization_id=organization_id)

    deleted_count: int
    deleted_count, _ = qs.delete()
    return deleted_count > 0


def get_section(section_id: str, organization_id: int | None = None) -> dict | None:
    """Fetch a single section by ID, or None if not found / inactive.

    Args:
        organization_id: Restrict to this org. ``None`` = any (superuser).
    """
    from apps.monitoring.models import Section

    qs = Section.objects.filter(id=section_id, is_active=True)
    if organization_id is not None:
        qs = qs.filter(organization_id=organization_id)

    section = qs.first()
    if section is None:
        return None
    return _section_to_dict(section)


def query_section_history(
    fiber_id: str,
    direction: int,
    channel_start: int,
    channel_end: int,
    minutes: int = 60,
    since_ms: int | None = None,
) -> list[dict]:
    """
    Query section history with resolution-aware table selection.

    - ≤5 min → ``detection_hires`` grouped by second (1s resolution)
    - >5 min → ``detection_1m`` with ``-Merge`` combinators (1min resolution)

    Args:
        since_ms: If provided, only return points after this timestamp (ms epoch).
            Used for incremental polling — the frontend sends the timestamp of its
            last known point and receives only new data.

    Returns ``[{time, speed, speedMax, samples, flow, occupancy}, ...]``.
    """
    if minutes <= 5:
        return _query_section_history_hires(
            fiber_id, direction, channel_start, channel_end, minutes, since_ms
        )
    return _query_section_history_1m(
        fiber_id, direction, channel_start, channel_end, minutes, since_ms
    )


def _query_section_history_hires(
    fiber_id: str,
    direction: int,
    channel_start: int,
    channel_end: int,
    minutes: int,
    since_ms: int | None = None,
) -> list[dict]:
    """Query detection_hires at 1-second resolution for short windows (≤5 min).

    Flow is total detections divided by total section channels (including inactive
    ones), so a vehicle seen across N channels isn't counted N times.
    """
    total_channels = max(1, channel_end - channel_start + 1)
    rows = query(
        """
        SELECT
            toUnixTimestamp(toStartOfSecond(ts)) * 1000 AS time_ms,
            avg(speed) AS speed,
            max(speed) AS speed_max,
            count() / {n_ch:UInt32} AS samples
        FROM sequoia.detection_hires
        WHERE fiber_id = {fid:String}
          AND direction = {dir:UInt8}
          AND ch BETWEEN {cs:UInt16} AND {ce:UInt16}
          AND ts >= now() - INTERVAL {mins:UInt32} MINUTE
          AND ({since:UInt64} = 0 OR ts > fromUnixTimestamp64Milli({since:UInt64}))
        GROUP BY toStartOfSecond(ts)
        ORDER BY toStartOfSecond(ts)
        """,
        parameters={
            "fid": fiber_id,
            "dir": direction,
            "cs": channel_start,
            "ce": channel_end,
            "mins": minutes,
            "since": since_ms or 0,
            "n_ch": total_channels,
        },
    )

    return _transform_history_rows(rows, bucket_seconds=1)


def _query_section_history_1m(
    fiber_id: str,
    direction: int,
    channel_start: int,
    channel_end: int,
    minutes: int,
    since_ms: int | None = None,
) -> list[dict]:
    """Query detection_1m at 1-minute resolution using -Merge combinators.

    Flow is total detections divided by total section channels, not sum across all.
    """
    total_channels = max(1, channel_end - channel_start + 1)
    rows = query(
        """
        SELECT
            toUnixTimestamp(ts) * 1000 AS time_ms,
            avgMerge(speed_avg_state) AS speed,
            maxMerge(speed_max_state) AS speed_max,
            sumMerge(samples_state) / {n_ch:UInt32} AS samples
        FROM sequoia.detection_1m
        WHERE fiber_id = {fid:String}
          AND direction = {dir:UInt8}
          AND ch BETWEEN {cs:UInt16} AND {ce:UInt16}
          AND ts >= now() - INTERVAL {mins:UInt32} MINUTE
          AND ({since:UInt64} = 0 OR ts > fromUnixTimestamp64Milli({since:UInt64}))
        GROUP BY ts
        ORDER BY ts
        """,
        parameters={
            "fid": fiber_id,
            "dir": direction,
            "cs": channel_start,
            "ce": channel_end,
            "mins": minutes,
            "since": since_ms or 0,
            "n_ch": total_channels,
        },
    )

    return _transform_history_rows(rows, bucket_seconds=60)


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


def _transform_history_rows(rows: list[dict], bucket_seconds: int = 60) -> list[dict]:
    """Transform raw query rows into the section history response shape.

    Args:
        bucket_seconds: Duration of each time bucket (1 for hires, 60 for 1m).
            Used to correctly scale flow to per-hour for occupancy calculation.

    Computes derived metrics:
    - ``flow``: vehicles per hour (``avg_detections_per_channel * 3600 / bucket_seconds``)
    - ``occupancy``: estimated road occupancy percentage using
      ``(flow_vph * vehicle_length) / (speed_m_s * 1000)``
    """
    return [_transform_history_point(r, bucket_seconds) for r in rows]


def _transform_history_point(r: dict, bucket_seconds: int) -> dict:
    speed = round(float(r["speed"]), 1) if r["speed"] is not None else 0.0
    samples = int(r["samples"]) if r["samples"] is not None else 0

    # Flow = vehicles per hour (standard traffic engineering unit)
    flow = round(samples * (3600 / bucket_seconds))
    occupancy = compute_occupancy(speed, flow)

    return {
        "time": int(r["time_ms"]),
        "speed": speed,
        "speedMax": round(float(r["speed_max"]), 1) if r["speed_max"] is not None else 0,
        "samples": samples,
        "flow": flow,
        "occupancy": occupancy,
    }


def _section_to_dict(section: Section) -> dict:
    """Convert a Section model instance to the API response dict."""
    ca = section.created_at
    created = ca.isoformat() if hasattr(ca, "isoformat") else str(ca)

    return {
        "id": section.id,
        "fiberId": section.fiber_id,
        "direction": section.direction,
        "name": section.name,
        "channelStart": section.channel_start,
        "channelEnd": section.channel_end,
        "expectedTravelTime": section.expected_travel_time_seconds,
        "isActive": section.is_active,
        "createdAt": created,
    }
