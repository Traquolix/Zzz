"""
Monitoring views — incidents (ClickHouse), infrastructure (PostgreSQL), stats, SHM spectra.

All ClickHouse queries are org-scoped via FiberAssignment: non-superusers
only see data from fibers assigned to their organization.
"""

import contextlib
import logging
import time
from typing import Any

from django.core.cache import cache as django_cache
from django.db import IntegrityError
from django.db.models import Count, Sum
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ParseError
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.fibers.models import FiberCable
from apps.fibers.utils import fiber_belongs_to_org, get_org_fiber_ids
from apps.monitoring.incident_service import (
    query_by_id as incident_query_by_id,
)
from apps.monitoring.incident_service import (
    query_recent as incident_query_recent,
)
from apps.monitoring.mixins import FlowAwareMixin
from apps.monitoring.models import IncidentAction, Infrastructure, Section
from apps.monitoring.section_service import (
    delete_section,
    get_section,
    insert_section,
    query_batch_section_history,
    query_section_history,
    query_sections,
)
from apps.monitoring.serializers import (
    IncidentActionInputSerializer,
    IncidentActionSerializer,
    IncidentSerializer,
    IncidentSnapshotSerializer,
    InfrastructureSerializer,
    SectionHistorySerializer,
    SectionInputSerializer,
    SectionSerializer,
    SpectralDataSerializer,
    SpectralPeaksSerializer,
    StatsSerializer,
)
from apps.monitoring.workflow import (
    InvalidTransitionError,
    get_current_status,
    validate_transition,
)
from apps.shared.clickhouse import clickhouse_fallback, query, query_scalar
from apps.shared.exceptions import ClickHouseUnavailableError
from apps.shared.permissions import IsActiveUser, IsNotViewer
from apps.shared.utils import build_org_cache_key

logger = logging.getLogger("sequoia")

_PROCESS_START_TIME = time.time()

INCIDENTS_CACHE_TTL = 10  # 10 seconds
STATS_CACHE_TTL = 5  # 5 seconds
# Keep in sync with frontend: services/platform/frontend/src/api/sections.ts
MAX_SECTIONS_PER_ORG = 50


def _get_fiber_ids_or_none(user: Any) -> list[str] | None:
    """Return fiber_ids list for org-scoped users, None for superusers."""
    if user.is_superuser:
        return None
    return get_org_fiber_ids(user.organization)


