"""
Public incident list and detail endpoints.
"""

from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.fibers.utils import get_org_fiber_ids
from apps.monitoring.detection_serializers import (
    IncidentDetailResponseSerializer,
    IncidentListResponseSerializer,
)
from apps.monitoring.detection_utils import check_fiber_access
from apps.shared.clickhouse import clickhouse_fallback, query
from apps.shared.constants import CH_INCIDENTS
from apps.shared.incident_service import extract_tags

from .auth import IsAPIKeyUser, PublicAPIThrottle
from .params import decode_cursor, encode_cursor


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
            OpenApiParameter("tag", str, required=False, description="Filter by tag"),
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

        limit_str = request.GET.get("limit", "100")
        try:
            limit = max(1, min(int(limit_str), 1000))
        except ValueError:
            return Response(
                {"detail": "limit must be an integer"}, status=status.HTTP_400_BAD_REQUEST
            )

        extra_clauses = []
        extra_params: dict = {}

        tag = request.GET.get("tag")
        if tag:
            extra_clauses.append("AND has(tags, {tag:String})")
            extra_params["tag"] = tag

        status_filter = request.GET.get("status")
        if status_filter:
            extra_clauses.append("AND status = {stat:String}")
            extra_params["stat"] = status_filter

        cursor_clause = ""
        cursor_str = request.GET.get("cursor")
        if cursor_str:
            cursor = decode_cursor(cursor_str)
            if cursor is None:
                return Response({"detail": "Invalid cursor"}, status=status.HTTP_400_BAD_REQUEST)
            cursor_ts, _, _ = cursor
            cursor_clause = "AND detected_at < {cur_ts:DateTime64(3)}"
            extra_params["cur_ts"] = cursor_ts

        filter_sql = " ".join(extra_clauses)
        fetch_limit = limit + 1

        sql = f"""
            SELECT incident_id, fiber_id, type, severity, tags, status,
                   toString(detected_at) as detected_at,
                   channel_start, channel_end, speed_kmh, duration_s
            FROM {CH_INCIDENTS} FINAL
            WHERE fiber_id = {{fid:String}}
              AND detected_at >= {{start:DateTime64(3)}}
              AND detected_at <= {{end:DateTime64(3)}}
              {filter_sql}
              {cursor_clause}
            ORDER BY detected_at DESC
            LIMIT {{lim:UInt32}}
        """

        rows = query(
            sql,
            parameters={
                "fid": fiber_id,
                "start": start,
                "end": end,
                "lim": fetch_limit,
                **extra_params,
            },
        )

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        next_cursor = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = encode_cursor(str(last["detected_at"]), 0, 0)

        data = [
            {
                "incidentId": r["incident_id"],
                "fiberId": r["fiber_id"],
                "type": r["type"],
                "tags": extract_tags(r),
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
    def get(self, request: Request, incident_id: str) -> Response:
        org = request.user.organization
        fiber_ids = get_org_fiber_ids(org)

        rows = query(
            f"""
            SELECT incident_id, fiber_id, type, severity, tags, status,
                   toString(detected_at) as detected_at,
                   channel_start, channel_end, speed_kmh, duration_s
            FROM {CH_INCIDENTS} FINAL
            WHERE incident_id = {{iid:String}}
              AND fiber_id IN {{fids:Array(String)}}
            LIMIT 1
            """,
            parameters={"iid": incident_id, "fids": fiber_ids},
        )

        if not rows:
            return Response({"detail": "Incident not found"}, status=status.HTTP_404_NOT_FOUND)

        row = rows[0]
        return Response(
            {
                "data": {
                    "incidentId": row["incident_id"],
                    "fiberId": row["fiber_id"],
                    "type": row["type"],
                    "tags": extract_tags(row),
                    "status": row["status"],
                    "detectedAt": row["detected_at"],
                    "channelStart": row["channel_start"],
                    "channelEnd": row["channel_end"],
                    "speedKmh": row.get("speed_kmh"),
                    "durationS": row.get("duration_s"),
                }
            }
        )
