"""
Admin API views — Tag CRUD.

Permission model: org admin (scoped to own org) or superuser (all).
"""

import logging

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.incidents.models import Tag
from apps.organizations.models import Organization
from apps.shared.admin_permissions import IsAdminOrSuperuser
from apps.shared.utils import add_cache_control, org_filter_queryset, paginate_queryset

logger = logging.getLogger("sequoia.admin_api.tag_views")


class TagListView(APIView):
    permission_classes = [IsAdminOrSuperuser]

    @add_cache_control()
    def get(self, request: Request) -> Response:
        tags = org_filter_queryset(Tag.objects.all(), request.user)
        page, pagination_data = paginate_queryset(request, tags)

        results = [
            {
                "id": str(tag.pk),
                "name": tag.name,
                "color": tag.color,
                "isLocked": tag.is_locked,
            }
            for tag in page
        ]
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
        name = (data.get("name") or "").strip()
        color = data.get("color", "#6b7280")

        if not name:
            return Response(
                {"detail": "name is required", "code": "validation_error"},
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

        if Tag.objects.filter(organization=org, name=name).exists():
            return Response(
                {"detail": f"Tag '{name}' already exists", "code": "duplicate"},
                status=status.HTTP_409_CONFLICT,
            )

        tag = Tag.objects.create(organization=org, name=name, color=color)
        return Response(
            {
                "id": str(tag.pk),
                "name": tag.name,
                "color": tag.color,
                "isLocked": tag.is_locked,
            },
            status=status.HTTP_201_CREATED,
        )


class TagDetailView(APIView):
    permission_classes = [IsAdminOrSuperuser]

    def _get_tag(self, request: Request, tag_id: str) -> tuple[Tag | None, Response | None]:
        try:
            return org_filter_queryset(Tag.objects.all(), request.user).get(pk=tag_id), None
        except Tag.DoesNotExist:
            return None, Response(
                {"detail": "Not found", "code": "not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )

    def patch(self, request: Request, tag_id: str) -> Response:
        tag, error = self._get_tag(request, tag_id)
        if error:
            return error
        assert tag is not None

        data = request.data

        if tag.is_locked and "name" in data:
            return Response(
                {"detail": "Cannot rename a locked tag", "code": "locked"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if "name" in data:
            name = (data["name"] or "").strip()
            if not name:
                return Response(
                    {"detail": "name cannot be empty", "code": "validation_error"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if (
                Tag.objects.filter(organization=tag.organization, name=name)
                .exclude(pk=tag.pk)
                .exists()
            ):
                return Response(
                    {"detail": f"Tag '{name}' already exists", "code": "duplicate"},
                    status=status.HTTP_409_CONFLICT,
                )
            tag.name = name

        if "color" in data:
            tag.color = data["color"]

        tag.save()
        return Response(
            {
                "id": str(tag.pk),
                "name": tag.name,
                "color": tag.color,
                "isLocked": tag.is_locked,
            }
        )

    def delete(self, request: Request, tag_id: str) -> Response:
        tag, error = self._get_tag(request, tag_id)
        if error:
            return error
        assert tag is not None

        if tag.is_locked:
            return Response(
                {"detail": "Cannot delete a locked tag", "code": "locked"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tag.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
