"""
Monitoring views — incidents (ClickHouse), infrastructure (PostgreSQL), stats, SHM spectra.

All ClickHouse queries are org-scoped via FiberAssignment: non-superusers
only see data from fibers assigned to their organization.
"""

import logging
import time

from django.core.cache import cache as django_cache
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.fibers.utils import get_org_fiber_ids
from apps.monitoring.incident_service import (
    _ensure_directional_fiber_id,
    strip_directional_suffix,
)
from apps.monitoring.incident_service import (
    query_by_id as incident_query_by_id,
)
from apps.monitoring.incident_service import (
    query_recent as incident_query_recent,
)
from apps.monitoring.models import IncidentAction, Infrastructure
from apps.monitoring.section_service import (
    delete_section,
    insert_section,
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

logger = logging.getLogger("sequoia")

_PROCESS_START_TIME = time.time()

INCIDENTS_CACHE_TTL = 10  # 10 seconds
STATS_CACHE_TTL = 5  # 5 seconds
FALLBACK_CACHE_TTL = 60  # 60 seconds when ClickHouse unavailable (reduce log spam)


def _get_fiber_ids_or_none(user):
    """Return fiber_ids list for org-scoped users, None for superusers."""
    if user.is_superuser:
        return None
    return get_org_fiber_ids(user.organization)


def _incidents_cache_key(user):
    if user.is_superuser:
        return "incidents:all"
    return f"incidents:org:{user.organization_id}"


def _stats_cache_key(user):
    if user.is_superuser:
        return "stats:all"
    return f"stats:org:{user.organization_id}"


def _verify_infrastructure_access(user, infrastructure_id):
    """Verify the user's org owns the infrastructure. Returns error Response or None."""
    if not infrastructure_id or user.is_superuser:
        return None
    if not Infrastructure.objects.filter(
        id=infrastructure_id,
        organization=user.organization,
    ).exists():
        return Response(
            {"detail": "Infrastructure not found", "code": "not_found"},
            status=404,
        )
    return None


class IncidentListView(APIView):
    """
    GET /api/incidents — returns active + recent incidents from ClickHouse.

    Org-scoped: only incidents from the user's assigned fibers.
    """

    permission_classes = [IsActiveUser]

    @extend_schema(
        responses={200: IncidentSerializer(many=True)},
        tags=["incidents"],
    )
    def get(self, request):
        try:
            limit = min(int(request.query_params.get("limit", 100)), 500)
        except (ValueError, TypeError):
            limit = 100

        cache_key = f"{_incidents_cache_key(request.user)}:{limit}"
        cached = django_cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        fiber_ids = _get_fiber_ids_or_none(request.user)
        if fiber_ids is not None and not fiber_ids:
            result = {"results": [], "hasMore": False, "limit": limit}
            django_cache.set(cache_key, result, INCIDENTS_CACHE_TTL)
            return Response(result)

        try:
            # Fetch one extra to detect if there's a next page
            incidents = incident_query_recent(fiber_ids=fiber_ids, hours=24, limit=limit + 1)
        except ClickHouseUnavailableError:
            incidents = None

        # Simulation keeps incidents in memory only — fall back when
        # ClickHouse is unavailable or returned no results.
        # Skip sim fallback when client is explicitly on the live flow.
        if not incidents and request.query_params.get("flow") != "live":
            from apps.realtime.simulation_manager import SimulationManager

            if SimulationManager.instance().is_running:
                try:
                    from apps.realtime.simulation import get_simulation_incidents

                    sim_incidents = get_simulation_incidents()
                    # Org-scope: filter sim incidents to user's fibers
                    if fiber_ids is not None:
                        sim_incidents = [
                            i
                            for i in sim_incidents
                            if strip_directional_suffix(i.get("fiberLine", "")) in fiber_ids
                        ]
                    if sim_incidents:
                        result = {
                            "results": sim_incidents,
                            "hasMore": False,
                            "limit": len(sim_incidents),
                        }
                        django_cache.set(cache_key, result, FALLBACK_CACHE_TTL)
                        return Response(result)
                except ImportError:
                    pass
        if incidents is None:
            return Response(
                {"detail": "ClickHouse unavailable", "code": "clickhouse_unavailable"},
                status=503,
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


class IncidentSnapshotView(APIView):
    """
    GET /api/incidents/<id>/snapshot — high-res speed data around an incident.

    Org-scoped: verifies the incident's fiber belongs to the user's org.

    Supports both live (ClickHouse) and simulation (in-memory) incidents.
    Simulation snapshots contain real recorded detections from the simulation
    engine — the same vehicles and speeds that were happening near the incident.
    """

    permission_classes = [IsActiveUser]

    @extend_schema(
        responses={200: IncidentSnapshotSerializer},
        tags=["incidents"],
    )
    def get(self, request, incident_id):
        # Check simulation cache first (fast path, no ClickHouse needed)
        # Skip sim cache when client is explicitly on the live flow
        if request.query_params.get("flow") != "live":
            sim_snapshot = self._get_simulation_snapshot(request, incident_id)
            if sim_snapshot is not None:
                return Response(sim_snapshot)

        try:
            incident_rows = query(
                """
                SELECT fiber_id, channel_start, channel_end, timestamp_ns
                FROM sequoia.fiber_incidents
                FINAL
                WHERE incident_id = {id:String}
                LIMIT 1
                """,
                parameters={"id": incident_id},
            )
        except ClickHouseUnavailableError:
            return Response(
                {"detail": "ClickHouse unavailable", "code": "clickhouse_unavailable"}, status=503
            )

        if not incident_rows:
            return Response(
                {"detail": "Incident not found", "code": "incident_not_found"}, status=404
            )

        incident = incident_rows[0]
        fiber_id = incident["fiber_id"]

        # Org-scoping: verify the incident's fiber belongs to user's org
        # fiber_id from ClickHouse may be directional ("carros:0") while
        # fiber_ids from FiberAssignment are plain ("carros") — strip suffix
        fiber_ids = _get_fiber_ids_or_none(request.user)
        if fiber_ids is not None:
            plain_fiber_id = strip_directional_suffix(fiber_id)
            if plain_fiber_id not in fiber_ids:
                return Response(
                    {"detail": "Incident not found", "code": "incident_not_found"}, status=404
                )

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
                  AND ch BETWEEN {ch_min:UInt16} AND {ch_max:UInt16}
                  AND ts BETWEEN fromUnixTimestamp64Nano({ts_start:UInt64})
                              AND fromUnixTimestamp64Nano({ts_end:UInt64})
                GROUP BY bucket_ms
                ORDER BY bucket_ms
                """,
                parameters={
                    "fid": fiber_id,
                    "ch_min": max(0, center_ch - 50),
                    "ch_max": center_ch + 50,
                    "ts_start": window_start_ns,
                    "ts_end": window_end_ns,
                },
            )
        except ClickHouseUnavailableError:
            return Response(
                {"detail": "ClickHouse unavailable", "code": "clickhouse_unavailable"}, status=503
            )

        # Build lookup from aggregated rows
        avg_vehicle_length_m = 6
        bucket_lookup = {}
        for row in agg_rows:
            avg_spd = round(row["avg_speed"])
            flow = int(row["total_count"])
            speed_ms = avg_spd * (1000 / 3600)
            occ = (
                min(100, round((flow * 3600 * avg_vehicle_length_m) / (speed_ms * 1000)))
                if speed_ms > 0
                else None
            )
            bucket_lookup[int(row["bucket_ms"])] = {
                "speed": avg_spd,
                "flow": flow,
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
                "fiberLine": _ensure_directional_fiber_id(fiber_id),
                "centerChannel": center_ch,
                "capturedAt": int(time.time() * 1000),
                "points": points,
                "complete": True,
            }
        )

    def _get_simulation_snapshot(self, request, incident_id: str) -> dict | None:
        """Return snapshot from simulation cache, or None to fall through to ClickHouse."""
        from apps.realtime.simulation import get_simulation_incidents, get_simulation_snapshot

        # Find the incident in simulation cache
        sim_incidents = get_simulation_incidents()
        sim_incident = next((i for i in sim_incidents if i["id"] == incident_id), None)
        if sim_incident is None:
            return None

        # Org-scoping: verify fiber belongs to user's org
        fiber_ids = _get_fiber_ids_or_none(request.user)
        if fiber_ids is not None:
            plain_fid = strip_directional_suffix(sim_incident["fiberLine"])
            if plain_fid not in fiber_ids:
                raise NotFound({"detail": "Incident not found", "code": "incident_not_found"})

        snapshot = get_simulation_snapshot(incident_id)
        points = snapshot["points"] if snapshot else []
        complete = snapshot["complete"] if snapshot else True

        return {
            "incidentId": incident_id,
            "fiberLine": sim_incident["fiberLine"],
            "centerChannel": sim_incident["channel"],
            "capturedAt": int(time.time() * 1000),
            "points": points,
            "complete": complete,
        }


class IncidentActionView(APIView):
    """
    GET  /api/incidents/<id>/actions — action history for an incident.
    POST /api/incidents/<id>/actions — record a workflow transition.

    Org-scoped: verifies the incident's fiber belongs to the user's org.
    POST requires non-viewer role (API keys are viewer-only).
    """

    def get_permissions(self):
        perms = [IsActiveUser()]
        if self.request.method == "POST":
            perms.append(IsNotViewer())
        return perms

    def _get_incident_or_404(self, incident_id, request):
        """Fetch incident from ClickHouse and verify org access."""
        try:
            incident = incident_query_by_id(incident_id)
        except ClickHouseUnavailableError:
            return None, Response(
                {"detail": "ClickHouse unavailable", "code": "clickhouse_unavailable"},
                status=503,
            )

        if not incident:
            return None, Response(
                {"detail": "Incident not found", "code": "incident_not_found"},
                status=404,
            )

        # Org-scoping
        fiber_ids = _get_fiber_ids_or_none(request.user)
        if fiber_ids is not None:
            plain_fiber_id = strip_directional_suffix(incident["fiber_id"])
            if plain_fiber_id not in fiber_ids:
                return None, Response(
                    {"detail": "Incident not found", "code": "incident_not_found"},
                    status=404,
                )

        return incident, None

    @extend_schema(
        responses={200: IncidentActionSerializer(many=True)},
        tags=["incidents"],
    )
    def get(self, request, incident_id):
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
    def post(self, request, incident_id):
        from django.db import transaction

        input_serializer = IncidentActionInputSerializer(data=request.data)
        if not input_serializer.is_valid():
            return Response(
                {
                    "detail": "Invalid input",
                    "code": "validation_error",
                    "errors": input_serializer.errors,
                },
                status=400,
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
                    status=409,
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
            status=201,
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
    def get(self, request):
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
                    "startChannel": item.start_channel,
                    "endChannel": item.end_channel,
                    "imageUrl": image_url,
                }
            )
        return Response({"results": data, "hasMore": False, "limit": len(data)})


class StatsView(APIView):
    """
    GET /api/stats — system-level statistics.

    Org-scoped: counts only fibers/channels/incidents/detections from
    the user's assigned fibers.
    """

    permission_classes = [IsActiveUser]

    @extend_schema(
        responses={200: StatsSerializer},
        tags=["stats"],
    )
    @clickhouse_fallback()
    def get(self, request):
        cache_key = _stats_cache_key(request.user)
        cached = django_cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        fiber_ids = _get_fiber_ids_or_none(request.user)

        if fiber_ids is not None:
            if not fiber_ids:
                fiber_count = 0
                total_channels = 0
                active_incidents = 0
                recent_rows = 0
                active_vehicles = 0
            else:
                fiber_count = (
                    query_scalar(
                        "SELECT count(DISTINCT fiber_id) FROM sequoia.fiber_cables WHERE fiber_id IN {fids:Array(String)}",
                        parameters={"fids": fiber_ids},
                    )
                    or 0
                )

                total_channels = (
                    query_scalar(
                        "SELECT sum(length(channel_coordinates)) FROM sequoia.fiber_cables WHERE fiber_id IN {fids:Array(String)}",
                        parameters={"fids": fiber_ids},
                    )
                    or 0
                )

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
            fiber_count = (
                query_scalar("SELECT count(DISTINCT fiber_id) FROM sequoia.fiber_cables") or 0
            )

            total_channels = (
                query_scalar("SELECT sum(length(channel_coordinates)) FROM sequoia.fiber_cables")
                or 0
            )

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

        data = {
            "fiberCount": fiber_count,
            "totalChannels": total_channels,
            "activeVehicles": int(active_vehicles),
            "detectionsPerSecond": round(float(recent_rows), 1),
            "activeIncidents": active_incidents,
            "systemUptime": int(time.time() - _PROCESS_START_TIME),
        }
        django_cache.set(cache_key, data, STATS_CACHE_TTL)
        return Response(data)


class SectionListView(APIView):
    """
    GET  /api/sections — list active monitored sections.
    POST /api/sections — create a new monitored section.

    Org-scoped via fiber assignment.
    """

    permission_classes = [IsActiveUser]

    @extend_schema(
        responses={200: SectionSerializer(many=True)},
        tags=["sections"],
    )
    @clickhouse_fallback(fallback_fn=lambda self, request, *a, **kw: Response({"results": []}))
    def get(self, request):
        fiber_ids = _get_fiber_ids_or_none(request.user)
        if fiber_ids is not None and not fiber_ids:
            return Response({"results": []})

        sections = query_sections(fiber_ids=fiber_ids)
        return Response({"results": sections})

    @extend_schema(
        request=SectionInputSerializer,
        responses={201: SectionSerializer},
        tags=["sections"],
    )
    @clickhouse_fallback()
    def post(self, request):
        serializer = SectionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        fiber_id = serializer.validated_data["fiberId"]
        name = serializer.validated_data["name"]
        channel_start = serializer.validated_data["channelStart"]
        channel_end = serializer.validated_data["channelEnd"]

        # Org-scoping: verify the fiber belongs to user's org
        fiber_ids = _get_fiber_ids_or_none(request.user)
        if fiber_ids is not None:
            plain_fiber_id = strip_directional_suffix(fiber_id)
            if plain_fiber_id not in fiber_ids:
                return Response(
                    {"detail": "Fiber not found", "code": "not_found"},
                    status=404,
                )

        section = insert_section(
            fiber_id=fiber_id,
            name=name,
            channel_start=channel_start,
            channel_end=channel_end,
            user=str(request.user.id) if hasattr(request.user, "id") else "",
        )
        return Response(section, status=201)


class SectionDeleteView(APIView):
    """
    DELETE /api/sections/<id> — soft-delete a monitored section.

    Org-scoped: verifies the section's fiber belongs to the user's org.
    """

    permission_classes = [IsActiveUser]

    @clickhouse_fallback()
    def delete(self, request, section_id):
        sections = query_sections()

        section = next((s for s in sections if s["id"] == section_id), None)
        if not section:
            return Response(
                {"detail": "Section not found", "code": "not_found"},
                status=404,
            )

        # Org-scoping
        fiber_ids = _get_fiber_ids_or_none(request.user)
        if fiber_ids is not None:
            if strip_directional_suffix(section["fiberId"]) not in fiber_ids:
                return Response(
                    {"detail": "Section not found", "code": "not_found"},
                    status=404,
                )

        delete_section(section_id, section["fiberId"])
        return Response(status=204)


class SectionHistoryView(APIView):
    """
    GET /api/sections/<id>/history?minutes=60 — speed time-series for a section.

    Aggregates speed_1m data over the section's channel range.
    """

    permission_classes = [IsActiveUser]

    @extend_schema(
        responses={200: SectionHistorySerializer},
        parameters=[
            OpenApiParameter(
                name="minutes", type=int, description="History window in minutes (max 1440)"
            ),
        ],
        tags=["sections"],
    )
    @clickhouse_fallback()
    def get(self, request, section_id):
        try:
            minutes = min(int(request.query_params.get("minutes", 60)), 1440)
        except (ValueError, TypeError):
            minutes = 60

        sections = query_sections()

        section = next((s for s in sections if s["id"] == section_id), None)
        if not section:
            return Response(
                {"detail": "Section not found", "code": "not_found"},
                status=404,
            )

        # Org-scoping
        fiber_ids = _get_fiber_ids_or_none(request.user)
        if fiber_ids is not None:
            if strip_directional_suffix(section["fiberId"]) not in fiber_ids:
                return Response(
                    {"detail": "Section not found", "code": "not_found"},
                    status=404,
                )

        history = query_section_history(
            fiber_id=section["fiberId"],
            channel_start=section["channelStart"],
            channel_end=section["channelEnd"],
            minutes=minutes,
        )

        return Response(
            {
                "sectionId": section_id,
                "minutes": minutes,
                "points": history,
            }
        )


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
    def get(self, request):
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
                status=404,
            )

        try:
            data = load_spectral_data()
        except Exception as e:
            logger.error(f"Failed to load spectral data: {e}")
            return Response(
                {"detail": "Failed to load spectral data", "code": "shm_load_error"}, status=500
            )

        # Apply time filtering if startTime/endTime provided (takes priority over indices)
        start_time_str = request.query_params.get("startTime")
        end_time_str = request.query_params.get("endTime")

        if start_time_str or end_time_str:
            # Calculate absolute timestamps for all samples
            timestamps = np.array([data.t0.timestamp() + offset for offset in data.dt])

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
    - maxSamples: Maximum number of time samples to return (default 1000)
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
    def get(self, request):
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
                status=404,
            )

        try:
            data = load_spectral_data()
        except Exception as e:
            logger.error(f"Failed to load spectral data: {e}")
            return Response(
                {"detail": "Failed to load spectral data", "code": "shm_load_error"}, status=500
            )

        # Apply time filtering if startTime/endTime provided
        start_time_str = request.query_params.get("startTime")
        end_time_str = request.query_params.get("endTime")

        if start_time_str or end_time_str:
            # Calculate absolute timestamps for all samples
            timestamps = np.array([data.t0.timestamp() + offset for offset in data.dt])

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

        try:
            max_samples = min(int(request.query_params.get("maxSamples", 1000)), 5000)
        except (ValueError, TypeError):
            max_samples = 1000
        data = data.downsample_time(max_samples)

        peak_freqs, peak_powers = data.get_peak_frequencies()

        return Response(
            {
                "t0": data.t0.isoformat(),
                "dt": data.dt.tolist(),
                "peakFrequencies": peak_freqs.tolist(),
                "peakPowers": peak_powers.tolist(),
                "freqRange": list(data.freq_range),
            }
        )


class SpectralSummaryView(APIView):
    """
    GET /api/shm/summary — returns summary info about available spectral data.

    Lightweight endpoint to check data availability without loading full dataset.
    """

    permission_classes = [IsActiveUser]

    @extend_schema(tags=["shm"])
    def get(self, request):
        from apps.monitoring.hdf5_reader import get_spectral_summary, sample_file_exists

        if not sample_file_exists():
            return Response(
                {"detail": "No SHM sample data available", "code": "shm_data_unavailable"},
                status=404,
            )

        try:
            summary = get_spectral_summary()
        except Exception as e:
            logger.error(f"Failed to get spectral summary: {e}")
            return Response(
                {"detail": "Failed to load spectral data", "code": "shm_load_error"}, status=500
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
    def get(self, request, infrastructure_id):
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
                status=400,
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
