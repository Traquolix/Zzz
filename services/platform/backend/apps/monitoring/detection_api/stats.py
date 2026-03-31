"""
Public stats endpoint.
"""

from django.db.models import Sum
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.fibers.models import FiberCable
from apps.fibers.utils import get_org_fiber_ids
from apps.monitoring.detection_serializers import PublicStatsResponseSerializer
from apps.monitoring.detection_utils import TIER_TABLES
from apps.shared.clickhouse import clickhouse_fallback, query_scalar
from apps.shared.constants import CH_INCIDENTS

from .auth import IsAPIKeyUser, PublicAPIThrottle


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
    def get(self, request: Request) -> Response:
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

        fiber_qs = FiberCable.objects.filter(id__in=fiber_ids)
        fiber_count = fiber_qs.count()
        total_channels = fiber_qs.aggregate(total=Sum("channel_count"))["total"] or 0

        active_incidents = (
            query_scalar(
                f"SELECT count() FROM {CH_INCIDENTS} FINAL "
                "WHERE status = 'active' AND fiber_id IN {fids:Array(String)}",
                parameters={"fids": fiber_ids},
            )
            or 0
        )

        recent_rows = (
            query_scalar(
                f"SELECT count() / 10 FROM {TIER_TABLES['hires']} "
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
