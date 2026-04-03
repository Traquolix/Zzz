"""
Section CRUD via Django ORM (PostgreSQL) and history queries from ClickHouse.

Sections are config data stored in PostgreSQL. Time-series history
(detection_hires, detection_1m) stays in ClickHouse.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from apps.monitoring.detection_utils import TIER_TABLES
from apps.shared.clickhouse import query
from apps.shared.traffic_utils import compute_occupancy

if TYPE_CHECKING:
    from apps.monitoring.models import Section

logger = logging.getLogger("sequoia.monitoring.section_service")


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

    qs = Section.objects.filter(id=section_id, is_active=True)
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
        f"""
        SELECT
            toUnixTimestamp(toStartOfSecond(ts)) * 1000 AS time_ms,
            avg(speed) AS speed_avg,
            max(speed) AS speed_max,
            count() / {{n_ch:Float64}} AS samples
        FROM {TIER_TABLES["hires"]}
        WHERE fiber_id = {{fid:String}}
          AND direction = {{dir:UInt8}}
          AND ch BETWEEN {{cs:UInt16}} AND {{ce:UInt16}}
          AND ts >= now() - INTERVAL {{mins:UInt32}} MINUTE
          AND ({{since:UInt64}} = 0 OR ts >= fromUnixTimestamp64Milli({{since:UInt64}} + 1000))
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
        f"""
        SELECT
            toUnixTimestamp(ts) * 1000 AS time_ms,
            avgMerge(speed_avg_state) AS speed_avg,
            maxMerge(speed_max_state) AS speed_max,
            sumMerge(samples_state) / {{n_ch:Float64}} AS samples
        FROM {TIER_TABLES["1m"]}
        WHERE fiber_id = {{fid:String}}
          AND direction = {{dir:UInt8}}
          AND ch BETWEEN {{cs:UInt16}} AND {{ce:UInt16}}
          AND ts >= now() - INTERVAL {{mins:UInt32}} MINUTE
          AND ({{since:UInt64}} = 0 OR ts > fromUnixTimestamp64Milli({{since:UInt64}}))
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
    speed = round(float(r["speed_avg"]), 1) if r["speed_avg"] is not None else 0.0
    samples = float(r["samples"]) if r["samples"] is not None else 0.0

    # Flow = vehicles per hour (standard traffic engineering unit)
    flow = round(samples * (3600 / bucket_seconds))
    occupancy = compute_occupancy(speed, flow)

    return {
        "time": int(r["time_ms"]),
        "speed": speed,
        "speedMax": round(float(r["speed_max"]), 1) if r["speed_max"] is not None else 0,
        "samples": round(samples, 4),
        "flow": flow,
        "occupancy": occupancy,
    }


def query_batch_section_history(
    sections: list[dict],
    minutes: int = 60,
    since_map: dict[str, int] | None = None,
) -> dict[str, list[dict]]:
    """Query history for multiple sections in a single ClickHouse round-trip.

    Each section dict must have: id, fiberId, direction, channelStart, channelEnd.

    Args:
        since_map: Per-section ``{section_id: epoch_ms}`` cursors. Each section
            only returns points after its own cursor. ``None`` = full window.

    Builds a UNION ALL query where each branch is tagged with a section index.
    All per-section values (fiber_id, direction, channel range, since) are
    ClickHouse parameters with indexed suffixes (``fid_0``, ``fid_1``, ...).
    The ``n_ch`` divisor is a literal integer derived from the section config.

    Returns ``{section_id: [{time, speed, speedMax, samples, flow, occupancy}, ...], ...}``.
    """
    if not sections:
        return {}

    since = since_map or {}

    if minutes <= 5:
        return _query_batch_hires(sections, minutes, since)
    return _query_batch_1m(sections, minutes, since)


def _query_batch_hires(
    sections: list[dict], minutes: int, since: dict[str, int]
) -> dict[str, list[dict]]:
    """Batch query detection_hires at 1-second resolution using UNION ALL."""
    parts: list[str] = []
    params: dict = {"mins": minutes}

    for i, sec in enumerate(sections):
        s = f"_{i}"
        params[f"fid{s}"] = sec["fiberId"]
        params[f"dir{s}"] = sec["direction"]
        params[f"cs{s}"] = sec["channelStart"]
        params[f"ce{s}"] = sec["channelEnd"]
        params[f"since{s}"] = since.get(sec["id"], 0)
        params[f"nch{s}"] = max(1, sec["channelEnd"] - sec["channelStart"] + 1)

        parts.append(f"""
            SELECT
                {i} AS section_idx,
                toUnixTimestamp(toStartOfSecond(ts)) * 1000 AS time_ms,
                avg(speed) AS speed_avg,
                max(speed) AS speed_max,
                count() / {{nch{s}:Float64}} AS samples
            FROM {TIER_TABLES["hires"]}
            WHERE fiber_id = {{fid{s}:String}}
              AND direction = {{dir{s}:UInt8}}
              AND ch BETWEEN {{cs{s}:UInt16}} AND {{ce{s}:UInt16}}
              AND ts >= now() - INTERVAL {{mins:UInt32}} MINUTE
              AND ({{since{s}:UInt64}} = 0
                   OR ts >= fromUnixTimestamp64Milli({{since{s}:UInt64}} + 1000))
            GROUP BY toStartOfSecond(ts)
        """)

    sql = " UNION ALL ".join(parts) + " ORDER BY section_idx, time_ms"
    rows = query(sql, parameters=params)
    return _split_batch_rows(rows, sections, bucket_seconds=1)


def _query_batch_1m(
    sections: list[dict], minutes: int, since: dict[str, int]
) -> dict[str, list[dict]]:
    """Batch query detection_1m at 1-minute resolution using UNION ALL."""
    parts: list[str] = []
    params: dict = {"mins": minutes}

    for i, sec in enumerate(sections):
        s = f"_{i}"
        params[f"fid{s}"] = sec["fiberId"]
        params[f"dir{s}"] = sec["direction"]
        params[f"cs{s}"] = sec["channelStart"]
        params[f"ce{s}"] = sec["channelEnd"]
        params[f"since{s}"] = since.get(sec["id"], 0)
        params[f"nch{s}"] = max(1, sec["channelEnd"] - sec["channelStart"] + 1)

        parts.append(f"""
            SELECT
                {i} AS section_idx,
                toUnixTimestamp(ts) * 1000 AS time_ms,
                avgMerge(speed_avg_state) AS speed_avg,
                maxMerge(speed_max_state) AS speed_max,
                sumMerge(samples_state) / {{nch{s}:Float64}} AS samples
            FROM {TIER_TABLES["1m"]}
            WHERE fiber_id = {{fid{s}:String}}
              AND direction = {{dir{s}:UInt8}}
              AND ch BETWEEN {{cs{s}:UInt16}} AND {{ce{s}:UInt16}}
              AND ts >= now() - INTERVAL {{mins:UInt32}} MINUTE
              AND ({{since{s}:UInt64}} = 0
                   OR ts > fromUnixTimestamp64Milli({{since{s}:UInt64}}))
            GROUP BY ts
        """)

    sql = " UNION ALL ".join(parts) + " ORDER BY section_idx, time_ms"
    rows = query(sql, parameters=params)
    return _split_batch_rows(rows, sections, bucket_seconds=60)


def _split_batch_rows(
    rows: list[dict], sections: list[dict], bucket_seconds: int
) -> dict[str, list[dict]]:
    """Split UNION ALL rows back into per-section results by section_idx."""
    result: dict[str, list[dict]] = {sec["id"]: [] for sec in sections}
    for row in rows:
        idx = int(row["section_idx"])
        if 0 <= idx < len(sections):
            result[sections[idx]["id"]].append(_transform_history_point(row, bucket_seconds))
    return result


def _section_to_dict(section: Section) -> dict:
    """Convert a Section model instance to the API response dict."""
    return {
        "id": section.id,
        "fiberId": section.fiber_id,
        "direction": section.direction,
        "name": section.name,
        "channelStart": section.channel_start,
        "channelEnd": section.channel_end,
        "expectedTravelTime": section.expected_travel_time_seconds,
        "isActive": section.is_active,
        "createdAt": section.created_at.isoformat(),
    }
