"""
Detection query parameter parsing, validation, and query building.

Shared across detection list and summary endpoints.
"""

import base64
import json
from dataclasses import dataclass
from datetime import datetime

from django.utils.dateparse import parse_datetime
from rest_framework.request import Request

from apps.monitoring.detection_utils import TIER_TABLES

MAX_LIMIT = 5000
DEFAULT_LIMIT = 1000


@dataclass
class DetectionParams:
    """Parsed and validated detection query parameters."""

    fiber_id: str
    start: datetime
    end: datetime
    direction: int | None
    channel_min: int | None
    channel_max: int | None
    resolution: str
    limit: int
    cursor: tuple[str, int, int] | None  # (ts, channel, direction)


def parse_detection_params(request: Request) -> tuple[DetectionParams | None, str | None]:
    """Parse query params for detection endpoints. Returns (params, error)."""
    fiber_id = request.GET.get("fiber_id")
    start_str = request.GET.get("start")
    end_str = request.GET.get("end")

    errors = []
    if not fiber_id:
        errors.append("fiber_id is required")
    if not start_str:
        errors.append("start is required")
    if not end_str:
        errors.append("end is required")
    if errors:
        return None, "; ".join(errors)

    start = parse_datetime(start_str)
    end = parse_datetime(end_str)
    if start is None or end is None:
        return None, "Invalid ISO 8601 format for start or end"
    if start >= end:
        return None, "start must be before end"

    # Optional filters
    direction = request.GET.get("direction")
    if direction is not None:
        try:
            direction = int(direction)
            if direction not in (0, 1):
                return None, "direction must be 0 or 1"
        except ValueError:
            return None, "direction must be 0 or 1"

    channel_min = request.GET.get("channel_min")
    if channel_min is not None:
        try:
            channel_min = int(channel_min)
        except ValueError:
            return None, "channel_min must be an integer"

    channel_max = request.GET.get("channel_max")
    if channel_max is not None:
        try:
            channel_max = int(channel_max)
        except ValueError:
            return None, "channel_max must be an integer"

    resolution = request.GET.get("resolution", "auto")
    if resolution not in ("raw", "1m", "1h", "auto"):
        return None, "resolution must be one of: raw, 1m, 1h, auto"

    limit_str = request.GET.get("limit", str(DEFAULT_LIMIT))
    try:
        limit = int(limit_str)
        limit = max(1, min(limit, MAX_LIMIT))
    except ValueError:
        return None, "limit must be an integer"

    # Cursor decoding
    cursor = None
    cursor_str = request.GET.get("cursor")
    if cursor_str:
        cursor = decode_cursor(cursor_str)
        if cursor is None:
            return None, "Invalid cursor"

    return DetectionParams(
        fiber_id=fiber_id,
        start=start,
        end=end,
        direction=direction,
        channel_min=channel_min,
        channel_max=channel_max,
        resolution=resolution,
        limit=limit,
        cursor=cursor,
    ), None


def encode_cursor(ts: str, channel: int, direction: int) -> str:
    """Encode a cursor as base64 JSON."""
    payload = json.dumps([ts, channel, direction], separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor_str: str) -> tuple[str, int, int] | None:
    """Decode a cursor from base64 JSON. Returns (ts, channel, direction) or None."""
    try:
        payload = base64.urlsafe_b64decode(cursor_str.encode()).decode()
        parts = json.loads(payload)
        if not isinstance(parts, list) or len(parts) != 3:
            return None
        ts, channel, direction = parts
        if (
            not isinstance(ts, str)
            or not isinstance(channel, int)
            or not isinstance(direction, int)
        ):
            return None
        return (ts, channel, direction)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, IndexError, KeyError):
        return None


def build_direction_filter(direction: int | None) -> tuple[str, dict]:
    """Build optional direction filter clause."""
    if direction is not None:
        return "AND direction = {dir:UInt8}", {"dir": direction}
    return "", {}


def build_channel_filter(channel_min: int | None, channel_max: int | None) -> tuple[str, dict]:
    """Build optional channel range filter clause."""
    clauses = []
    params: dict = {}
    if channel_min is not None:
        clauses.append("AND ch >= {ch_min:UInt32}")
        params["ch_min"] = channel_min
    if channel_max is not None:
        clauses.append("AND ch <= {ch_max:UInt32}")
        params["ch_max"] = channel_max
    return " ".join(clauses), params


def build_cursor_clause(cursor: tuple[str, int, int] | None) -> tuple[str, dict]:
    """Build cursor WHERE clause for keyset pagination."""
    if cursor is None:
        return "", {}
    ts, ch, direction = cursor
    clause = "AND (ts, ch, direction) > ({cur_ts:DateTime64(3)}, {cur_ch:UInt32}, {cur_dir:UInt8})"
    return clause, {"cur_ts": ts, "cur_ch": ch, "cur_dir": direction}


def build_hires_query(params: DetectionParams) -> tuple[str, dict]:
    """Build ClickHouse query for hires tier with cursor pagination."""
    dir_clause, dir_params = build_direction_filter(params.direction)
    ch_clause, ch_params = build_channel_filter(params.channel_min, params.channel_max)
    cursor_clause, cursor_params = build_cursor_clause(params.cursor)

    fetch_limit = params.limit + 1

    sql = f"""
        SELECT toString(ts) as timestamp, fiber_id, ch as channel,
               direction, speed, vehicle_count, n_cars, n_trucks,
               lng as longitude, lat as latitude
        FROM {TIER_TABLES["hires"]}
        WHERE fiber_id = {{fid:String}}
          AND ts >= {{start:DateTime64(3)}}
          AND ts <= {{end:DateTime64(3)}}
          {dir_clause}
          {ch_clause}
          {cursor_clause}
        ORDER BY ts, ch, direction
        LIMIT {{lim:UInt32}}
    """

    query_params = {
        "fid": params.fiber_id,
        "start": params.start,
        "end": params.end,
        "lim": fetch_limit,
        **dir_params,
        **ch_params,
        **cursor_params,
    }
    return sql, query_params


def build_aggregate_query(params: DetectionParams, table: str) -> tuple[str, dict]:
    """Build ClickHouse query for aggregate tier (1m or 1h) with cursor pagination."""
    dir_clause, dir_params = build_direction_filter(params.direction)
    ch_clause, ch_params = build_channel_filter(params.channel_min, params.channel_max)
    cursor_clause, cursor_params = build_cursor_clause(params.cursor)

    fetch_limit = params.limit + 1

    sql = f"""
        SELECT toString(ts) as timestamp, fiber_id, ch as channel,
               direction,
               avgMerge(speed_avg_state) as speed_avg,
               minMerge(speed_min_state) as speed_min,
               maxMerge(speed_max_state) as speed_max,
               sumMerge(count_sum_state) as vehicle_count,
               sumMerge(cars_sum_state) as n_cars,
               sumMerge(trucks_sum_state) as n_trucks,
               sumMerge(samples_state) as sample_count
        FROM {table}
        WHERE fiber_id = {{fid:String}}
          AND ts >= {{start:DateTime64(3)}}
          AND ts <= {{end:DateTime64(3)}}
          {dir_clause}
          {ch_clause}
          {cursor_clause}
        GROUP BY ts, fiber_id, ch, direction
        ORDER BY ts, ch, direction
        LIMIT {{lim:UInt32}}
    """

    query_params = {
        "fid": params.fiber_id,
        "start": params.start,
        "end": params.end,
        "lim": fetch_limit,
        **dir_params,
        **ch_params,
        **cursor_params,
    }
    return sql, query_params
