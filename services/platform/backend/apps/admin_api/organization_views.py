"""
Admin API views — Organization and OrgSettings CRUD.

Permission model:
- Organization CRUD: superuser only
- OrgSettings GET/PATCH: org admin (scoped to own org) or superuser (all)
"""

import logging

from django.db.models import Q
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.incidents.models import seed_default_tags
from apps.organizations.models import Organization, OrganizationSettings
from apps.shared.admin_permissions import IsAdminOrSuperuser, IsSuperuser
from apps.shared.utils import add_cache_control, paginate_queryset

logger = logging.getLogger("sequoia.admin_api.organization_views")


# ---------------------------------------------------------------------------
# Organizations (superuser only)
# ---------------------------------------------------------------------------


class OrganizationListView(APIView):
    permission_classes = [IsSuperuser]

    @add_cache_control()
    def get(self, request: Request) -> Response:
        search = request.GET.get("search", "").strip()
        orgs = Organization.objects.prefetch_related("settings", "fiber_assignments").all()

        # Apply search filter
        if search:
            orgs = orgs.filter(Q(name__icontains=search) | Q(slug__icontains=search))

        # Apply pagination
        page, pagination_data = paginate_queryset(request, orgs)

        results = []
        for org in page:
            fiber_assignments = []
            for fa in org.fiber_assignments.all():
                fiber_assignments.append(
                    {
                        "id": str(fa.pk),
                        "fiberId": fa.fiber_id,
                        "assignedAt": fa.assigned_at.isoformat(),
                    }
                )
            settings = getattr(org, "settings", None)
            results.append(
                {
                    "id": str(org.pk),
                    "name": org.name,
                    "slug": org.slug,
                    "isActive": org.is_active,
                    "createdAt": org.created_at.isoformat(),
                    "allowedWidgets": settings.allowed_widgets if settings else [],
                    "allowedLayers": settings.allowed_layers if settings else [],
                    "fiberAssignments": fiber_assignments,
                }
            )
        return Response(
            {
                "results": results,
                "hasMore": pagination_data["hasMore"],
                "limit": pagination_data["limit"],
                "offset": pagination_data["offset"],
                "total": pagination_data["total"],
            }
        )

    def post(self, request: Request) -> Response:
        name = request.data.get("name")
        if not name:
            return Response(
                {"detail": "Name is required", "code": "validation_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        org = Organization.objects.create(name=name)
        # Auto-create settings and default tags
        OrganizationSettings.objects.get_or_create(organization=org)
        seed_default_tags(org)
        return Response(
            {
                "id": str(org.pk),
                "name": org.name,
                "slug": org.slug,
                "isActive": org.is_active,
            },
            status=status.HTTP_201_CREATED,
        )


class OrganizationDetailView(APIView):
    permission_classes = [IsSuperuser]

    def patch(self, request: Request, org_id: str) -> Response:
        try:
            org = Organization.objects.get(pk=org_id)
        except Organization.DoesNotExist:
            return Response(
                {"detail": "Organization not found", "code": "not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        if "name" in request.data:
            org.name = request.data["name"]
        if "isActive" in request.data:
            org.is_active = request.data["isActive"]
        org.save()
        return Response(
            {
                "id": str(org.pk),
                "name": org.name,
                "slug": org.slug,
                "isActive": org.is_active,
            }
        )


class OrgSettingsView(APIView):
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request: Request, org_id: str) -> Response:
        # Org admin can only GET their own org's settings
        # Superuser can GET any
        if not request.user.is_superuser and str(request.user.organization_id) != str(org_id):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        try:
            settings = OrganizationSettings.objects.select_related("organization").get(
                organization_id=org_id
            )
        except OrganizationSettings.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            {
                "timezone": settings.timezone,
                "speedAlertThreshold": settings.speed_alert_threshold,
                "incidentAutoResolveMinutes": settings.incident_auto_resolve_minutes,
                "shmEnabled": settings.shm_enabled,
                "allowedWidgets": settings.allowed_widgets,
                "allowedLayers": settings.allowed_layers,
            }
        )

    def patch(self, request: Request, org_id: str) -> Response:
        if not request.user.is_superuser and str(request.user.organization_id) != str(org_id):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        try:
            settings = OrganizationSettings.objects.get(organization_id=org_id)
        except OrganizationSettings.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        data = request.data

        # Fields org admin CAN edit
        if "timezone" in data:
            settings.timezone = data["timezone"]
        if "speedAlertThreshold" in data:
            settings.speed_alert_threshold = data["speedAlertThreshold"]
        if "incidentAutoResolveMinutes" in data:
            settings.incident_auto_resolve_minutes = data["incidentAutoResolveMinutes"]
        if "shmEnabled" in data:
            settings.shm_enabled = data["shmEnabled"]

        # Fields ONLY superuser can edit
        if "allowedWidgets" in data:
            if not request.user.is_superuser:
                return Response(
                    {"detail": "Only superusers can edit widget restrictions"},
                    status=status.HTTP_403_FORBIDDEN,
                )
            widgets = data["allowedWidgets"]
            from apps.shared.constants import ALL_WIDGETS

            invalid = [w for w in widgets if w not in ALL_WIDGETS]
            if invalid:
                return Response(
                    {"detail": f"Invalid widget keys: {', '.join(invalid)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            settings.allowed_widgets = widgets

        if "allowedLayers" in data:
            if not request.user.is_superuser:
                return Response(
                    {"detail": "Only superusers can edit layer restrictions"},
                    status=status.HTTP_403_FORBIDDEN,
                )
            layers = data["allowedLayers"]
            from apps.shared.constants import ALL_LAYERS

            invalid = [layer for layer in layers if layer not in ALL_LAYERS]
            if invalid:
                return Response(
                    {"detail": f"Invalid layer keys: {', '.join(invalid)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            settings.allowed_layers = layers

        settings.save()
        return Response(
            {
                "timezone": settings.timezone,
                "speedAlertThreshold": settings.speed_alert_threshold,
                "incidentAutoResolveMinutes": settings.incident_auto_resolve_minutes,
                "shmEnabled": settings.shm_enabled,
                "allowedWidgets": settings.allowed_widgets,
                "allowedLayers": settings.allowed_layers,
            }
        )
