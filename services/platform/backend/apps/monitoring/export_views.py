"""
Bulk data export views — CSV/JSON downloads for incidents and detections.

Features:
- Automatic tier selection: hires (<48h), 1m (48h-90d), 1h (>90d)
- Org-scoped via FiberAssignment
- Streaming CSV for large result sets
- Rate limited (10/hour)
"""

import csv
import io
import logging
from collections.abc import Generator
from datetime import datetime
from typing import Any

from django.http import JsonResponse, StreamingHttpResponse
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.exceptions import ParseError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.monitoring.detection_utils import (
    CH_INCIDENTS,
    TIER_TABLES,
    check_fiber_access,
    select_tier,
)
from apps.monitoring.mixins import FlowAwareMixin
from apps.shared.clickhouse import clickhouse_fallback, query, query_scalar
from apps.shared.permissions import IsActiveUser

logger = logging.getLogger("sequoia.monitoring.export_views")


class ExportThrottle(UserRateThrottle):
    scope = "export"


class ExportEstimateThrottle(UserRateThrottle):
    scope = "export_estimate"


def _parse_params(
    request: Request,
) -> tuple[str | None, datetime | None, datetime | None, str | None, list[str] | None]:
    """Parse and validate common export parameters. Returns (fiber_id, start, end, format, errors)."""
    fiber_id = request.GET.get("fiber_id")
    start_str = request.GET.get("start")
    end_str = request.GET.get("end")
    fmt = request.GET.get("fmt", request.GET.get("format", "csv"))

    errors = []
    if not fiber_id:
        errors.append("fiber_id is required")
    if not start_str:
        errors.append("start is required")
    if not end_str:
        errors.append("end is required")
    if errors:
        return None, None, None, None, errors

    start = parse_datetime(start_str)
    end = parse_datetime(end_str)

    # Handle date-only strings
    if start is None:
        from django.utils.dateparse import parse_date

        d = parse_date(start_str)
        if d:
            from django.utils import timezone

            start = timezone.make_aware(timezone.datetime(d.year, d.month, d.day))
    if end is None:
        from django.utils.dateparse import parse_date

        d = parse_date(end_str)
        if d:
            from django.utils import timezone

            end = timezone.make_aware(timezone.datetime(d.year, d.month, d.day, 23, 59, 59))

    if start is None or end is None:
        errors.append("Invalid date format for start or end")
        return None, None, None, None, errors

    return fiber_id, start, end, fmt, None


def _build_direction_clause(request: Request) -> tuple[str, dict[str, Any]]:
    """Build optional direction filter for export queries."""
    direction = request.GET.get("direction")
    if direction is not None:
        try:
            direction = int(direction)
            if direction not in (0, 1):
                return "", {}
            return "AND direction = {dir:UInt8}", {"dir": direction}
        except ValueError:
            return "", {}
    return "", {}


def _build_channel_clause(request: Request, column: str = "ch") -> tuple[str, dict[str, Any]]:
    """Build optional channel range filter for export queries."""
    ch_start = request.GET.get("channel_start")
    ch_end = request.GET.get("channel_end")
    clause_parts: list[str] = []
    params: dict = {}
    if ch_start is not None:
        try:
            clause_parts.append(f"AND {column} >= {{ch_start:UInt32}}")
            params["ch_start"] = int(ch_start)
        except ValueError:
            pass
    if ch_end is not None:
        try:
            clause_parts.append(f"AND {column} <= {{ch_end:UInt32}}")
            params["ch_end"] = int(ch_end)
        except ValueError:
            pass
    return " ".join(clause_parts), params


