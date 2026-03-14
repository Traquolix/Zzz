"""
Public detection API (v1) — versioned REST endpoints for external consumers.

Auth: API key only (X-API-Key: sqk_...). JWT is not accepted on these endpoints.
Rate limit: 300 requests/hour per API key.
"""

import base64
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from apps.api_keys.models import APIKey
from apps.fibers.utils import get_org_fiber_ids
from apps.monitoring.detection_serializers import (
    DetectionListResponseSerializer,
    DetectionSummarySerializer,
    IncidentDetailResponseSerializer,
    IncidentListResponseSerializer,
    InfrastructureListResponseSerializer,
    InfrastructureStatusSerializer,
    PublicFiberListResponseSerializer,
    PublicStatsResponseSerializer,
    SectionHistoryResponseSerializer,
    SectionListResponseSerializer,
)
from apps.monitoring.detection_utils import check_fiber_access, select_tier
from apps.monitoring.models import Infrastructure, Section
from apps.shared.clickhouse import clickhouse_fallback, get_client, query_scalar

logger = logging.getLogger("sequoia.public_api")

MAX_LIMIT = 5000
DEFAULT_LIMIT = 1000


class PublicAPIThrottle(SimpleRateThrottle):
    """Rate limiter for public API endpoints, keyed by API key."""

    scope = "public_api"

    def get_cache_key(self, request, view):
        # Key by the API key hash, not the user
        api_key = getattr(request, "auth", None)
        if isinstance(api_key, APIKey):
            return self.cache_format % {"scope": self.scope, "ident": api_key.key_hash[:16]}
        # Fallback: shouldn't happen since IsAPIKeyUser rejects non-API-key requests
        return None


class IsAPIKeyUser(BasePermission):
    """
    Allows access only to requests authenticated via API key.

    Rejects JWT-authenticated requests to keep the public API cleanly separated.
    """

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        # request.auth is set to the APIKey instance by APIKeyAuthentication
        if not isinstance(getattr(request, "auth", None), APIKey):
            return False
        return True


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


def _parse_detection_params(request) -> tuple[DetectionParams | None, str | None]:
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
        cursor = _decode_cursor(cursor_str)
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