def _verify_infrastructure_access(user: Any, infrastructure_id: str | None) -> Response | None:
    """Verify the user's org owns the infrastructure. Returns error Response or None."""
    if not infrastructure_id or user.is_superuser:
        return None
    if not Infrastructure.objects.filter(
        id=infrastructure_id,
        organization=user.organization,
    ).exists():
        return Response(
            {"detail": "Infrastructure not found", "code": "not_found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    return None


class IncidentListView(FlowAwareMixin, APIView):
    """
    GET /api/incidents — returns active + recent incidents.

    Strict flow isolation:
    - ``flow=sim`` → simulation cache only (never ClickHouse)
    - ``flow=live`` → ClickHouse only (503 if unavailable, never sim)

    Org-scoped: only incidents from the user's assigned fibers.
    """

    permission_classes = [IsActiveUser]

    @extend_schema(
        responses={200: IncidentSerializer(many=True)},
        tags=["incidents"],
    )
    def get(self, request: Request) -> Response:
        try:
            limit = min(int(request.query_params.get("limit", 100)), 500)
        except (ValueError, TypeError):
            limit = 100

        flow = self._get_flow(request)
        cache_key = f"{build_org_cache_key('incidents', request.user)}:{flow}:{limit}"
        cached = django_cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        fiber_ids = _get_fiber_ids_or_none(request.user)
        if fiber_ids is not None and not fiber_ids:
            result = {"results": [], "hasMore": False, "limit": limit}
            django_cache.set(cache_key, result, INCIDENTS_CACHE_TTL)
            return Response(result)

        if self._is_sim(request):
            return self._get_sim_incidents(request, cache_key, limit)

        return self._get_live_incidents(request, cache_key, limit, fiber_ids)

    def _get_sim_incidents(self, request: Request, cache_key: str, limit: int) -> Response:
        """Sim flow: return incidents from simulation cache only."""
        from apps.realtime.simulation import get_simulation_incidents

        sim_incidents = self._get_sim_data(request, get_simulation_incidents)
        page = sim_incidents[:limit]
        result = {
            "results": page,
            "hasMore": len(sim_incidents) > limit,
            "limit": limit,
        }
        django_cache.set(cache_key, result, INCIDENTS_CACHE_TTL)
        return Response(result)

    def _get_live_incidents(
        self, request: Request, cache_key: str, limit: int, fiber_ids: list[str] | None
    ) -> Response:
        """Live flow: return incidents from ClickHouse only."""
        try:
            incidents = incident_query_recent(fiber_ids=fiber_ids, hours=24, limit=limit + 1)
        except ClickHouseUnavailableError:
            return Response(
                {"detail": "ClickHouse unavailable", "code": "clickhouse_unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        has_more = len(incidents) > limit
        page = incidents[:limit]
        result = {
            "results": page,
            "hasMore": has_more,
            "limit": limit,
        }
        django_cache.set(cache_key, result, INCIDENTS_CACHE_TTL)
        return Response(result)


class IncidentSnapshotView(FlowAwareMixin, APIView):
    """
    GET /api/incidents/<id>/snapshot — high-res speed data around an incident.

    Strict flow isolation:
    - ``flow=sim`` → simulation snapshot cache only
    - ``flow=live`` → ClickHouse only (503 if unavailable)

    Org-scoped: verifies the incident's fiber belongs to the user's org.
    """

    permission_classes = [IsActiveUser]

    @extend_schema(
        responses={200: IncidentSnapshotSerializer},
        tags=["incidents"],
    )
    def get(self, request: Request, incident_id: str) -> Response:
        if self._is_sim(request):
            return self._get_sim_snapshot(request, incident_id)

        return self._get_live_snapshot(request, incident_id)

    def _get_sim_snapshot(self, request: Request, incident_id: str) -> Response:
        """Sim flow: return snapshot from simulation cache only."""
        from apps.realtime.simulation import get_simulation_incidents, get_simulation_snapshot

        sim_incidents = get_simulation_incidents()
        sim_incident = next((i for i in sim_incidents if i["id"] == incident_id), None)
        if sim_incident is None:
            raise NotFound({"detail": "Incident not found", "code": "incident_not_found"})

        # Org-scoping: verify fiber belongs to user's org
        fiber_ids = _get_fiber_ids_or_none(request.user)
        if fiber_ids is not None and not fiber_belongs_to_org(sim_incident["fiberId"], fiber_ids):
            raise NotFound({"detail": "Incident not found", "code": "incident_not_found"})

        snapshot = get_simulation_snapshot(incident_id)
        points = snapshot["points"] if snapshot else []
        complete = snapshot["complete"] if snapshot else True

        return Response(
            {
                "incidentId": incident_id,
                "fiberId": sim_incident["fiberId"],
                "direction": sim_incident["direction"],
                "centerChannel": sim_incident["channel"],
                "capturedAt": int(time.time() * 1000),
                "points": points,
                "complete": complete,
            }
        )

    def _get_live_snapshot(self, request: Request, incident_id: str) -> Response:
        """Live flow: return snapshot from ClickHouse only."""
        try:
            incident_rows = query(
                """
                SELECT fiber_id, direction, channel_start, channel_end, timestamp_ns
                FROM sequoia.fiber_incidents
                FINAL
                WHERE incident_id = {id:String}
                LIMIT 1
                """,
                parameters={"id": incident_id},
            )
        except ClickHouseUnavailableError:
            return Response(
                {"detail": "ClickHouse unavailable", "code": "clickhouse_unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if not incident_rows:
            raise NotFound({"detail": "Incident not found", "code": "incident_not_found"})

        incident = incident_rows[0]
        fiber_id = incident["fiber_id"]
        direction = incident["direction"]

        # Org-scoping: verify the incident's fiber belongs to user's org
        fiber_ids = _get_fiber_ids_or_none(request.user)
        if fiber_ids is not None and not fiber_belongs_to_org(fiber_id, fiber_ids):
            raise NotFound({"detail": "Incident not found", "code": "incident_not_found"})

        center_ch = (incident["channel_start"] + incident["channel_end"]) // 2
        ts_ns = incident["timestamp_ns"]

        # Aggregate into 1-second buckets server-side
        window_start_ns = ts_ns - 60_000_000_000
        window_end_ns = ts_ns + 60_000_000_000
        try:
            agg_rows = query(
                """
                SELECT
                    toUnixTimestamp64Milli(
                        toStartOfInterval(ts, INTERVAL 1 second)
                    ) AS bucket_ms,
                    avg(abs(speed)) AS avg_speed,
                    sum(vehicle_count) AS total_count
                FROM sequoia.detection_hires
                WHERE fiber_id = {fid:String}
                  AND direction = {dir:UInt8}
                  AND ch BETWEEN {ch_min:UInt16} AND {ch_max:UInt16}
                  AND ts BETWEEN fromUnixTimestamp64Nano({ts_start:UInt64})
                              AND fromUnixTimestamp64Nano({ts_end:UInt64})
                GROUP BY bucket_ms
                ORDER BY bucket_ms
                """,
                parameters={
                    "fid": fiber_id,
                    "dir": direction,
                    "ch_min": max(0, center_ch - 50),
                    "ch_max": center_ch + 50,
                    "ts_start": window_start_ns,
                    "ts_end": window_end_ns,
                },
            )
        except ClickHouseUnavailableError:
            return Response(
                {"detail": "ClickHouse unavailable", "code": "clickhouse_unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # Build lookup from aggregated rows
        avg_vehicle_length_m = 6
        bucket_lookup = {}
        for row in agg_rows:
            avg_spd = round(row["avg_speed"])
            flow_count = int(row["total_count"])
            speed_ms = avg_spd * (1000 / 3600)
            occ = (
                min(100, round((flow_count * 3600 * avg_vehicle_length_m) / (speed_ms * 1000)))
                if speed_ms > 0
                else None
            )
            bucket_lookup[int(row["bucket_ms"])] = {
                "speed": avg_spd,
                "flow": flow_count,
                "occupancy": occ,
            }

        # Fill all 120 second slots
        window_start_ms = ts_ns // 1_000_000 - 60_000
        points = []
        for s in range(120):
            t = window_start_ms + s * 1000
            if t in bucket_lookup:
                points.append({"time": t, **bucket_lookup[t]})
            else:
                points.append({"time": t, "speed": None, "flow": None, "occupancy": None})

        return Response(
            {
                "incidentId": incident_id,
                "fiberId": fiber_id,
                "direction": incident.get("direction", 0),
                "centerChannel": center_ch,
                "capturedAt": int(time.time() * 1000),
                "points": points,
                "complete": True,
            }
        )


class IncidentActionView(FlowAwareMixin, APIView):
    """
    GET  /api/incidents/<id>/actions — action history for an incident.
    POST /api/incidents/<id>/actions — record a workflow transition.

    Org-scoped: verifies the incident's fiber belongs to the user's org.
    POST requires non-viewer role (API keys are viewer-only).
    Live flow only — sim incidents are ephemeral and don't support workflow actions.
    """

    def get_permissions(self) -> list[BasePermission]:
        perms: list[BasePermission] = [IsActiveUser()]
        if self.request.method == "POST":
            perms.append(IsNotViewer())
        return perms

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        if self._is_sim(request):
            raise ParseError("Workflow actions are not supported for simulated incidents")

    def _get_incident_or_404(
        self, incident_id: str, request: Request
    ) -> tuple[dict | None, Response | None]:
        """Fetch incident from ClickHouse and verify org access."""
        try:
            incident = incident_query_by_id(incident_id)
        except ClickHouseUnavailableError:
            return None, Response(
                {"detail": "ClickHouse unavailable", "code": "clickhouse_unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if not incident:
            return None, Response(
                {"detail": "Incident not found", "code": "incident_not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Org-scoping
        fiber_ids = _get_fiber_ids_or_none(request.user)
        if fiber_ids is not None and not fiber_belongs_to_org(incident["fiber_id"], fiber_ids):
            return None, Response(
                {"detail": "Incident not found", "code": "incident_not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return incident, None

    @extend_schema(
        responses={200: IncidentActionSerializer(many=True)},
        tags=["incidents"],
    )
    def get(self, request: Request, incident_id: str) -> Response:
        incident, error_resp = self._get_incident_or_404(incident_id, request)
        if error_resp:
            return error_resp

        actions = IncidentAction.objects.filter(incident_id=incident_id).select_related(
            "performed_by"
        )

        current_status = get_current_status(incident_id)

        return Response(
            {
                "currentStatus": current_status,
                "actions": IncidentActionSerializer(actions, many=True).data,
            }
        )

    @extend_schema(
        request=IncidentActionInputSerializer,
        responses={201: IncidentActionSerializer},
        tags=["incidents"],
    )
    def post(self, request: Request, incident_id: str) -> Response:
        from django.db import transaction

        input_serializer = IncidentActionInputSerializer(data=request.data)
        if not input_serializer.is_valid():
            return Response(
                {
                    "detail": "Invalid input",
                    "code": "validation_error",
                    "errors": input_serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        incident, error_resp = self._get_incident_or_404(incident_id, request)
        if error_resp:
            return error_resp

        target_status = input_serializer.validated_data["action"]

        # Atomic block prevents TOCTOU race: lock the latest action row
        # so concurrent transitions are serialized.
        with transaction.atomic():
            latest = (
                IncidentAction.objects.select_for_update()
                .filter(incident_id=incident_id)
                .order_by("-performed_at")
                .first()
            )
            current_status = latest.to_status if latest else "active"

            try:
                validate_transition(current_status, target_status)
            except InvalidTransitionError:
                return Response(
                    {
                        "detail": f"Cannot transition from {current_status!r} to {target_status!r}",
                        "code": "invalid_transition",
                        "currentStatus": current_status,
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            action = IncidentAction.objects.create(
                incident_id=incident_id,
                from_status=current_status,
                to_status=target_status,
                performed_by=request.user,
                note=input_serializer.validated_data.get("note", ""),
            )

        return Response(
            IncidentActionSerializer(action).data,
            status=status.HTTP_201_CREATED,
        )


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
        from apps.realtime.simulation import get_simulation_incidents, get_simulation_stats

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
                        "SELECT count() FROM sequoia.fiber_incidents FINAL WHERE status = 'active' AND fiber_id IN {fids:Array(String)}",
                        parameters={"fids": fiber_ids},
                    )
                    or 0
                )

                recent_rows = (
                    query_scalar(
                        """
                    SELECT count() / 10
                    FROM sequoia.detection_hires
                    WHERE ts >= now() - INTERVAL 10 SECOND
                      AND fiber_id IN {fids:Array(String)}
                    """,
                        parameters={"fids": fiber_ids},
                    )
                    or 0
                )

                active_vehicles = (
                    query_scalar(
                        """
                    SELECT coalesce(sum(vehicle_count), 0)
                    FROM sequoia.detection_hires
                    WHERE ts >= (now() - toIntervalSecond(30))
                      AND fiber_id IN {fids:Array(String)}
                    """,
                        parameters={"fids": fiber_ids},
                    )
                    or 0
                )
        else:
            fiber_count = FiberCable.objects.count()
            total_channels = FiberCable.objects.aggregate(total=Sum("channel_count"))["total"] or 0

            active_incidents = (
                query_scalar(
                    "SELECT count() FROM sequoia.fiber_incidents FINAL WHERE status = 'active'"
                )
                or 0
            )

            recent_rows = (
                query_scalar("""
                SELECT count() / 10
                FROM sequoia.detection_hires
                WHERE ts >= now() - INTERVAL 10 SECOND
            """)
                or 0
            )

            active_vehicles = (
                query_scalar("""
                SELECT coalesce(sum(vehicle_count), 0)
                FROM sequoia.detection_hires
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


class SectionListView(APIView):
    """
    GET  /api/sections — list active monitored sections.
    POST /api/sections — create a new monitored section (requires non-viewer role).

    Org-scoped via Section.organization FK.
    """

    permission_classes = [IsActiveUser]

    def get_permissions(self) -> list[BasePermission]:
        perms: list[BasePermission] = [IsActiveUser()]
        if self.request.method == "POST":
            perms.append(IsNotViewer())
        return perms

    @extend_schema(
        responses={200: SectionSerializer(many=True)},
        tags=["sections"],
    )
    def get(self, request: Request) -> Response:
        org_id = None if request.user.is_superuser else request.user.organization_id
        sections = query_sections(organization_id=org_id)
        return Response({"results": sections})

    @extend_schema(
        request=SectionInputSerializer,
        responses={201: SectionSerializer},
        tags=["sections"],
    )
    def post(self, request: Request) -> Response:
        serializer = SectionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        fiber_id = serializer.validated_data["fiberId"]
        direction = serializer.validated_data["direction"]
        name = serializer.validated_data["name"]
        channel_start = serializer.validated_data["channelStart"]
        channel_end = serializer.validated_data["channelEnd"]

        if request.user.organization_id is None:
            return Response(
                {"detail": "Cannot create sections without an organization"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Enforce per-org section limit
        org_count = Section.objects.filter(
            organization_id=request.user.organization_id, is_active=True
        ).count()
        if org_count >= MAX_SECTIONS_PER_ORG:
            return Response(
                {
                    "detail": f"Section limit reached ({MAX_SECTIONS_PER_ORG} per organization)",
                    "code": "limit_reached",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Org-scoping: verify the fiber belongs to user's org
        fiber_ids = _get_fiber_ids_or_none(request.user)
        if fiber_ids is not None and not fiber_belongs_to_org(fiber_id, fiber_ids):
            return Response(
                {"detail": "Fiber not found", "code": "not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            section = insert_section(
                fiber_id=fiber_id,
                name=name,
                channel_start=channel_start,
                channel_end=channel_end,
                direction=direction,
                organization_id=request.user.organization_id,
                user_id=request.user.id,
            )
        except IntegrityError:
            return Response(
                {"detail": "A section with this range already exists", "code": "duplicate"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(section, status=status.HTTP_201_CREATED)


class SectionDeleteView(APIView):
    """
    DELETE /api/sections/<id> — delete a monitored section.

    Org-scoped via Section.organization FK. Requires non-viewer role.
    """

    permission_classes = [IsActiveUser, IsNotViewer]

    def delete(self, request: Request, section_id: str) -> Response:
        org_id = None if request.user.is_superuser else request.user.organization_id
        if not delete_section(section_id, organization_id=org_id):
            return Response(
                {"detail": "Section not found", "code": "not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class SectionHistoryView(FlowAwareMixin, APIView):
    """
    GET /api/sections/<id>/history?minutes=60 — speed time-series for a section.

    Strict flow isolation:
    - ``flow=sim`` → in-memory simulation buffers (per-second ≤5min, per-minute >5min)
    - ``flow=live`` → ClickHouse (``detection_hires`` ≤5min, ``detection_1m`` >5min)

    Org-scoped via Section.organization FK.
    """

    permission_classes = [IsActiveUser]

    @extend_schema(
        responses={200: SectionHistorySerializer},
        parameters=[
            OpenApiParameter(
                name="minutes", type=int, description="History window in minutes (max 1440)"
            ),
            OpenApiParameter(
                name="since",
                type=int,
                description="Only return points after this timestamp (ms epoch). "
                "Used for incremental polling.",
                required=False,
            ),
        ],
        tags=["sections"],
    )
    @clickhouse_fallback()
    def get(self, request: Request, section_id: str) -> Response:
        try:
            minutes = min(int(request.query_params.get("minutes", 60)), 1440)
        except (ValueError, TypeError):
            minutes = 60

        # Parse optional since parameter for incremental polling
        since_raw = request.query_params.get("since")
        since_ms: int | None = None
        if since_raw is not None:
            with contextlib.suppress(ValueError, TypeError):
                since_ms = int(since_raw)
        if since_ms is not None and since_ms < 0:
            since_ms = None

        # Sim flow: cap at 60 min (buffer limit)
        if self._is_sim(request):
            minutes = min(minutes, 60)

        org_id = None if request.user.is_superuser else request.user.organization_id
        section = get_section(section_id, organization_id=org_id)
        if not section:
            return Response(
                {"detail": "Section not found", "code": "not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if self._is_sim(request):
            history = self._get_sim_history(section, minutes, since_ms)
        else:
            history = query_section_history(
                fiber_id=section["fiberId"],
                direction=section["direction"],
                channel_start=section["channelStart"],
                channel_end=section["channelEnd"],
                minutes=minutes,
                since_ms=since_ms,
            )

        return Response(
            {
                "sectionId": section_id,
                "minutes": minutes,
                "points": history,
            }
        )

    def _get_sim_history(
        self, section: dict, minutes: int, since_ms: int | None = None
    ) -> list[dict]:
        """Sim flow: query in-memory simulation detection buffers."""
        from apps.realtime.simulation import get_simulation_section_history

        return get_simulation_section_history(
            fiber_id=section["fiberId"],
            direction=section["direction"],
            channel_start=section["channelStart"],
            channel_end=section["channelEnd"],
            minutes=minutes,
            since_ms=since_ms,
        )


class BatchSectionHistoryView(FlowAwareMixin, APIView):
    """
    POST /api/sections/batch-history — speed time-series for multiple sections.

    Replaces N parallel GET /api/sections/<id>/history calls with a single
    batch request. Used by the live stats poller (useLiveStats) which needs
    history for all sections every 2 seconds.

    Request body: ``{"sectionIds": [...], "minutes": 1, "since": {"id1": ms, "id2": ms}}``

    Strict flow isolation:
    - ``flow=sim`` → in-memory simulation buffers
    - ``flow=live`` → ClickHouse

    Org-scoped: only returns data for sections belonging to the user's org.
    """

    permission_classes = [IsActiveUser]

    @clickhouse_fallback()
    def post(self, request: Request) -> Response:
        section_ids = request.data.get("sectionIds")
        if not isinstance(section_ids, list) or not section_ids:
            return Response(
                {"detail": "sectionIds must be a non-empty list", "code": "validation_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate each element is a string
        section_ids = [sid for sid in section_ids if isinstance(sid, str) and sid]
        if not section_ids:
            return Response(
                {
                    "detail": "sectionIds must contain at least one valid string",
                    "code": "validation_error",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(section_ids) > MAX_SECTIONS_PER_ORG:
            return Response(
                {
                    "detail": f"Too many sections: {len(section_ids)} requested, "
                    f"max {MAX_SECTIONS_PER_ORG} per request",
                    "code": "validation_error",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            minutes = min(int(request.data.get("minutes", 60)), 1440)
        except (ValueError, TypeError):
            minutes = 60

        # Per-section since cursors: {"section-abc": 1741234567000, ...}
        since_raw = request.data.get("since")
        since_map: dict[str, int] | None = None
        if isinstance(since_raw, dict):
            since_map = {}
            for k, v in since_raw.items():
                try:
                    val = int(v)
                    if val >= 0:
                        since_map[str(k)] = val
                except (ValueError, TypeError):
                    pass

        if self._is_sim(request):
            minutes = min(minutes, 60)

        # Fetch sections from DB, org-scoped (cached — sections rarely change)
        org_id = None if request.user.is_superuser else request.user.organization_id
        cache_key = build_org_cache_key("batch_sections", request.user)
        sections = django_cache.get(cache_key)
        if sections is None:
            sections = query_sections(organization_id=org_id)
            django_cache.set(cache_key, sections, 30)

        # Filter to requested IDs only
        sections_by_id = {s["id"]: s for s in sections}
        requested = [sections_by_id[sid] for sid in section_ids if sid in sections_by_id]

        if not requested:
            return Response({"results": {}})

        if self._is_sim(request):
            results = self._get_sim_batch(requested, minutes, since_map)
        else:
            results = query_batch_section_history(requested, minutes, since_map)

        return Response({"results": results})

    def _get_sim_batch(
        self, sections: list[dict], minutes: int, since_map: dict[str, int] | None
    ) -> dict[str, list[dict]]:
        """Sim flow: query in-memory simulation detection buffers for each section."""
        from apps.realtime.simulation import get_simulation_section_history

        result: dict[str, list[dict]] = {}
        for sec in sections:
            since_ms = (since_map or {}).get(sec["id"])
            result[sec["id"]] = get_simulation_section_history(
                fiber_id=sec["fiberId"],
                direction=sec["direction"],
                channel_start=sec["channelStart"],
                channel_end=sec["channelEnd"],
                minutes=minutes,
                since_ms=since_ms,
            )
        return result


class SpectralDataView(APIView):
    """
    GET /api/shm/spectra — returns spectral data for SHM heatmap visualization.

    Query parameters:
    - infrastructureId: Infrastructure ID (optional, for production real-time data)
    - maxTimeSamples: Maximum number of time samples to return (default 500)
    - maxFreqBins: Maximum number of frequency bins to return (default 200)
    - startIdx: Starting time index for slicing (optional)
    - endIdx: Ending time index for slicing (optional)
    - startTime: ISO timestamp for start of time range (optional)
    - endTime: ISO timestamp for end of time range (optional)

    In demo mode (no infrastructureId), returns sample data from HDF5 file.
    In production mode, will fetch real-time data for the specified infrastructure.
    """

    permission_classes = [IsActiveUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="infrastructureId",
                type=str,
                description="Infrastructure ID for real-time data",
            ),
            OpenApiParameter(name="maxTimeSamples", type=int, description="Max time samples"),
            OpenApiParameter(name="maxFreqBins", type=int, description="Max frequency bins"),
            OpenApiParameter(name="startIdx", type=int, description="Start time index"),
            OpenApiParameter(name="endIdx", type=int, description="End time index"),
            OpenApiParameter(name="startTime", type=str, description="Start time (ISO format)"),
            OpenApiParameter(name="endTime", type=str, description="End time (ISO format)"),
        ],
        responses={200: SpectralDataSerializer},
        tags=["shm"],
    )
    def get(self, request: Request) -> Response:
        from datetime import datetime

        import numpy as np

        from apps.monitoring.hdf5_reader import load_spectral_data, sample_file_exists

        # Org-scoping: validate infrastructure access if specified
        error_resp = _verify_infrastructure_access(
            request.user,
            request.query_params.get("infrastructureId"),
        )
        if error_resp:
            return error_resp

        # Demo mode: return sample data from HDF5 file
        if not sample_file_exists():
            return Response(
                {"detail": "No SHM sample data available", "code": "shm_data_unavailable"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            data = load_spectral_data()
        except Exception as e:
            logger.error("Failed to load spectral data: %s", e)
            return Response(
                {"detail": "Failed to load spectral data", "code": "shm_load_error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Apply time filtering if startTime/endTime provided (takes priority over indices)
        start_time_str = request.query_params.get("startTime")
        end_time_str = request.query_params.get("endTime")

        if start_time_str or end_time_str:
            # Calculate absolute timestamps for all samples
            timestamps = data.t0.timestamp() + data.dt

            # Parse filter times
            start_ts = (
                datetime.fromisoformat(start_time_str.replace("Z", "+00:00")).timestamp()
                if start_time_str
                else 0
            )
            end_ts = (
                datetime.fromisoformat(end_time_str.replace("Z", "+00:00")).timestamp()
                if end_time_str
                else float("inf")
            )

            # Find indices within the time range
            mask = (timestamps >= start_ts) & (timestamps <= end_ts)
            indices = np.where(mask)[0]

            if len(indices) > 0:
                start_idx = int(indices[0])
                end_idx = int(indices[-1]) + 1
                data = data.slice_time(start_idx, end_idx)
        else:
            # Apply index-based time slicing if requested
            start_idx = request.query_params.get("startIdx")
            end_idx = request.query_params.get("endIdx")
            if start_idx is not None or end_idx is not None:
                start = int(start_idx) if start_idx else 0
                end = int(end_idx) if end_idx else data.num_time_samples
                data = data.slice_time(start, end)

        # Apply downsampling (clamped to prevent unbounded allocation)
        max_time = min(int(request.query_params.get("maxTimeSamples", 500)), 5000)
        max_freq = min(int(request.query_params.get("maxFreqBins", 200)), 2000)

        data = data.downsample_time(max_time)
        data = data.downsample_freq(max_freq)

        return Response(data.to_dict(log_scale=True))


class SpectralPeaksView(APIView):
    """
    GET /api/shm/peaks — returns peak frequencies over time for scatter plot.

    Query parameters:
    - infrastructureId: Infrastructure ID (optional, for production real-time data)
    - maxSamples: Maximum number of time samples to return (optional, cap 10000)
    - startTime: ISO timestamp for start of time range (optional)
    - endTime: ISO timestamp for end of time range (optional)

    In demo mode (no infrastructureId), returns sample data from HDF5 file.
    In production mode, will fetch real-time data for the specified infrastructure.
    """

    permission_classes = [IsActiveUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="infrastructureId",
                type=str,
                description="Infrastructure ID for real-time data",
            ),
            OpenApiParameter(name="maxSamples", type=int, description="Max samples"),
            OpenApiParameter(name="startTime", type=str, description="Start time (ISO format)"),
            OpenApiParameter(name="endTime", type=str, description="End time (ISO format)"),
        ],
        responses={200: SpectralPeaksSerializer},
        tags=["shm"],
    )
    def get(self, request: Request) -> Response:
        from datetime import datetime, timedelta

        import numpy as np

        from apps.monitoring.hdf5_reader import (
            load_peak_frequencies,
            load_spectral_data,
            sample_file_exists,
        )

        # Org-scoping: validate infrastructure access if specified
        error_resp = _verify_infrastructure_access(
            request.user,
            request.query_params.get("infrastructureId"),
        )
        if error_resp:
            return error_resp

        # Demo mode: return sample data from HDF5 file
        if not sample_file_exists():
            return Response(
                {"detail": "No SHM sample data available", "code": "shm_data_unavailable"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            data = load_spectral_data()
            # Use cached peak frequencies instead of recomputing find_peaks
            all_peak_freqs, all_peak_powers = load_peak_frequencies()
        except Exception as e:
            logger.error("Failed to load spectral data: %s", e)
            return Response(
                {"detail": "Failed to load spectral data", "code": "shm_load_error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Defensive copies: cached arrays are process-global and must not be
        # mutated in-place. Subsequent basic slices (e.g. arr[si:ei]) produce
        # views into these copies — safe because the copies isolate us from
        # the cache, and we do no in-place mutation after slicing.
        dt = data.dt.copy()
        peak_freqs = all_peak_freqs.copy()
        peak_powers = all_peak_powers.copy()
        t0 = data.t0

        # Apply time filtering. When no startTime/endTime and no maxSamples
        # are provided, default to the last day of available data so the
        # endpoint never returns the full unfiltered dataset by accident.
        start_time_str = request.query_params.get("startTime")
        end_time_str = request.query_params.get("endTime")
        max_samples_param = request.query_params.get("maxSamples")

        try:
            max_samples_int = int(max_samples_param) if max_samples_param is not None else None
        except (ValueError, TypeError):
            max_samples_int = None

        if (
            not start_time_str
            and not end_time_str
            and (max_samples_int is None or max_samples_int <= 0)
        ):
            # Use the file's own end time so this works for both live and
            # historical/demo data (where "today" may not overlap the file).
            last_offset = float(dt[-1])
            file_end = t0 + timedelta(seconds=last_offset)
            day_start = file_end.replace(hour=0, minute=0, second=0, microsecond=0)
            start_time_str = day_start.isoformat()
            end_time_str = (day_start + timedelta(days=1)).isoformat()

        if start_time_str or end_time_str:
            timestamps = t0.timestamp() + dt

            start_ts = (
                datetime.fromisoformat(start_time_str.replace("Z", "+00:00")).timestamp()
                if start_time_str
                else 0
            )
            end_ts = (
                datetime.fromisoformat(end_time_str.replace("Z", "+00:00")).timestamp()
                if end_time_str
                else float("inf")
            )

            mask = (timestamps >= start_ts) & (timestamps <= end_ts)
            idx = np.where(mask)[0]

            if len(idx) > 0:
                si, ei = int(idx[0]), int(idx[-1]) + 1
                start_offset = float(dt[si])
                dt = dt[si:ei] - dt[si]
                peak_freqs = peak_freqs[si:ei]
                peak_powers = peak_powers[si:ei]
                t0 = t0 + timedelta(seconds=start_offset)

        # Downsample by selecting evenly-spaced indices.
        # When the caller passes an explicit maxSamples we honour it (capped at 10 000).
        # Otherwise we skip downsampling — the time filter already bounds the result.
        max_samples = (
            min(max_samples_int, 10000)
            if max_samples_int is not None and max_samples_int > 0
            else 0
        )

        n = len(dt)
        if max_samples > 0 and max_samples < n:
            sel = np.linspace(0, n - 1, max_samples, dtype=int)
            dt = dt[sel]
            peak_freqs = peak_freqs[sel]
            peak_powers = peak_powers[sel]

        return Response(
            {
                "t0": t0.isoformat(),
                "dt": dt.tolist(),
                "peakFrequencies": peak_freqs.tolist(),
                "peakPowers": peak_powers.tolist(),
                "freqRange": list(data.freq_range),
            }
        )


class SpectralSummaryView(APIView):
    """
    GET /api/shm/summary — returns summary info about available spectral data.

    Query parameters:
    - infrastructureId: Infrastructure ID (optional, for production real-time data)

    Lightweight endpoint to check data availability without loading full dataset.
    """

    permission_classes = [IsActiveUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="infrastructureId",
                type=str,
                description="Infrastructure ID for real-time data",
            ),
        ],
        tags=["shm"],
    )
    def get(self, request: Request) -> Response:
        from apps.monitoring.hdf5_reader import get_spectral_summary, sample_file_exists

        # Org-scoping: validate infrastructure access if specified
        error_resp = _verify_infrastructure_access(
            request.user,
            request.query_params.get("infrastructureId"),
        )
        if error_resp:
            return error_resp

        if not sample_file_exists():
            return Response(
                {"detail": "No SHM sample data available", "code": "shm_data_unavailable"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            summary = get_spectral_summary()
        except Exception as e:
            logger.error("Failed to get spectral summary: %s", e)
            return Response(
                {"detail": "Failed to load spectral data", "code": "shm_load_error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(summary)


class SHMStatusView(APIView):
    """
    GET /api/monitoring/shm/status/<infrastructure_id> — compute live SHM status.

    Uses the SHM intelligence module to detect frequency shifts and classify
    deviation severity. For demo, generates plausible frequency data.
    """

    permission_classes = [IsActiveUser]

    @extend_schema(
        responses={200: dict},
        tags=["shm"],
    )
    def get(self, request: Request, infrastructure_id: str) -> Response:
        import random

        import numpy as np

        from apps.monitoring.shm_intelligence import (
            compute_baseline,
            detect_frequency_shift,
        )

        # Org-scoping: verify infrastructure belongs to user's org
        error_resp = _verify_infrastructure_access(request.user, infrastructure_id)
        if error_resp:
            return error_resp

        # Seed RNG with infrastructure_id for deterministic demo responses
        rng = random.Random(infrastructure_id)

        # Simulate baseline frequencies (would come from ClickHouse in production)
        baseline_freqs = np.array([1.10 + rng.gauss(0, 0.02) for _ in range(20)])
        baseline = compute_baseline(baseline_freqs)

        if baseline is None:
            return Response(
                {"detail": "Insufficient baseline data", "code": "insufficient_data"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Simulate current frequencies
        current_freqs = np.array([1.12 + rng.gauss(0, 0.03) for _ in range(10)])

        shift = detect_frequency_shift(baseline, current_freqs)

        # Map SHM classification to frontend status
        status_map = {
            "normal": "nominal",
            "warning": "warning",
            "alert": "warning",
            "critical": "critical",
        }

        return Response(
            {
                "status": status_map.get(shift.severity, "nominal"),
                "currentMean": round(shift.current_mean, 4),
                "baselineMean": round(shift.baseline_mean, 4),
                "deviationSigma": round(shift.deviation_sigma, 2),
                "direction": shift.direction,
                "severity": shift.severity,
            }
        )
