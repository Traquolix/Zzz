"""
Public section list and history endpoints.
"""

from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.monitoring.detection_serializers import (
    SectionHistoryResponseSerializer,
    SectionListResponseSerializer,
)
from apps.monitoring.detection_utils import TIER_TABLES, select_tier
from apps.monitoring.models import Section
from apps.shared.clickhouse import clickhouse_fallback, query

from .auth import IsAPIKeyUser, PublicAPIThrottle


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
    def get(self, request: Request) -> Response:
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
    def get(self, request: Request, section_id: str) -> Response:
        org = request.user.organization
        try:
            section = Section.objects.get(pk=section_id, organization=org, is_active=True)
        except Section.DoesNotExist:
            return Response({"detail": "Section not found"}, status=status.HTTP_404_NOT_FOUND)

        start_str = request.GET.get("start")
        end_str = request.GET.get("end")
        if not start_str or not end_str:
            return Response(
                {"detail": "start and end are required"}, status=status.HTTP_400_BAD_REQUEST
            )

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

        resolution = request.GET.get("resolution", "auto")
        tier, tier_error = select_tier(start, end, resolution)
        if tier_error or tier is None:
            return Response({"detail": tier_error}, status=status.HTTP_400_BAD_REQUEST)

        total_channels = max(1, section.channel_end - section.channel_start + 1)

        if tier == "hires":
            sql = f"""
                SELECT
                    toString(toStartOfSecond(ts)) AS timestamp,
                    avg(speed) AS speed,
                    count() / {{n_ch:Float64}} AS flow,
                    uniqExact(ch) / {{n_ch:Float64}} AS occupancy
                FROM {TIER_TABLES["hires"]}
                WHERE fiber_id = {{fid:String}}
                  AND direction = {{dir:UInt8}}
                  AND ch BETWEEN {{cs:UInt32}} AND {{ce:UInt32}}
                  AND ts >= {{start:DateTime64(3)}}
                  AND ts <= {{end:DateTime64(3)}}
                GROUP BY toStartOfSecond(ts)
                ORDER BY toStartOfSecond(ts)
            """
        else:
            table = TIER_TABLES[tier]
            sql = f"""
                SELECT
                    toString(ts) AS timestamp,
                    avgMerge(speed_avg_state) AS speed,
                    sumMerge(count_sum_state) / {{n_ch:Float64}} AS flow,
                    uniqExact(ch) / {{n_ch:Float64}} AS occupancy
                FROM {table}
                WHERE fiber_id = {{fid:String}}
                  AND direction = {{dir:UInt8}}
                  AND ch BETWEEN {{cs:UInt32}} AND {{ce:UInt32}}
                  AND ts >= {{start:DateTime64(3)}}
                  AND ts <= {{end:DateTime64(3)}}
                GROUP BY ts
                ORDER BY ts
            """

        data = query(
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

        return Response(
            {
                "data": data,
                "meta": {"section_id": section_id, "tier": tier},
            }
        )