def _encode_cursor(ts: str, channel: int, direction: int) -> str:
    """Encode a cursor as base64 JSON."""
    payload = json.dumps([ts, channel, direction], separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_cursor(cursor_str: str) -> tuple[str, int, int] | None:
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
    except Exception:
        return None


def _build_direction_filter(direction: int | None) -> tuple[str, dict]:
    """Build optional direction filter clause."""
    if direction is not None:
        return "AND direction = {dir:UInt8}", {"dir": direction}
    return "", {}


def _build_channel_filter(channel_min: int | None, channel_max: int | None) -> tuple[str, dict]:
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


def _build_cursor_clause(cursor: tuple[str, int, int] | None) -> tuple[str, dict]:
    """Build cursor WHERE clause for keyset pagination."""
    if cursor is None:
        return "", {}
    ts, ch, direction = cursor
    clause = "AND (ts, ch, direction) > ({cur_ts:DateTime64(3)}, {cur_ch:UInt32}, {cur_dir:UInt8})"
    return clause, {"cur_ts": ts, "cur_ch": ch, "cur_dir": direction}


def _build_hires_query(params: DetectionParams) -> tuple[str, dict]:
    """Build ClickHouse query for hires tier with cursor pagination."""
    dir_clause, dir_params = _build_direction_filter(params.direction)
    ch_clause, ch_params = _build_channel_filter(params.channel_min, params.channel_max)
    cursor_clause, cursor_params = _build_cursor_clause(params.cursor)

    # Fetch limit+1 to detect has_more
    fetch_limit = params.limit + 1

    sql = f"""
        SELECT toString(ts) as timestamp, fiber_id, ch as channel,
               direction, speed, vehicle_count, n_cars, n_trucks,
               lng as longitude, lat as latitude
        FROM sequoia.detection_hires
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


def _build_aggregate_query(params: DetectionParams, table: str) -> tuple[str, dict]:
    """Build ClickHouse query for aggregate tier (1m or 1h) with cursor pagination."""
    dir_clause, dir_params = _build_direction_filter(params.direction)
    ch_clause, ch_params = _build_channel_filter(params.channel_min, params.channel_max)
    cursor_clause, cursor_params = _build_cursor_clause(params.cursor)

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
        FROM sequoia.{table}
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


class DetectionListView(APIView):
    """
    GET /api/v1/detections — query detections with filters and cursor pagination.

    Automatically selects the appropriate data tier based on the requested time range,
    or accepts an explicit `resolution` parameter.

    Requires API key authentication (X-API-Key header).
    """

    permission_classes = [IsAPIKeyUser]
    throttle_classes = [PublicAPIThrottle]

    @extend_schema(
        parameters=[
            OpenApiParameter("fiber_id", str, required=True, description="Fiber identifier"),
            OpenApiParameter("start", str, required=True, description="Start time (ISO 8601)"),
            OpenApiParameter("end", str, required=True, description="End time (ISO 8601)"),
            OpenApiParameter("direction", int, required=False, description="Filter by direction"),
            OpenApiParameter("channel_min", int, required=False, description="Min channel"),
            OpenApiParameter("channel_max", int, required=False, description="Max channel"),
            OpenApiParameter(
                "resolution",
                str,
                required=False,
                description="Data resolution: raw, 1m, 1h, or auto (default)",
            ),
            OpenApiParameter("limit", int, required=False, description="Page size (max 5000)"),
            OpenApiParameter(
                "cursor",
                str,
                required=False,
                description="Opaque token from a previous response's next_cursor (for fetching the next page)",
            ),
        ],
        responses={200: DetectionListResponseSerializer},
        tags=["Detections"],
        operation_id="listDetections",
        summary="Query detections",
        description=(
            "Query detection data with filters and cursor-based pagination.\n\n"
            "The API automatically selects the best data tier based on your time range, "
            "or you can specify `resolution` explicitly.\n\n"
            "**Cursor pagination:** if `has_more` is true, pass `next_cursor` as the "
            "`cursor` parameter in your next request."
        ),
    )
    @clickhouse_fallback()
    def get(self, request):
        params, error = _parse_detection_params(request)
        if error:
            return Response({"detail": error}, status=400)

        if not check_fiber_access(request.user, params.fiber_id):
            return Response({"detail": "Access denied for this fiber"}, status=403)

        tier, tier_error = select_tier(params.start, params.end, params.resolution)
        if tier_error:
            return Response({"detail": tier_error}, status=400)

        client = get_client()

        if tier == "hires":
            sql, query_params = _build_hires_query(params)
        else:
            table = f"detection_{tier}"
            sql, query_params = _build_aggregate_query(params, table)

        result = client.query(sql, parameters=query_params)
        columns = result.column_names
        rows = [dict(zip(columns, row)) for row in result.result_rows]

        # Check if there are more pages
        has_more = len(rows) > params.limit
        if has_more:
            rows = rows[: params.limit]

        # Build next cursor from last row
        next_cursor = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = _encode_cursor(
                str(last["timestamp"]),
                int(last["channel"]),
                int(last["direction"]),
            )

        return Response(
            {
                "data": rows,
                "meta": {
                    "tier": tier,
                    "start": params.start.isoformat(),
                    "end": params.end.isoformat(),
                    "fiber_id": params.fiber_id,
                    "count": len(rows),
                    "has_more": has_more,
                    "next_cursor": next_cursor,
                },
            }
        )


class DetectionSummaryView(APIView):
    """
    GET /api/v1/detections/summary — aggregate statistics for a fiber + time range.

    Returns total counts, speed stats, and channel coverage.
    Requires API key authentication.
    """

    permission_classes = [IsAPIKeyUser]
    throttle_classes = [PublicAPIThrottle]

    @extend_schema(
        parameters=[
            OpenApiParameter("fiber_id", str, required=True, description="Fiber identifier"),
            OpenApiParameter("start", str, required=True, description="Start time (ISO 8601)"),
            OpenApiParameter("end", str, required=True, description="End time (ISO 8601)"),
            OpenApiParameter("direction", int, required=False, description="Filter by direction"),
            OpenApiParameter(
                "resolution",
                str,
                required=False,
                description="Data resolution: raw, 1m, 1h, or auto (default)",
            ),
        ],
        responses={200: DetectionSummarySerializer},
        tags=["Detections"],
        operation_id="getDetectionSummary",
        summary="Detection summary",
        description=(
            "Get aggregate statistics (total vehicles, speed stats, channel coverage) "
            "for a fiber and time range."
        ),
    )
    @clickhouse_fallback()
    def get(self, request):
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
            return Response({"detail": "; ".join(errors)}, status=400)

        start = parse_datetime(start_str)
        end = parse_datetime(end_str)
        if start is None or end is None:
            return Response({"detail": "Invalid ISO 8601 format for start or end"}, status=400)
        if start >= end:
            return Response({"detail": "start must be before end"}, status=400)

        if not check_fiber_access(request.user, fiber_id):
            return Response({"detail": "Access denied for this fiber"}, status=403)

        resolution = request.GET.get("resolution", "auto")
        tier, tier_error = select_tier(start, end, resolution)
        if tier_error:
            return Response({"detail": tier_error}, status=400)

        dir_clause, dir_params = _build_direction_filter(
            int(request.GET["direction"]) if "direction" in request.GET else None
        )

        client = get_client()

        if tier == "hires":
            sql = f"""
                SELECT
                    sum(vehicle_count) as total_vehicles,
                    sum(n_cars) as total_cars,
                    sum(n_trucks) as total_trucks,
                    avg(speed) as avg_speed,
                    min(speed) as min_speed,
                    max(speed) as max_speed,
                    uniqExact(ch) as channel_count,
                    count() as record_count
                FROM sequoia.detection_hires
                WHERE fiber_id = {{fid:String}}
                  AND ts >= {{start:DateTime64(3)}}
                  AND ts <= {{end:DateTime64(3)}}
                  {dir_clause}
            """
        else:
            table = f"detection_{tier}"
            sql = f"""
                SELECT
                    sum(vehicle_count) as total_vehicles,
                    sum(n_cars) as total_cars,
                    sum(n_trucks) as total_trucks,
                    avg(speed_avg) as avg_speed,
                    min(speed_avg) as min_speed,
                    max(speed_avg) as max_speed,
                    uniqExact(ch) as channel_count,
                    count() as record_count
                FROM (
                    SELECT ch,
                           avgMerge(speed_avg_state) as speed_avg,
                           sumMerge(count_sum_state) as vehicle_count,
                           sumMerge(cars_sum_state) as n_cars,
                           sumMerge(trucks_sum_state) as n_trucks
                    FROM sequoia.{table}
                    WHERE fiber_id = {{fid:String}}
                      AND ts >= {{start:DateTime64(3)}}
                      AND ts <= {{end:DateTime64(3)}}
                      {dir_clause}
                    GROUP BY ts, fiber_id, ch, direction
                )
            """

        query_params = {
            "fid": fiber_id,
            "start": start,
            "end": end,
            **dir_params,
        }

        result = client.query(sql, parameters=query_params)
        if result.result_rows:
            row = dict(zip(result.column_names, result.result_rows[0]))
        else:
            row = {
                "total_vehicles": 0,
                "total_cars": 0,
                "total_trucks": 0,
                "avg_speed": None,
                "min_speed": None,
                "max_speed": None,
                "channel_count": 0,
                "record_count": 0,
            }

        return Response(
            {
                "fiber_id": fiber_id,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "tier": tier,
                **row,
            }
        )


class PublicFiberListView(APIView):
    """
    GET /api/v1/fibers — list fibers accessible to the API key's organization,
    with data availability metadata.

    Returns fiber IDs, names, directions, channel ranges, and the time range
    of available detection data per fiber.
    """

    permission_classes = [IsAPIKeyUser]
    throttle_classes = [PublicAPIThrottle]

    @extend_schema(
        responses={200: PublicFiberListResponseSerializer},
        tags=["Fibers"],
        operation_id="listFibers",
        summary="List accessible fibers",
        description=(
            "List fibers accessible to your API key's organization, with data "
            "availability metadata (earliest/latest timestamps, hires coverage)."
        ),
    )
    @clickhouse_fallback()
    def get(self, request):
        org = request.user.organization
        fiber_ids = get_org_fiber_ids(org)

        if not fiber_ids:
            return Response({"data": []})

        client = get_client()

        # Get fiber metadata from ClickHouse fiber_cables
        cables_result = client.query(
            """
            SELECT fiber_id, fiber_name, length(channel_coordinates) as channel_count
            FROM sequoia.fiber_cables
            WHERE fiber_id IN {fids:Array(String)}
            ORDER BY fiber_id
            """,
            parameters={"fids": fiber_ids},
        )

        cable_meta: dict[str, dict] = {}
        for row in cables_result.result_rows:
            fid, name, ch_count = row
            cable_meta[fid] = {"name": name, "channel_count": ch_count}

        # Get data availability from detection_1h (permanent storage)
        avail_result = client.query(
            """
            SELECT fiber_id,
                   min(ts) as earliest,
                   max(ts) as latest
            FROM sequoia.detection_1h
            WHERE fiber_id IN {fids:Array(String)}
            GROUP BY fiber_id
            """,
            parameters={"fids": fiber_ids},
        )

        availability: dict[str, dict] = {}
        for row in avail_result.result_rows:
            fid, earliest, latest = row
            availability[fid] = {"earliest": earliest, "latest": latest}

        # Build response — include all assigned fibers, even without cable metadata
        data = []
        for fid in sorted(fiber_ids):
            meta = cable_meta.get(fid, {})
            avail = availability.get(fid, {})
            ch_count = meta.get("channel_count", 0)

            data.append(
                {
                    "fiber_id": fid,
                    "name": meta.get("name", fid),
                    "directions": [0, 1],
                    "channel_range": [0, ch_count - 1] if ch_count > 0 else [0, 0],
                    "data_available": {
                        "earliest": avail.get("earliest"),
                        "latest": avail.get("latest"),
                        "hires_since": (
                            datetime.now(tz=timezone.utc) - timedelta(hours=48)
                        ).isoformat()
                        if avail
                        else None,
                    },
                }
            )

        return Response({"data": data})


# ── Incident endpoints ───────────────────────────────────────────────


class IncidentListAPIView(APIView):
    """
    GET /api/v1/incidents — list incidents for a fiber + time range.

    Cursor-based pagination. Requires API key authentication.
    """

    permission_classes = [IsAPIKeyUser]
    throttle_classes = [PublicAPIThrottle]

    @extend_schema(
        parameters=[
            OpenApiParameter("fiber_id", str, required=True, description="Fiber identifier"),
            OpenApiParameter("start", str, required=True, description="Start time (ISO 8601)"),
            OpenApiParameter("end", str, required=True, description="End time (ISO 8601)"),
            OpenApiParameter("severity", str, required=False, description="Filter by severity"),
            OpenApiParameter("status", str, required=False, description="Filter by status"),
            OpenApiParameter("limit", int, required=False, description="Page size (max 1000)"),
            OpenApiParameter("cursor", str, required=False, description="Pagination cursor"),
        ],
        responses={200: IncidentListResponseSerializer},
        tags=["Incidents"],
        operation_id="listIncidents",
        summary="List incidents",
        description="Query incidents for a fiber and time range with cursor-based pagination.",
    )
    @clickhouse_fallback()
    def get(self, request):
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
            return Response({"detail": "; ".join(errors)}, status=400)

        start = parse_datetime(start_str)
        end = parse_datetime(end_str)
        if start is None or end is None:
            return Response({"detail": "Invalid ISO 8601 format for start or end"}, status=400)
        if start >= end:
            return Response({"detail": "start must be before end"}, status=400)

        if not check_fiber_access(request.user, fiber_id):
            return Response({"detail": "Access denied for this fiber"}, status=403)

        limit_str = request.GET.get("limit", "100")
        try:
            limit = max(1, min(int(limit_str), 1000))
        except ValueError:
            return Response({"detail": "limit must be an integer"}, status=400)

        # Optional filters
        extra_clauses = []
        extra_params: dict = {}

        severity = request.GET.get("severity")
        if severity:
            extra_clauses.append("AND severity = {sev:String}")
            extra_params["sev"] = severity

        status_filter = request.GET.get("status")
        if status_filter:
            extra_clauses.append("AND status = {stat:String}")
            extra_params["stat"] = status_filter

        # Cursor
        cursor_clause = ""
        cursor_str = request.GET.get("cursor")
        if cursor_str:
            cursor = _decode_cursor(cursor_str)
            if cursor is None:
                return Response({"detail": "Invalid cursor"}, status=400)
            cursor_ts, _, _ = cursor
            cursor_clause = "AND detected_at < {cur_ts:DateTime64(3)}"
            extra_params["cur_ts"] = cursor_ts

        filter_sql = " ".join(extra_clauses)
        fetch_limit = limit + 1

        client = get_client()
        sql = f"""
            SELECT incident_id, fiber_id, type, severity, status,
                   toString(detected_at) as detected_at,
                   channel_start, channel_end, speed_kmh, duration_s
            FROM sequoia.fiber_incidents FINAL
            WHERE fiber_id = {{fid:String}}
              AND detected_at >= {{start:DateTime64(3)}}
              AND detected_at <= {{end:DateTime64(3)}}
              {filter_sql}
              {cursor_clause}
            ORDER BY detected_at DESC
            LIMIT {{lim:UInt32}}
        """

        result = client.query(
            sql,
            parameters={
                "fid": fiber_id,
                "start": start,
                "end": end,
                "lim": fetch_limit,
                **extra_params,
            },
        )

        columns = result.column_names
        rows = [dict(zip(columns, row)) for row in result.result_rows]

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        next_cursor = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = _encode_cursor(str(last["detected_at"]), 0, 0)

        # Remap to camelCase
        data = [
            {
                "incidentId": r["incident_id"],
                "fiberId": r["fiber_id"],
                "type": r["type"],
                "severity": r["severity"],
                "status": r["status"],
                "detectedAt": r["detected_at"],
                "channelStart": r["channel_start"],
                "channelEnd": r["channel_end"],
                "speedKmh": r.get("speed_kmh"),
                "durationS": r.get("duration_s"),
            }
            for r in rows
        ]

        return Response(
            {
                "data": data,
                "meta": {
                    "count": len(data),
                    "has_more": has_more,
                    "next_cursor": next_cursor,
                },
            }
        )


class IncidentDetailAPIView(APIView):
    """GET /api/v1/incidents/<id> — single incident detail."""

    permission_classes = [IsAPIKeyUser]
    throttle_classes = [PublicAPIThrottle]

    @extend_schema(
        responses={200: IncidentDetailResponseSerializer},
        tags=["Incidents"],
        operation_id="getIncident",
        summary="Get incident detail",
        description="Retrieve a single incident by ID.",
    )
    @clickhouse_fallback()
    def get(self, request, incident_id):
        org = request.user.organization
        fiber_ids = get_org_fiber_ids(org)

        client = get_client()
        result = client.query(
            """
            SELECT incident_id, fiber_id, type, severity, status,
                   toString(detected_at) as detected_at,
                   channel_start, channel_end, speed_kmh, duration_s
            FROM sequoia.fiber_incidents FINAL
            WHERE incident_id = {iid:String}
              AND fiber_id IN {fids:Array(String)}
            LIMIT 1
            """,
            parameters={"iid": incident_id, "fids": fiber_ids},
        )

        if not result.result_rows:
            return Response({"detail": "Incident not found"}, status=404)

        row = dict(zip(result.column_names, result.result_rows[0]))
        return Response(
            {
                "data": {
                    "incidentId": row["incident_id"],
                    "fiberId": row["fiber_id"],
                    "type": row["type"],
                    "severity": row["severity"],
                    "status": row["status"],
                    "detectedAt": row["detected_at"],
                    "channelStart": row["channel_start"],
                    "channelEnd": row["channel_end"],
                    "speedKmh": row.get("speed_kmh"),
                    "durationS": row.get("duration_s"),
                }
            }
        )


# ── Section endpoints ────────────────────────────────────────────────


class SectionListAPIView(APIView):
    """GET /api/v1/sections — list sections for the org."""

    permission_classes = [IsAPIKeyUser]
    throttle_classes = [PublicAPIThrottle]

    @extend_schema(
        responses={200: SectionListResponseSerializer},
        tags=["Sections"],
        operation_id="listSections",
        summary="List sections",
        description="List all active road sections defined for your organization.",
    )
    def get(self, request):
        org = request.user.organization
        sections = Section.objects.filter(organization=org, is_active=True)

        data = [
            {
                "id": s.id,
                "fiberId": s.fiber_id,
                "direction": s.direction,
                "name": s.name,
                "channelStart": s.channel_start,
                "channelEnd": s.channel_end,
                "isActive": s.is_active,
            }
            for s in sections
        ]

        return Response({"data": data})


class SectionHistoryAPIView(APIView):
    """GET /api/v1/sections/<id>/history — section time-series data."""

    permission_classes = [IsAPIKeyUser]
    throttle_classes = [PublicAPIThrottle]

    @extend_schema(
        parameters=[
            OpenApiParameter("start", str, required=True, description="Start time (ISO 8601)"),
            OpenApiParameter("end", str, required=True, description="End time (ISO 8601)"),
            OpenApiParameter(
                "resolution",
                str,
                required=False,
                description="Data resolution: auto, 1m, or 1h (default: auto)",
            ),
        ],
        responses={200: SectionHistoryResponseSerializer},
        tags=["Sections"],
        operation_id="getSectionHistory",
        summary="Section history",
        description="Get time-series speed, flow, and occupancy data for a section.",
    )
    @clickhouse_fallback()
    def get(self, request, section_id):
        org = request.user.organization
        try:
            section = Section.objects.get(pk=section_id, organization=org, is_active=True)
        except Section.DoesNotExist:
            return Response({"detail": "Section not found"}, status=404)

        start_str = request.GET.get("start")
        end_str = request.GET.get("end")
        if not start_str or not end_str:
            return Response({"detail": "start and end are required"}, status=400)

        start = parse_datetime(start_str)
        end = parse_datetime(end_str)
        if start is None or end is None:
            return Response({"detail": "Invalid ISO 8601 format for start or end"}, status=400)
        if start >= end:
            return Response({"detail": "start must be before end"}, status=400)

        resolution = request.GET.get("resolution", "auto")
        tier, tier_error = select_tier(start, end, resolution)
        if tier_error:
            return Response({"detail": tier_error}, status=400)

        total_channels = max(1, section.channel_end - section.channel_start + 1)
        client = get_client()

        if tier == "hires":
            sql = """
                SELECT
                    toString(toStartOfSecond(ts)) AS timestamp,
                    avg(speed) AS speed,
                    count() / {n_ch:Float64} AS flow,
                    uniqExact(ch) / {n_ch:Float64} AS occupancy
                FROM sequoia.detection_hires
                WHERE fiber_id = {fid:String}
                  AND direction = {dir:UInt8}
                  AND ch BETWEEN {cs:UInt32} AND {ce:UInt32}
                  AND ts >= {start:DateTime64(3)}
                  AND ts <= {end:DateTime64(3)}
                GROUP BY toStartOfSecond(ts)
                ORDER BY toStartOfSecond(ts)
            """
        else:
            table = f"detection_{tier}"
            sql = f"""
                SELECT
                    toString(ts) AS timestamp,
                    avgMerge(speed_avg_state) AS speed,
                    sumMerge(count_sum_state) / {{n_ch:Float64}} AS flow,
                    uniqExact(ch) / {{n_ch:Float64}} AS occupancy
                FROM sequoia.{table}
                WHERE fiber_id = {{fid:String}}
                  AND direction = {{dir:UInt8}}
                  AND ch BETWEEN {{cs:UInt32}} AND {{ce:UInt32}}
                  AND ts >= {{start:DateTime64(3)}}
                  AND ts <= {{end:DateTime64(3)}}
                GROUP BY ts, fiber_id, ch, direction
                ORDER BY ts
            """

        result = client.query(
            sql,
            parameters={
                "fid": section.fiber_id,
                "dir": section.direction,
                "cs": section.channel_start,
                "ce": section.channel_end,
                "start": start,
                "end": end,
                "n_ch": float(total_channels),
            },
        )

        columns = result.column_names
        data = [dict(zip(columns, row)) for row in result.result_rows]

        return Response(
            {
                "data": data,
                "meta": {"section_id": section_id, "tier": tier},
            }
        )


# ── Stats endpoint ───────────────────────────────────────────────────


class StatsAPIView(APIView):
    """GET /api/v1/stats — system-level statistics for the org."""

    permission_classes = [IsAPIKeyUser]
    throttle_classes = [PublicAPIThrottle]

    @extend_schema(
        responses={200: PublicStatsResponseSerializer},
        tags=["Stats"],
        operation_id="getStats",
        summary="System statistics",
        description="Get aggregate system statistics for your organization.",
    )
    @clickhouse_fallback()
    def get(self, request):
        org = request.user.organization
        fiber_ids = get_org_fiber_ids(org)

        if not fiber_ids:
            return Response(
                {
                    "data": {
                        "fiberCount": 0,
                        "totalChannels": 0,
                        "activeIncidents": 0,
                        "detectionsPerSecond": 0.0,
                    }
                }
            )

        fiber_count = (
            query_scalar(
                "SELECT count(DISTINCT fiber_id) FROM sequoia.fiber_cables "
                "WHERE fiber_id IN {fids:Array(String)}",
                parameters={"fids": fiber_ids},
            )
            or 0
        )

        total_channels = (
            query_scalar(
                "SELECT sum(length(channel_coordinates)) FROM sequoia.fiber_cables "
                "WHERE fiber_id IN {fids:Array(String)}",
                parameters={"fids": fiber_ids},
            )
            or 0
        )

        active_incidents = (
            query_scalar(
                "SELECT count() FROM sequoia.fiber_incidents FINAL "
                "WHERE status = 'active' AND fiber_id IN {fids:Array(String)}",
                parameters={"fids": fiber_ids},
            )
            or 0
        )

        recent_rows = (
            query_scalar(
                "SELECT count() / 10 FROM sequoia.detection_hires "
                "WHERE ts >= now() - INTERVAL 10 SECOND "
                "AND fiber_id IN {fids:Array(String)}",
                parameters={"fids": fiber_ids},
            )
            or 0
        )

        return Response(
            {
                "data": {
                    "fiberCount": fiber_count,
                    "totalChannels": total_channels,
                    "activeIncidents": active_incidents,
                    "detectionsPerSecond": round(float(recent_rows), 1),
                }
            }
        )


# ── Infrastructure endpoints ────────────────────────────────────────


class InfrastructureListAPIView(APIView):
    """GET /api/v1/infrastructure — list SHM infrastructure items for the org."""

    permission_classes = [IsAPIKeyUser]
    throttle_classes = [PublicAPIThrottle]

    @extend_schema(
        responses={200: InfrastructureListResponseSerializer},
        tags=["Infrastructure"],
        operation_id="listInfrastructure",
        summary="List infrastructure",
        description="List SHM infrastructure items (bridges, tunnels) for your organization.",
    )
    def get(self, request):
        org = request.user.organization
        items = Infrastructure.objects.filter(organization=org)

        data = [
            {
                "id": item.id,
                "type": item.type,
                "name": item.name,
                "fiberId": item.fiber_id,
                "direction": item.direction,
                "startChannel": item.start_channel,
                "endChannel": item.end_channel,
            }
            for item in items
        ]

        return Response({"data": data})


class InfrastructureStatusAPIView(APIView):
    """GET /api/v1/infrastructure/<id>/status — current SHM status for an item."""

    permission_classes = [IsAPIKeyUser]
    throttle_classes = [PublicAPIThrottle]

    @extend_schema(
        responses={200: InfrastructureStatusSerializer},
        tags=["Infrastructure"],
        operation_id="getInfrastructureStatus",
        summary="Infrastructure SHM status",
        description="Get the current structural health monitoring status for an infrastructure item.",
    )
    def get(self, request, infra_id):
        import random

        import numpy as np

        from apps.monitoring.shm_intelligence import compute_baseline, detect_frequency_shift

        org = request.user.organization
        if not Infrastructure.objects.filter(id=infra_id, organization=org).exists():
            return Response({"detail": "Infrastructure not found"}, status=404)

        # Deterministic demo data seeded by infra_id
        rng = random.Random(infra_id)
        baseline_freqs = np.array([1.10 + rng.gauss(0, 0.02) for _ in range(20)])
        baseline = compute_baseline(baseline_freqs)

        if baseline is None:
            return Response(
                {"detail": "Insufficient baseline data", "code": "insufficient_data"},
                status=400,
            )

        current_freqs = np.array([1.12 + rng.gauss(0, 0.03) for _ in range(10)])
        shift = detect_frequency_shift(baseline, current_freqs)

        status_map = {
            "normal": "nominal",
            "warning": "warning",
            "alert": "warning",
            "critical": "critical",
        }

        return Response(
            {
                "data": {
                    "status": status_map.get(shift.severity, "nominal"),
                    "currentMean": round(shift.current_mean, 4),
                    "baselineMean": round(shift.baseline_mean, 4),
                    "deviationSigma": round(shift.deviation_sigma, 2),
                    "direction": shift.direction,
                    "severity": shift.severity,
                }
            }
        )
