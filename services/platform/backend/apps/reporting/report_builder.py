"""
Report builder — queries ClickHouse for time-series data and renders HTML.

Automatically selects the appropriate detection tier based on time range:
  <= 48h  → detection_hires
  <= 90d  → detection_1m (AggregatingMergeTree, uses -Merge combinators)
  > 90d   → detection_1h (AggregatingMergeTree, uses -Merge combinators)
"""

import logging

from django.template.loader import render_to_string
from django.utils.translation import gettext as _

from apps.monitoring.detection_utils import select_tier
from apps.shared.clickhouse import query
from apps.shared.exceptions import ClickHouseUnavailableError

logger = logging.getLogger("sequoia.reporting")


def build_report_html(report) -> str:
    """Query ClickHouse data for the report's time range and render HTML."""
    context = {
        "title": report.title,
        "start_time": report.start_time,
        "end_time": report.end_time,
        "fiber_ids": report.fiber_ids,
        "sections": [],
    }

    for section in report.sections:
        if section == "incidents":
            context["sections"].append(
                {
                    "type": "incidents",
                    "title": _("Incident Summary"),
                    "data": _query_incidents(report),
                }
            )
        elif section == "speed":
            context["sections"].append(
                {
                    "type": "speed",
                    "title": _("Speed Statistics"),
                    "data": _query_speed_stats(report),
                }
            )
        elif section == "volume":
            context["sections"].append(
                {
                    "type": "volume",
                    "title": _("Traffic Volume"),
                    "data": _query_volume(report),
                }
            )

    return str(render_to_string("reporting/report.html", context))


def _query_incidents(report) -> list[dict]:
    """Incident summary grouped by type and severity."""
    try:
        rows = query(
            """
            SELECT
                incident_type,
                severity,
                count() AS total
            FROM sequoia.fiber_incidents
            WHERE fiber_id IN {fids:Array(String)}
              AND timestamp BETWEEN {start:DateTime64(3)} AND {end:DateTime64(3)}
            GROUP BY incident_type, severity
            ORDER BY total DESC
            """,
            parameters={
                "fids": report.fiber_ids,
                "start": report.start_time,
                "end": report.end_time,
            },
        )
    except ClickHouseUnavailableError:
        return []

    return [
        {
            "type": row["incident_type"],
            "severity": row["severity"],
            "count": row["total"],
        }
        for row in rows
    ]


def _query_speed_stats(report) -> list[dict]:
    """Average speed per fiber, using the appropriate detection tier."""
    tier, error = select_tier(report.start_time, report.end_time)
    if tier is None:
        logger.warning("select_tier failed for speed stats: %s", error)
        return []

    try:
        if tier == "hires":
            rows = query(
                """
                SELECT
                    fiber_id,
                    direction,
                    round(avg(abs(speed)), 1) AS avg_speed,
                    round(min(abs(speed)), 1) AS min_speed,
                    round(max(abs(speed)), 1) AS max_speed,
                    count() AS sample_count
                FROM sequoia.detection_hires
                WHERE fiber_id IN {fids:Array(String)}
                  AND ts BETWEEN {start:DateTime64(3)} AND {end:DateTime64(3)}
                GROUP BY fiber_id, direction
                ORDER BY fiber_id, direction
                """,
                parameters={
                    "fids": report.fiber_ids,
                    "start": report.start_time,
                    "end": report.end_time,
                },
            )
        else:
            table = "detection_1m" if tier == "1m" else "detection_1h"
            rows = query(
                f"""
                SELECT
                    fiber_id,
                    direction,
                    round(avgMerge(speed_avg_state), 1) AS avg_speed,
                    round(minMerge(speed_min_state), 1) AS min_speed,
                    round(maxMerge(speed_max_state), 1) AS max_speed,
                    sumMerge(samples_state) AS sample_count
                FROM sequoia.{table}
                WHERE fiber_id IN {{fids:Array(String)}}
                  AND ts BETWEEN {{start:DateTime64(3)}} AND {{end:DateTime64(3)}}
                GROUP BY fiber_id, direction
                ORDER BY fiber_id, direction
                """,
                parameters={
                    "fids": report.fiber_ids,
                    "start": report.start_time,
                    "end": report.end_time,
                },
            )
    except ClickHouseUnavailableError:
        return []

    return [
        {
            "fiberId": row["fiber_id"],
            "direction": row["direction"],
            "avgSpeed": row["avg_speed"],
            "minSpeed": row["min_speed"],
            "maxSpeed": row["max_speed"],
            "sampleCount": row["sample_count"],
        }
        for row in rows
    ]


def _query_volume(report) -> list[dict]:
    """Hourly vehicle count per fiber, using the appropriate detection tier."""
    tier, error = select_tier(report.start_time, report.end_time)
    if tier is None:
        logger.warning("select_tier failed for volume query: %s", error)
        return []

    try:
        if tier == "hires":
            rows = query(
                """
                SELECT
                    fiber_id,
                    direction,
                    toStartOfHour(ts) AS hour,
                    sum(vehicle_count) AS total_vehicles
                FROM sequoia.detection_hires
                WHERE fiber_id IN {fids:Array(String)}
                  AND ts BETWEEN {start:DateTime64(3)} AND {end:DateTime64(3)}
                GROUP BY fiber_id, direction, hour
                ORDER BY fiber_id, direction, hour
                """,
                parameters={
                    "fids": report.fiber_ids,
                    "start": report.start_time,
                    "end": report.end_time,
                },
            )
        else:
            table = "detection_1m" if tier == "1m" else "detection_1h"
            rows = query(
                f"""
                SELECT
                    fiber_id,
                    direction,
                    toStartOfHour(ts) AS hour,
                    sumMerge(count_sum_state) AS total_vehicles
                FROM sequoia.{table}
                WHERE fiber_id IN {{fids:Array(String)}}
                  AND ts BETWEEN {{start:DateTime64(3)}} AND {{end:DateTime64(3)}}
                GROUP BY fiber_id, direction, hour
                ORDER BY fiber_id, direction, hour
                """,
                parameters={
                    "fids": report.fiber_ids,
                    "start": report.start_time,
                    "end": report.end_time,
                },
            )
    except ClickHouseUnavailableError:
        return []

    return [
        {
            "fiberId": row["fiber_id"],
            "direction": row["direction"],
            "hour": row["hour"].isoformat()
            if hasattr(row["hour"], "isoformat")
            else str(row["hour"]),
            "vehicles": row["total_vehicles"],
        }
        for row in rows
    ]
