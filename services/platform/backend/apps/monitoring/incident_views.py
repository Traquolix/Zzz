"""
Incident views — list, snapshot, and workflow actions.

All ClickHouse queries are org-scoped via FiberAssignment: non-superusers
only see data from fibers assigned to their organization.
"""

import logging
import time
from typing import Any

from django.core.cache import cache as django_cache
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ParseError
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.fibers.utils import fiber_belongs_to_org
from apps.monitoring.detection_utils import CH_INCIDENTS, TIER_TABLES
from apps.monitoring.incident_service import (
    query_by_id as incident_query_by_id,
)
from apps.monitoring.incident_service import (
    query_recent as incident_query_recent,
)
from apps.monitoring.mixins import FlowAwareMixin
from apps.monitoring.models import IncidentAction
from apps.monitoring.serializers import (
    IncidentActionInputSerializer,
    IncidentActionSerializer,
    IncidentSerializer,
    IncidentSnapshotSerializer,
)
from apps.monitoring.view_helpers import INCIDENTS_CACHE_TTL, _get_fiber_ids_or_none
from apps.monitoring.workflow import (
    InvalidTransitionError,
    get_current_status,
    validate_transition,
)
from apps.shared.clickhouse import query
from apps.shared.exceptions import ClickHouseUnavailableError
from apps.shared.permissions import IsActiveUser, IsNotViewer
from apps.shared.utils import build_org_cache_key

logger = logging.getLogger("sequoia.monitoring.views")


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
        from apps.shared.simulation_cache import get_simulation_incidents

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
        from apps.shared.simulation_cache import get_simulation_incidents, get_simulation_snapshot

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
                f"""
                SELECT fiber_id, direction, channel_start, channel_end, timestamp_ns
                FROM {CH_INCIDENTS}
                FINAL
                WHERE incident_id = {{id:String}}
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
                f"""
                SELECT
                    toUnixTimestamp64Milli(
                        toStartOfInterval(ts, INTERVAL 1 second)
                    ) AS bucket_ms,
                    avg(abs(speed)) AS avg_speed,
                    sum(vehicle_count) AS total_count
                FROM {TIER_TABLES["hires"]}
                WHERE fiber_id = {{fid:String}}
                  AND direction = {{dir:UInt8}}
                  AND ch BETWEEN {{ch_min:UInt16}} AND {{ch_max:UInt16}}
                  AND ts BETWEEN fromUnixTimestamp64Nano({{ts_start:UInt64}})
                              AND fromUnixTimestamp64Nano({{ts_end:UInt64}})
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
        _incident, error_resp = self._get_incident_or_404(incident_id, request)
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

        _incident, error_resp = self._get_incident_or_404(incident_id, request)
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
