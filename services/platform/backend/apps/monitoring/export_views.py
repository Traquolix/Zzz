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
from datetime import timedelta

from django.http import JsonResponse, StreamingHttpResponse
from django.utils.dateparse import parse_datetime
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.fibers.utils import get_org_fiber_ids
from apps.shared.clickhouse import get_client
from apps.shared.exceptions import ClickHouseUnavailableError
from apps.shared.permissions import IsActiveUser

logger = logging.getLogger("sequoia.export")

# Maximum time ranges per tier
MAX_HIRES_DAYS = 7
MAX_AGGREGATE_DAYS = 365

# Tier thresholds
HIRES_THRESHOLD = timedelta(hours=48)
MEDIUM_THRESHOLD = timedelta(days=90)


class ExportThrottle(UserRateThrottle):
    scope = "export"


def _parse_params(request):
    """Parse and validate common export parameters. Returns (fiber_id, start, end, format) or raises."""
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


def _check_fiber_access(user, fiber_id):
    """Check if user has access to the specified fiber. Returns True/False."""
    if user.is_superuser:
        return True
    fiber_ids = get_org_fiber_ids(user.organization)
    return fiber_id in fiber_ids


def _select_tier(start, end, explicit_tier=None):
    """Select the appropriate data tier based on time range."""
    duration = end - start

    if explicit_tier == "hires":
        if duration > timedelta(days=MAX_HIRES_DAYS):
            return None, f"Hires tier limited to {MAX_HIRES_DAYS} days"
        return "hires", None

    if explicit_tier:
        return explicit_tier, None

    # Auto-select
    if duration <= HIRES_THRESHOLD:
        return "hires", None
    elif duration <= MEDIUM_THRESHOLD:
        return "1m", None
    else:
        return "1h", None


def _stream_csv(columns, rows):
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


class ExportIncidentsView(APIView):
    """GET /api/export/incidents — export incident data as CSV or JSON."""

    permission_classes = [IsActiveUser]
    throttle_classes = [ExportThrottle]

    def get(self, request):
        fiber_id, start, end, fmt, errors = _parse_params(request)
        if errors:
            return Response({"detail": "; ".join(errors)}, status=400)

        if not _check_fiber_access(request.user, fiber_id):
            return Response({"detail": "Access denied for this fiber"}, status=403)

        try:
            client = get_client()
            result = client.query(
                """
                SELECT incident_id, fiber_id, type, severity,
                       toString(detected_at) as detected_at,
                       channel_start, channel_end, speed_kmh, duration_s
                FROM sequoia.fiber_incidents
                WHERE fiber_id = {fid:String}
                  AND detected_at >= {start:DateTime64(3)}
                  AND detected_at <= {end:DateTime64(3)}
                ORDER BY detected_at DESC
                LIMIT 100000
                """,
                parameters={"fid": fiber_id, "start": start, "end": end},
            )
        except ClickHouseUnavailableError:
            return Response({"detail": "Analytics service temporarily unavailable"}, status=503)

        columns = result.column_names
        rows = result.result_rows

        if fmt == "json":
            data = [dict(zip(columns, row)) for row in rows]
            return JsonResponse(data, safe=False)

        response = StreamingHttpResponse(
            _stream_csv(columns, rows),
            content_type="text/csv",
        )
        response["Content-Disposition"] = 'attachment; filename="incidents.csv"'
        return response


class ExportDetectionsView(APIView):
    """GET /api/export/detections — export detection data with automatic tier selection."""

    permission_classes = [IsActiveUser]
    throttle_classes = [ExportThrottle]

    def get(self, request):
        fiber_id, start, end, fmt, errors = _parse_params(request)
        if errors:
            return Response({"detail": "; ".join(errors)}, status=400)

        if not _check_fiber_access(request.user, fiber_id):
            return Response({"detail": "Access denied for this fiber"}, status=403)

        explicit_tier = request.GET.get("tier")
        tier, tier_error = _select_tier(start, end, explicit_tier)
        if tier_error:
            return Response({"detail": tier_error}, status=400)

        try:
            client = get_client()

            if tier == "hires":
                result = client.query(
                    """
                    SELECT toString(ts) as ts, fiber_id, ch as channel,
                           direction, speed, vehicle_count, n_cars, n_trucks,
                           lng, lat
                    FROM sequoia.detection_hires
                    WHERE fiber_id = {fid:String}
                      AND ts >= {start:DateTime64(3)}
                      AND ts <= {end:DateTime64(3)}
                    ORDER BY ts
                    LIMIT 500000
                    """,
                    parameters={"fid": fiber_id, "start": start, "end": end},
                )
            elif tier == "1m":
                result = client.query(
                    """
                    SELECT toString(ts) as ts, fiber_id, ch as channel,
                           direction,
                           avgMerge(speed_avg_state) as speed_avg,
                           sumMerge(count_sum_state) as vehicle_count,
                           sumMerge(cars_sum_state) as n_cars,
                           sumMerge(trucks_sum_state) as n_trucks,
                           sumMerge(samples_state) as sample_count
                    FROM sequoia.detection_1m
                    WHERE fiber_id = {fid:String}
                      AND ts >= {start:DateTime64(3)}
                      AND ts <= {end:DateTime64(3)}
                    GROUP BY ts, fiber_id, ch, direction
                    ORDER BY ts
                    LIMIT 500000
                    """,
                    parameters={"fid": fiber_id, "start": start, "end": end},
                )
            else:  # 1h
                result = client.query(
                    """
                    SELECT toString(ts) as ts, fiber_id, ch as channel,
                           direction,
                           avgMerge(speed_avg_state) as speed_avg,
                           sumMerge(count_sum_state) as vehicle_count,
                           sumMerge(cars_sum_state) as n_cars,
                           sumMerge(trucks_sum_state) as n_trucks,
                           sumMerge(samples_state) as sample_count
                    FROM sequoia.detection_1h
                    WHERE fiber_id = {fid:String}
                      AND ts >= {start:DateTime64(3)}
                      AND ts <= {end:DateTime64(3)}
                    GROUP BY ts, fiber_id, ch, direction
                    ORDER BY ts
                    LIMIT 500000
                    """,
                    parameters={"fid": fiber_id, "start": start, "end": end},
                )
        except ClickHouseUnavailableError:
            return Response({"detail": "Analytics service temporarily unavailable"}, status=503)

        columns = result.column_names
        rows = result.result_rows

        if fmt == "json":
            data = [dict(zip(columns, row)) for row in rows]
            return JsonResponse(data, safe=False)

        response = StreamingHttpResponse(
            _stream_csv(columns, rows),
            content_type="text/csv",
        )
        response["Content-Disposition"] = 'attachment; filename="detections.csv"'
        return response
