"""
Stats and infrastructure list views.

All queries are org-scoped via fiber assignments / Organization FK.
"""

import asyncio
import logging
import time

from asgiref.sync import sync_to_async
from django.core.cache import cache as django_cache
from django.db.models import Count, Sum
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.fibers.models import FiberCable
from apps.monitoring.detection_utils import TIER_TABLES
from apps.monitoring.mixins import FlowAwareMixin
from apps.monitoring.models import Infrastructure
from apps.monitoring.serializers import InfrastructureSerializer, StatsSerializer
from apps.monitoring.view_helpers import (
    _PROCESS_START_TIME,
    STATS_CACHE_TTL,
    _async_get_fiber_ids_or_none,
)
from apps.shared.clickhouse import async_query_scalar, clickhouse_fallback
from apps.shared.constants import CH_INCIDENTS
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
    async def get(self, request: Request) -> Response:
        flow = self._get_flow(request)
        cache_key = f"{build_org_cache_key('stats', request.user)}:{flow}"
        cached = await sync_to_async(django_cache.get)(cache_key)
        if cached is not None:
            return Response(cached)

        if self._is_sim(request):
            data = await self._async_get_sim_stats(request)
        else:
            data = await self._async_get_live_stats(request)

        await sync_to_async(django_cache.set)(cache_key, data, STATS_CACHE_TTL)
        return Response(data)

    async def _async_get_sim_stats(self, request: Request) -> dict:
        """Sim flow: derive stats from simulation caches."""
        from apps.shared.simulation_cache import get_simulation_incidents, get_simulation_stats

        sim_incidents = await self._async_get_sim_data(request, get_simulation_incidents)
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

    async def _async_get_live_stats(self, request: Request) -> dict:
        """Live flow: query ClickHouse for real stats (concurrent queries)."""
        fiber_ids = await _async_get_fiber_ids_or_none(request.user)

        if fiber_ids is not None:
            if not fiber_ids:
                return {
                    "fiberCount": 0,
                    "totalChannels": 0,
                    "activeVehicles": 0,
                    "detectionsPerSecond": 0,
                    "activeIncidents": 0,
                    "systemUptime": int(time.time() - _PROCESS_START_TIME),
                }

            # Run all 3 ClickHouse queries concurrently + ORM aggregation
            incidents_coro = async_query_scalar(
                f"SELECT count() FROM {CH_INCIDENTS} FINAL"
                " WHERE status = 'active' AND fiber_id IN {fids:Array(String)}",
                parameters={"fids": fiber_ids},
            )
            recent_coro = async_query_scalar(
                f"SELECT count() / 10 FROM {TIER_TABLES['hires']}"
                " WHERE ts >= now() - INTERVAL 10 SECOND"
                " AND fiber_id IN {fids:Array(String)}",
                parameters={"fids": fiber_ids},
            )
            vehicles_coro = async_query_scalar(
                f"SELECT coalesce(sum(vehicle_count), 0) FROM {TIER_TABLES['hires']}"
                " WHERE ts >= (now() - toIntervalSecond(30))"
                " AND fiber_id IN {fids:Array(String)}",
                parameters={"fids": fiber_ids},
            )
            orm_coro = sync_to_async(
                lambda: FiberCable.objects.filter(id__in=fiber_ids).aggregate(
                    fiber_count=Count("id"),
                    total_channels=Sum("channel_count"),
                )
            )()

            active_incidents, recent_rows, active_vehicles, agg = await asyncio.gather(
                incidents_coro, recent_coro, vehicles_coro, orm_coro
            )
            fiber_count = agg["fiber_count"]
            total_channels = agg["total_channels"] or 0
        else:
            # Superuser: unscoped queries
            incidents_coro = async_query_scalar(
                f"SELECT count() FROM {CH_INCIDENTS} FINAL WHERE status = 'active'"
            )
            recent_coro = async_query_scalar(
                f"SELECT count() / 10 FROM {TIER_TABLES['hires']}"
                " WHERE ts >= now() - INTERVAL 10 SECOND"
            )
            vehicles_coro = async_query_scalar(
                f"SELECT coalesce(sum(vehicle_count), 0) FROM {TIER_TABLES['hires']}"
                " WHERE ts >= (now() - toIntervalSecond(30))"
            )
            orm_count = sync_to_async(FiberCable.objects.count)()
            orm_total = sync_to_async(
                lambda: FiberCable.objects.aggregate(total=Sum("channel_count"))["total"] or 0
            )()

            (
                active_incidents,
                recent_rows,
                active_vehicles,
                fiber_count,
                total_channels,
            ) = await asyncio.gather(
                incidents_coro, recent_coro, vehicles_coro, orm_count, orm_total
            )

        return {
            "fiberCount": fiber_count,
            "totalChannels": total_channels,
            "activeVehicles": int(active_vehicles or 0),
            "detectionsPerSecond": round(float(recent_rows or 0), 1),
            "activeIncidents": active_incidents or 0,
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
