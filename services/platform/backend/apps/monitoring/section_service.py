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
        fiber_ids: Restrict to these fibers. ``None`` = all (superuser).
    """
    if fiber_ids is not None:
        # Expand plain fiber IDs to also match directional variants (e.g. "carros" → "carros", "carros:0", "carros:1")
        expanded = set(fiber_ids)
        for fid in fiber_ids:
            if ":" not in fid:
                expanded.add(f"{fid}:0")
                expanded.add(f"{fid}:1")
        rows = query(
            """
            SELECT section_id, fiber_id, section_name,
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
            parameters={"fids": list(expanded)},
        )
    else:
        rows = query(
            """
            SELECT section_id, fiber_id, section_name,
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
            section_id, fiber_id, section_name,
            channel_start, channel_end,
            expected_travel_time_seconds, alert_threshold_percent,
            is_active, created_at, created_by, updated_at
        ) VALUES (
            {sid:String}, {fid:String}, {name:String},
            {cs:UInt32}, {ce:UInt32},
            NULL, 30.0,
            1, {now:DateTime}, {user:String}, {now2:DateTime}
        )
        """,
        parameters={
            "sid": section_id,
            "fid": fiber_id,
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
            section_id, fiber_id, section_name,
            channel_start, channel_end,
            expected_travel_time_seconds, alert_threshold_percent,
            is_active, created_at, created_by, updated_at
        )
        SELECT
            section_id, fiber_id, section_name,
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
    channel_start: int,
    channel_end: int,
    minutes: int = 60,
) -> list[dict]:
    """
    Query section history with resolution-aware table selection.

    - ≤5 min → ``detection_hires`` grouped by second (1s resolution)
    - >5 min → ``detection_1m`` with ``-Merge`` combinators (1min resolution)

    Returns ``[{time, speed, speedMax, samples}, ...]``.
    """
    if minutes <= 5:
        return _query_section_history_hires(fiber_id, channel_start, channel_end, minutes)
    return _query_section_history_1m(fiber_id, channel_start, channel_end, minutes)


def _query_section_history_hires(
    fiber_id: str,
    channel_start: int,
    channel_end: int,
    minutes: int,
) -> list[dict]:
    """Query detection_hires at 1-second resolution for short windows (≤5 min)."""
    rows = query(
        """
        SELECT
            toUnixTimestamp(toStartOfSecond(ts)) * 1000 AS time_ms,
            avg(speed) AS speed,
            max(speed) AS speed_max,
            count() AS samples
        FROM sequoia.detection_hires
        WHERE fiber_id = {fid:String}
          AND ch BETWEEN {cs:UInt16} AND {ce:UInt16}
          AND ts >= now() - INTERVAL {mins:UInt32} MINUTE
        GROUP BY toStartOfSecond(ts)
        ORDER BY toStartOfSecond(ts)
        """,
        parameters={
            "fid": fiber_id,
            "cs": channel_start,
            "ce": channel_end,
            "mins": minutes,
        },
    )

    return _transform_history_rows(rows)


def _query_section_history_1m(
    fiber_id: str,
    channel_start: int,
    channel_end: int,
    minutes: int,
) -> list[dict]:
    """Query detection_1m at 1-minute resolution using -Merge combinators."""
    rows = query(
        """
        SELECT
            toUnixTimestamp(ts) * 1000 AS time_ms,
            avgMerge(speed_avg_state) AS speed,
            maxMerge(speed_max_state) AS speed_max,
            sumMerge(samples_state) AS samples
        FROM sequoia.detection_1m
        WHERE fiber_id = {fid:String}
          AND ch BETWEEN {cs:UInt16} AND {ce:UInt16}
          AND ts >= now() - INTERVAL {mins:UInt32} MINUTE
        GROUP BY ts
        ORDER BY ts
        """,
        parameters={
            "fid": fiber_id,
            "cs": channel_start,
            "ce": channel_end,
            "mins": minutes,
        },
    )

    return _transform_history_rows(rows)


def _transform_history_rows(rows: list[dict]) -> list[dict]:
    """Transform raw query rows into the section history response shape."""
    return [
        {
            "time": int(r["time_ms"]),
            "speed": round(float(r["speed"]), 1) if r["speed"] is not None else 0,
            "speedMax": round(float(r["speed_max"]), 1) if r["speed_max"] is not None else 0,
            "samples": int(r["samples"]) if r["samples"] is not None else 0,
        }
        for r in rows
    ]


def _transform_section(row: dict) -> dict:
    ca = row["created_at"]
    created = ca.isoformat() if hasattr(ca, "isoformat") else str(ca)

    return {
        "id": row["section_id"],
        "fiberId": row["fiber_id"],
        "name": row["section_name"],
        "channelStart": row["channel_start"],
        "channelEnd": row["channel_end"],
        "expectedTravelTime": row.get("expected_travel_time_seconds"),
        "isActive": bool(row["is_active"]),
        "createdAt": created,
    }
