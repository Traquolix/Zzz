"""
Section views — list/create, delete, and history (single + batch).

All queries are org-scoped via Section.organization FK.
"""

import contextlib
import logging

from django.core.cache import cache as django_cache
from django.db import IntegrityError
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.fibers.utils import fiber_belongs_to_org
from apps.monitoring.mixins import FlowAwareMixin
from apps.monitoring.models import Section
from apps.monitoring.section_service import (
    delete_section,
    get_section,
    insert_section,
    query_batch_section_history,
    query_section_history,
    query_sections,
)
from apps.monitoring.serializers import (
    SectionHistorySerializer,
    SectionInputSerializer,
    SectionSerializer,
)
from apps.monitoring.view_helpers import _get_fiber_ids_or_none
from apps.shared.clickhouse import clickhouse_fallback
from apps.shared.constants import MAX_SECTIONS_PER_ORG
from apps.shared.permissions import IsActiveUser, IsNotViewer
from apps.shared.utils import build_org_cache_key

logger = logging.getLogger("sequoia.monitoring.views")


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


class SectionDetailView(APIView):
    """
    PATCH  /api/sections/<id> — update section name.
    DELETE /api/sections/<id> — delete a monitored section.

    Org-scoped via Section.organization FK. Requires non-viewer role.
    """

    permission_classes = [IsActiveUser, IsNotViewer]

    def patch(self, request: Request, section_id: str) -> Response:
        from apps.monitoring.models import Section

        org_id = None if request.user.is_superuser else request.user.organization_id
        qs = Section.objects.filter(id=section_id)
        if org_id is not None:
            qs = qs.filter(organization_id=org_id)
        section = qs.first()
        if not section:
            return Response(
                {"detail": "Section not found", "code": "not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        name = request.data.get("name")
        if name:
            section.name = name
            section.save(update_fields=["name", "updated_at"])
        return Response({"id": section.id, "name": section.name})

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
        from apps.shared.simulation_cache import get_simulation_section_history

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
        from apps.shared.simulation_cache import get_simulation_section_history

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