def _stream_csv(columns: list[str], rows: list[list[Any]]) -> Generator[str, None, None]:
    """Generator that yields CSV rows."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)
    yield output.getvalue()
    output.seek(0)
    output.truncate(0)

    for row in rows:
        writer.writerow(row)
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)


class ExportIncidentsView(FlowAwareMixin, APIView):
    """
    GET /api/export/incidents — export incident data as CSV or JSON.

    Live flow only — sim data is ephemeral and not meant for export.
    """

    permission_classes = [IsActiveUser]
    throttle_classes = [ExportThrottle]

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        if self._is_sim(request):
            raise ParseError("Export is not available for simulation data")

    @clickhouse_fallback()
    def get(self, request: Request) -> Response | StreamingHttpResponse | JsonResponse:
        fiber_id, start, end, fmt, errors = _parse_params(request)
        if errors:
            return Response({"detail": "; ".join(errors)}, status=status.HTTP_400_BAD_REQUEST)
        if fiber_id is None or start is None or end is None:
            return Response({"detail": "Missing parameters"}, status=status.HTTP_400_BAD_REQUEST)

        if not check_fiber_access(request.user, fiber_id):
            return Response(
                {"detail": "Access denied for this fiber"}, status=status.HTTP_403_FORBIDDEN
            )

        dir_clause, dir_params = _build_direction_clause(request)
        ch_clause, ch_params = _build_channel_clause(request, column="channel_start")

        rows = query(
            f"""
            SELECT incident_id, fiber_id, type, severity, tags, direction,
                   toString(detected_at) as detected_at,
                   channel_start, channel_end, speed_kmh, duration_s
            FROM {CH_INCIDENTS}
            WHERE fiber_id = {{fid:String}}
              AND detected_at >= {{start:DateTime64(3)}}
              AND detected_at <= {{end:DateTime64(3)}}
              {dir_clause}
              {ch_clause}
            ORDER BY detected_at DESC
            LIMIT 100000
            """,
            parameters={
                "fid": fiber_id,
                "start": start,
                "end": end,
                **dir_params,
                **ch_params,
            },
        )

        if fmt == "json":
            return JsonResponse(rows, safe=False)

        columns = list(rows[0].keys()) if rows else []
        csv_rows = [list(row.values()) for row in rows]

        response = StreamingHttpResponse(
            _stream_csv(columns, csv_rows),
            content_type="text/csv",
        )
        response["Content-Disposition"] = 'attachment; filename="incidents.csv"'
        return response


class ExportDetectionsView(FlowAwareMixin, APIView):
    """
    GET /api/export/detections — export detection data with automatic tier selection.

    Live flow only — sim data is ephemeral and not meant for export.
    Supports optional `direction` query parameter (0 or 1).
    """

    permission_classes = [IsActiveUser]
    throttle_classes = [ExportThrottle]

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        if self._is_sim(request):
            raise ParseError("Export is not available for simulation data")

    @clickhouse_fallback()
    def get(self, request: Request) -> Response | StreamingHttpResponse | JsonResponse:
        fiber_id, start, end, fmt, errors = _parse_params(request)
        if errors:
            return Response({"detail": "; ".join(errors)}, status=status.HTTP_400_BAD_REQUEST)
        if fiber_id is None or start is None or end is None:
            return Response({"detail": "Missing parameters"}, status=status.HTTP_400_BAD_REQUEST)

        if not check_fiber_access(request.user, fiber_id):
            return Response(
                {"detail": "Access denied for this fiber"}, status=status.HTTP_403_FORBIDDEN
            )

        explicit_tier = request.GET.get("tier")
        tier, tier_error = select_tier(start, end, explicit_tier)
        if tier_error or tier is None:
            return Response({"detail": tier_error}, status=status.HTTP_400_BAD_REQUEST)

        dir_clause, dir_params = _build_direction_clause(request)
        ch_clause, ch_params = _build_channel_clause(request)

        base_params = {
            "fid": fiber_id,
            "start": start,
            "end": end,
            **dir_params,
            **ch_params,
        }

        if tier == "hires":
            rows = query(
                f"""
                SELECT toString(ts) as timestamp, fiber_id, ch as channel,
                       direction, speed, vehicle_count, n_cars, n_trucks,
                       lng, lat
                FROM {TIER_TABLES["hires"]}
                WHERE fiber_id = {{fid:String}}
                  AND ts >= {{start:DateTime64(3)}}
                  AND ts <= {{end:DateTime64(3)}}
                  {dir_clause}
                  {ch_clause}
                ORDER BY ts
                LIMIT 500000
                """,
                parameters=base_params,
            )
        else:
            table = TIER_TABLES[tier]
            rows = query(
                f"""
                SELECT toString(ts) as timestamp, fiber_id, ch as channel,
                       direction,
                       avgMerge(speed_avg_state) as speed_avg,
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
                GROUP BY ts, fiber_id, ch, direction
                ORDER BY ts
                LIMIT 500000
                """,
                parameters=base_params,
            )

        if fmt == "json":
            return JsonResponse(rows, safe=False)

        columns = list(rows[0].keys()) if rows else []
        csv_rows = [list(row.values()) for row in rows]

        response = StreamingHttpResponse(
            _stream_csv(columns, csv_rows),
            content_type="text/csv",
        )
        response["Content-Disposition"] = 'attachment; filename="detections.csv"'
        return response


# Approximate CSV bytes per row (measured from real exports)
AVG_BYTES_PER_ROW: dict[str, int] = {
    "hires": 100,
    "1m": 90,
    "1h": 90,
    "incidents": 120,
}


class ExportEstimateView(APIView):
    """GET /api/export/estimate — estimate row count before downloading."""

    permission_classes = [IsActiveUser]
    throttle_classes = [ExportEstimateThrottle]

    @clickhouse_fallback()
    def get(self, request: Request) -> Response:
        fiber_id, start, end, _, errors = _parse_params(request)
        if errors:
            return Response({"detail": "; ".join(errors)}, status=status.HTTP_400_BAD_REQUEST)
        if fiber_id is None or start is None or end is None:
            return Response({"detail": "Missing parameters"}, status=status.HTTP_400_BAD_REQUEST)

        if not check_fiber_access(request.user, fiber_id):
            return Response(
                {"detail": "Access denied for this fiber"}, status=status.HTTP_403_FORBIDDEN
            )

        data_type = request.GET.get("type", "detections")
        if data_type not in ("detections", "incidents"):
            return Response(
                {"detail": "type must be 'detections' or 'incidents'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        dir_clause, dir_params = _build_direction_clause(request)
        ch_clause, ch_params = _build_channel_clause(request)

        if data_type == "incidents":
            # Incidents use channel_start/channel_end columns, not ch
            inc_ch_clause, inc_ch_params = _build_channel_clause(request, column="channel_start")
            count = query_scalar(
                f"""
                SELECT count() as cnt
                FROM {CH_INCIDENTS}
                WHERE fiber_id = {{fid:String}}
                  AND detected_at >= {{start:DateTime64(3)}}
                  AND detected_at <= {{end:DateTime64(3)}}
                  {dir_clause}
                  {inc_ch_clause}
                """,
                parameters={
                    "fid": fiber_id,
                    "start": start,
                    "end": end,
                    **dir_params,
                    **inc_ch_params,
                },
            )
            tier = None
        else:
            explicit_tier = request.GET.get("tier")
            tier, tier_error = select_tier(start, end, explicit_tier)
            if tier_error or tier is None:
                return Response({"detail": tier_error}, status=status.HTTP_400_BAD_REQUEST)

            table = TIER_TABLES[tier]

            count = query_scalar(
                f"""
                SELECT count() as cnt
                FROM {table}
                WHERE fiber_id = {{fid:String}}
                  AND ts >= {{start:DateTime64(3)}}
                  AND ts <= {{end:DateTime64(3)}}
                  {dir_clause}
                  {ch_clause}
                """,
                parameters={
                    "fid": fiber_id,
                    "start": start,
                    "end": end,
                    **dir_params,
                    **ch_params,
                },
            )

        rows: int = count or 0
        bpr: int = AVG_BYTES_PER_ROW.get(tier, 120) if tier else AVG_BYTES_PER_ROW["incidents"]
        estimated_size: int = rows * bpr

        return Response({"estimatedRows": rows, "estimatedSize": estimated_size, "tier": tier})
