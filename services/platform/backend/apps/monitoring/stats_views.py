"""
Stats and infrastructure list views.

All queries are org-scoped via fiber assignments / Organization FK.
"""

import logging
import time

from django.core.cache import cache as django_cache
from django.db.models import Count, Sum
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.fibers.models import FiberCable
from apps.monitoring.detection_utils import CH_INCIDENTS, TIER_TABLES
from apps.monitoring.mixins import FlowAwareMixin
from apps.monitoring.models import Infrastructure
from apps.monitoring.serializers import InfrastructureSerializer, StatsSerializer
from apps.monitoring.view_helpers import (
    _PROCESS_START_TIME,
    STATS_CACHE_TTL,
    _get_fiber_ids_or_none,
)
from apps.shared.clickhouse import clickhouse_fallback, query_scalar
from apps.shared.permissions import IsActiveUser
from apps.shared.utils import build_org_cache_key

logger = logging.getLogger("sequoia.monitoring.views")


class StatsView(FlowAwareMixin, APIView):
    """
    GET /api/stats — system-level statistics.

    Strict flow isolation:
    - ``flow=sim`` → stats derived from simulation caches
    - ``flow=live`` → stats from ClickHouse (503 if unavailable)

    Org-scoped: counts only fibers/channels/incidents/detections from
    the user's assigned fibers.
    """

    permission_classes = [IsActiveUser]

    @extend_schema(
        responses={200: StatsSerializer},
        tags=["stats"],
    )
    @clickhouse_fallback()
    def get(self, request: Request) -> Response:
        flow = self._get_flow(request)
        cache_key = f"{build_org_cache_key('stats', request.user)}:{flow}"
        cached = django_cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        if self._is_sim(request):
            data = self._get_sim_stats(request)
        else:
            data = self._get_live_stats(request)

        django_cache.set(cache_key, data, STATS_CACHE_TTL)
        return Response(data)

    def _get_sim_stats(self, request: Request) -> dict:
        """Sim flow: derive stats from simulation caches."""
        from apps.shared.simulation_cache import get_simulation_incidents, get_simulation_stats

        sim_incidents = self._get_sim_data(request, get_simulation_incidents)
        active_incidents = sum(1 for i in sim_incidents if i.get("status") == "active")
        stats = get_simulation_stats()

        return {
            "fiberCount": stats.get("fiber_count", 0),
            "totalChannels": stats.get("total_channels", 0),
            "activeVehicles": stats.get("active_vehicles", 0),
            "detectionsPerSecond": 0,
            "activeIncidents": active_incidents,
            "systemUptime": int(time.time() - _PROCESS_START_TIME),
        }

    def _get_live_stats(self, request: Request) -> dict:
        """Live flow: query ClickHouse for real stats."""
        fiber_ids = _get_fiber_ids_or_none(request.user)

        if fiber_ids is not None:
            if not fiber_ids:
                fiber_count = 0
                total_channels = 0
                active_incidents = 0
                recent_rows = 0
                active_vehicles = 0
            else:
                agg = FiberCable.objects.filter(id__in=fiber_ids).aggregate(
                    fiber_count=Count("id"),
                    total_channels=Sum("channel_count"),
                )
                fiber_count = agg["fiber_count"]
                total_channels = agg["total_channels"] or 0

                active_incidents = (
                    query_scalar(
                        f"SELECT count() FROM {CH_INCIDENTS} FINAL WHERE status = 'active' AND fiber_id IN {{fids:Array(String)}}",
                        parameters={"fids": fiber_ids},
                    )
                    or 0
                )

                recent_rows = (
                    query_scalar(
                        f"""
                    SELECT count() / 10
                    FROM {TIER_TABLES["hires"]}
                    WHERE ts >= now() - INTERVAL 10 SECOND
                      AND fiber_id IN {{fids:Array(String)}}
                    """,
                        parameters={"fids": fiber_ids},
                    )
                    or 0
                )

                active_vehicles = (
                    query_scalar(
                        f"""
                    SELECT coalesce(sum(vehicle_count), 0)
                    FROM {TIER_TABLES["hires"]}
                    WHERE ts >= (now() - toIntervalSecond(30))
                      AND fiber_id IN {{fids:Array(String)}}
                    """,
                        parameters={"fids": fiber_ids},
                    )
                    or 0
                )
        else:
            fiber_count = FiberCable.objects.count()
            total_channels = FiberCable.objects.aggregate(total=Sum("channel_count"))["total"] or 0

            active_incidents = (
                query_scalar(f"SELECT count() FROM {CH_INCIDENTS} FINAL WHERE status = 'active'")
                or 0
            )

            recent_rows = (
                query_scalar(f"""
                SELECT count() / 10
                FROM {TIER_TABLES["hires"]}
                WHERE ts >= now() - INTERVAL 10 SECOND
            """)
                or 0
            )

            active_vehicles = (
                query_scalar(f"""
                SELECT coalesce(sum(vehicle_count), 0)
                FROM {TIER_TABLES["hires"]}
                WHERE ts >= (now() - toIntervalSecond(30))
            """)
                or 0
            )

        return {
            "fiberCount": fiber_count,
            "totalChannels": total_channels,
            "activeVehicles": int(active_vehicles),
            "detectionsPerSecond": round(float(recent_rows), 1),
            "activeIncidents": active_incidents,
            "systemUptime": int(time.time() - _PROCESS_START_TIME),
        }


class InfrastructureListView(APIView):
    """
    GET /api/infrastructure — returns infrastructure items from PostgreSQL.

    Already org-scoped via Organization FK.
    No query parameters are accepted, so the pattern is safe.
    """

    permission_classes = [IsActiveUser]

    @extend_schema(
        responses={200: InfrastructureSerializer(many=True)},
        tags=["infrastructure"],
    )
    def get(self, request: Request) -> Response:
        if request.user.is_superuser:
            qs = Infrastructure.objects.all()
        elif hasattr(request.user, "organization") and request.user.organization:
            qs = Infrastructure.objects.filter(organization=request.user.organization)
        else:
            # Non-superuser without org — no access
            return Response({"results": [], "hasMore": False, "limit": 0})

        data = []
        for item in qs:
            image_url = None
            if item.image:
                image_url = f"/infrastructure/{item.image}"
            data.append(
                {
                    "id": item.id,
                    "type": item.type,
                    "name": item.name,
                    "fiberId": item.fiber_id,
                    "direction": item.direction,
                    "startChannel": item.start_channel,
                    "endChannel": item.end_channel,
                    "imageUrl": image_url,
                }
            )
        return Response({"results": data, "hasMore": False, "limit": len(data)})
