"""
Section CRUD and history queries against ClickHouse fiber_monitored_sections
and detection_1m tables.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from apps.shared.clickhouse import query

logger = logging.getLogger("sequoia.sections")


def query_sections(fiber_ids: Optional[list[str]] = None) -> list[dict]:
    """
    Return active monitored sections from ClickHouse.

    Args:
        fiber_ids: Restrict to these fibers (plain IDs). ``None`` = all (superuser).
    """
    if fiber_ids is not None:
        rows = query(
            """
            SELECT section_id, fiber_id, direction, section_name,
                   channel_start, channel_end,
                   expected_travel_time_seconds,
                   alert_threshold_percent,
                   is_active, created_at, created_by, updated_at
            FROM sequoia.fiber_monitored_sections
            FINAL
            WHERE is_active = 1
              AND fiber_id IN {fids:Array(String)}
            ORDER BY fiber_id, channel_start
            """,
            parameters={"fids": fiber_ids},
        )
    else:
        rows = query(
            """
            SELECT section_id, fiber_id, direction, section_name,
                   channel_start, channel_end,
                   expected_travel_time_seconds,
                   alert_threshold_percent,
                   is_active, created_at, created_by, updated_at
            FROM sequoia.fiber_monitored_sections
            FINAL
            WHERE is_active = 1
            ORDER BY fiber_id, channel_start
            """,
        )

    return [_transform_section(r) for r in rows]


def insert_section(
    fiber_id: str,
    name: str,
    channel_start: int,
    channel_end: int,
    direction: int = 0,
    user: str = "",
) -> dict:
    """
    Insert a new monitored section into ClickHouse.

    Returns the transformed section dict.
    """
    section_id = f"section-{uuid.uuid4().hex[:12]}"
    now = datetime.utcnow()

    query(
        """
        INSERT INTO sequoia.fiber_monitored_sections (
            section_id, fiber_id, direction, section_name,
            channel_start, channel_end,
            expected_travel_time_seconds, alert_threshold_percent,
            is_active, created_at, created_by, updated_at
        ) VALUES (
            {sid:String}, {fid:String}, {dir:UInt8}, {name:String},
            {cs:UInt32}, {ce:UInt32},
            NULL, 30.0,
            1, {now:DateTime}, {user:String}, {now2:DateTime}
        )
        """,
        parameters={
            "sid": section_id,
            "fid": fiber_id,
            "dir": direction,
            "name": name,
            "cs": channel_start,
            "ce": channel_end,
            "now": now,
            "user": user,
            "now2": now,
        },
    )

    return {
        "id": section_id,
        "fiberId": fiber_id,
        "direction": direction,
        "name": name,
        "channelStart": channel_start,
        "channelEnd": channel_end,
        "expectedTravelTime": None,
        "isActive": True,
        "createdAt": now.isoformat(),
    }


def delete_section(section_id: str, fiber_id: str) -> None:
    """
    Soft-delete a section by inserting a new row with is_active=0.

    ReplacingMergeTree merges on updated_at, so the newer inactive row wins.
    We need fiber_id because the table is partitioned by it and ORDER BY
    includes (fiber_id, section_id).
    """
    now = datetime.utcnow()

    query(
        """
        INSERT INTO sequoia.fiber_monitored_sections (
            section_id, fiber_id, direction, section_name,
            channel_start, channel_end,
            expected_travel_time_seconds, alert_threshold_percent,
            is_active, created_at, created_by, updated_at
        )
        SELECT
            section_id, fiber_id, direction, section_name,
            channel_start, channel_end,
            expected_travel_time_seconds, alert_threshold_percent,
            0, created_at, created_by, {now:DateTime}
        FROM sequoia.fiber_monitored_sections
        FINAL
        WHERE section_id = {sid:String}
        LIMIT 1
        """,
        parameters={"sid": section_id, "now": now},
    )


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
    """Query detection_hires at 1-second resolution for short windows (≤5 min)."""
    since_clause = ""
    params: dict = {
        "fid": fiber_id,
        "dir": direction,
        "cs": channel_start,
        "ce": channel_end,
        "mins": minutes,
    }
    if since_ms is not None:
        since_clause = "AND ts > fromUnixTimestamp64Milli({since:UInt64})"
        params["since"] = since_ms

    rows = query(
        f"""
        SELECT
            toUnixTimestamp(toStartOfSecond(ts)) * 1000 AS time_ms,
            avg(speed) AS speed,
            max(speed) AS speed_max,
            count() AS samples
        FROM sequoia.detection_hires
        WHERE fiber_id = {{fid:String}}
          AND direction = {{dir:UInt8}}
          AND ch BETWEEN {{cs:UInt16}} AND {{ce:UInt16}}
          AND ts >= now() - INTERVAL {{mins:UInt32}} MINUTE
          {since_clause}
        GROUP BY toStartOfSecond(ts)
        ORDER BY toStartOfSecond(ts)
        """,
        parameters=params,
    )

    return _transform_history_rows(rows)


def _query_section_history_1m(
    fiber_id: str,
    direction: int,
    channel_start: int,
    channel_end: int,
    minutes: int,
    since_ms: int | None = None,
) -> list[dict]:
    """Query detection_1m at 1-minute resolution using -Merge combinators."""
    since_clause = ""
    params: dict = {
        "fid": fiber_id,
        "dir": direction,
        "cs": channel_start,
        "ce": channel_end,
        "mins": minutes,
    }
    if since_ms is not None:
        since_clause = "AND ts > fromUnixTimestamp64Milli({since:UInt64})"
        params["since"] = since_ms

    rows = query(
        f"""
        SELECT
            toUnixTimestamp(ts) * 1000 AS time_ms,
            avgMerge(speed_avg_state) AS speed,
            maxMerge(speed_max_state) AS speed_max,
            sumMerge(samples_state) AS samples
        FROM sequoia.detection_1m
        WHERE fiber_id = {{fid:String}}
          AND direction = {{dir:UInt8}}
          AND ch BETWEEN {{cs:UInt16}} AND {{ce:UInt16}}
          AND ts >= now() - INTERVAL {{mins:UInt32}} MINUTE
          {since_clause}
        GROUP BY ts
        ORDER BY ts
        """,
        parameters=params,
    )

    return _transform_history_rows(rows)


AVG_VEHICLE_LENGTH_M = 6  # meters, for occupancy estimation


def _transform_history_rows(rows: list[dict]) -> list[dict]:
    """Transform raw query rows into the section history response shape.

    Computes derived metrics:
    - ``flow``: vehicle count (= samples) per time bucket
    - ``occupancy``: estimated road occupancy percentage using
      ``(flow_per_hour * vehicle_length) / (speed_m_s * 1000)``
    """
    return [_transform_history_point(r) for r in rows]


def _transform_history_point(r: dict) -> dict:
    speed = round(float(r["speed"]), 1) if r["speed"] is not None else 0.0
    samples = int(r["samples"]) if r["samples"] is not None else 0

    # Flow = samples per bucket (each row is one time bucket)
    flow = samples

    # Occupancy: (flow_per_hour * vehicle_length) / (speed_m_s * 1000)
    speed_ms = speed * (1000 / 3600)
    if speed_ms > 0 and flow > 0:
        flow_per_hour = flow * 60  # rough estimate assuming 1-min buckets
        occupancy = min(100, round((flow_per_hour * AVG_VEHICLE_LENGTH_M) / (speed_ms * 1000)))
    else:
        occupancy = 100 if flow > 0 else 0

    return {
        "time": int(r["time_ms"]),
        "speed": speed,
        "speedMax": round(float(r["speed_max"]), 1) if r["speed_max"] is not None else 0,
        "samples": samples,
        "flow": flow,
        "occupancy": occupancy,
    }


def _transform_section(row: dict) -> dict:
    ca = row["created_at"]
    created = ca.isoformat() if hasattr(ca, "isoformat") else str(ca)

    return {
        "id": row["section_id"],
        "fiberId": row["fiber_id"],
        "direction": row.get("direction", 0),
        "name": row["section_name"],
        "channelStart": row["channel_start"],
        "channelEnd": row["channel_end"],
        "expectedTravelTime": row.get("expected_travel_time_seconds"),
        "isActive": bool(row["is_active"]),
        "createdAt": created,
    }
