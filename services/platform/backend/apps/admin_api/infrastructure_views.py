"""
Admin API views — Infrastructure CRUD.

Permission model:
- Infrastructure management: org admin (scoped to own org) or superuser (all)
"""

import logging

from django.db.models import Q
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.monitoring.models import Infrastructure
from apps.organizations.models import Organization
from apps.shared.admin_permissions import IsAdminOrSuperuser
from apps.shared.utils import add_cache_control, org_filter_queryset, paginate_queryset

logger = logging.getLogger("sequoia.admin_api.infrastructure_views")


# ---------------------------------------------------------------------------
# Infrastructure (admin + superuser)
# ---------------------------------------------------------------------------


class InfrastructureAdminListView(APIView):
    permission_classes = [IsAdminOrSuperuser]

    @add_cache_control()
    def get(self, request: Request) -> Response:
        search = request.GET.get("search", "").strip()
        items = org_filter_queryset(Infrastructure.objects.all(), request.user)

        # Apply search filter
        if search:
            items = items.filter(Q(name__icontains=search) | Q(type__icontains=search))

        # Apply pagination
        page, pagination_data = paginate_queryset(request, items)

        results = []
        for item in page:
            results.append(
                {
                    "id": item.id,
                    "name": item.name,
                    "type": item.type,
                    "fiberId": item.fiber_id,
                    "direction": item.direction,
                    "startChannel": item.start_channel,
                    "endChannel": item.end_channel,
                    "organizationId": str(item.organization_id),
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
        data = request.data
        required = ["id", "name", "type", "fiberId", "startChannel", "endChannel"]
        missing = [f for f in required if f not in data]
        if missing:
            return Response(
                {"detail": f"Missing fields: {', '.join(missing)}", "code": "validation_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.shared.constants import INFRASTRUCTURE_TYPES

        valid_types = [t[0] for t in INFRASTRUCTURE_TYPES]
        if data["type"] not in valid_types:
            return Response(
                {
                    "detail": f"Invalid type. Must be one of: {', '.join(valid_types)}",
                    "code": "validation_error",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        org = request.user.organization if not request.user.is_superuser else None
        if request.user.is_superuser:
            org_id = data.get("organizationId")
            if org_id:
                try:
                    org = Organization.objects.get(pk=org_id)
                except Organization.DoesNotExist:
                    return Response(
                        {"detail": "Organization not found", "code": "org_invalid"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            else:
                return Response(
                    {"detail": "organizationId required for superuser", "code": "org_required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        infra = Infrastructure.objects.create(
            id=data["id"],
            name=data["name"],
            type=data["type"],
            organization=org,
            fiber_id=data["fiberId"],
            direction=data.get("direction"),
            start_channel=data["startChannel"],
            end_channel=data["endChannel"],
            image=data.get("image", ""),
        )
        return Response(
            {
                "id": infra.id,
                "name": infra.name,
                "type": infra.type,
            },
            status=status.HTTP_201_CREATED,
        )


class InfrastructureAdminDetailView(APIView):
    permission_classes = [IsAdminOrSuperuser]

    def delete(self, request: Request, infra_id: str) -> Response:
        try:
            item = org_filter_queryset(Infrastructure.objects.all(), request.user).get(id=infra_id)
        except Infrastructure.DoesNotExist:
            return Response(
                {"detail": "Not found", "code": "not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
