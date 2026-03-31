"""
Public detection list and summary endpoints.
"""

import logging

from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.monitoring.detection_serializers import (
    DetectionListResponseSerializer,
    DetectionSummarySerializer,
)
from apps.monitoring.detection_utils import TIER_TABLES, check_fiber_access, select_tier
from apps.shared.clickhouse import clickhouse_fallback, query

from .auth import IsAPIKeyUser, PublicAPIThrottle
from .params import (
    build_aggregate_query,
    build_direction_filter,
    build_hires_query,
    encode_cursor,
    parse_detection_params,
)

logger = logging.getLogger(__name__)


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
                description="Opaque token from a previous response's next_cursor",
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
    def get(self, request: Request) -> Response:
        params, error = parse_detection_params(request)
        if error or params is None:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

        if not check_fiber_access(request.user, params.fiber_id):
            return Response(
                {"detail": "Access denied for this fiber"},
                status=status.HTTP_403_FORBIDDEN,
            )

        tier, tier_error = select_tier(params.start, params.end, params.resolution)
        if tier_error or tier is None:
            return Response({"detail": tier_error}, status=status.HTTP_400_BAD_REQUEST)

        if tier == "hires":
            sql, query_params = build_hires_query(params)
        else:
            table = TIER_TABLES[tier]
            sql, query_params = build_aggregate_query(params, table)

        rows = query(sql, parameters=query_params)

        has_more = len(rows) > params.limit
        if has_more:
            rows = rows[: params.limit]

        next_cursor = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = encode_cursor(
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
    def get(self, request: Request) -> Response:
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
            return Response({"detail": "; ".join(errors)}, status=status.HTTP_400_BAD_REQUEST)

        start = parse_datetime(start_str)
        end = parse_datetime(end_str)
        if start is None or end is None:
            return Response(
                {"detail": "Invalid ISO 8601 format for start or end"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if start >= end:
            return Response(
                {"detail": "start must be before end"}, status=status.HTTP_400_BAD_REQUEST
            )

        if not check_fiber_access(request.user, fiber_id):
            return Response(
                {"detail": "Access denied for this fiber"},
                status=status.HTTP_403_FORBIDDEN,
            )

        resolution = request.GET.get("resolution", "auto")
        tier, tier_error = select_tier(start, end, resolution)
        if tier_error or tier is None:
            return Response({"detail": tier_error}, status=status.HTTP_400_BAD_REQUEST)

        direction = None
        if "direction" in request.GET:
            try:
                direction = int(request.GET["direction"])
                if direction not in (0, 1):
                    return Response(
                        {"detail": "direction must be 0 or 1"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except ValueError:
                return Response(
                    {"detail": "direction must be 0 or 1"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        dir_clause, dir_params = build_direction_filter(direction)

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
                FROM {TIER_TABLES["hires"]}
                WHERE fiber_id = {{fid:String}}
                  AND ts >= {{start:DateTime64(3)}}
                  AND ts <= {{end:DateTime64(3)}}
                  {dir_clause}
            """
        else:
            table = TIER_TABLES[tier]
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
                    FROM {table}
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

        rows = query(sql, parameters=query_params)
        if rows:
            row = rows[0]
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
