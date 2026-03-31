"""
Admin API views — API Key CRUD and rotation.

Permission model:
- API key management: org admin (scoped to own org) or superuser (all)
"""

import logging

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api_keys.models import APIKey
from apps.organizations.models import Organization
from apps.shared.admin_permissions import IsAdminOrSuperuser
from apps.shared.utils import org_filter_queryset

logger = logging.getLogger("sequoia.admin_api.api_key_views")


# ---------------------------------------------------------------------------
# API Keys (admin + superuser)
# ---------------------------------------------------------------------------


class APIKeyListView(APIView):
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request: Request) -> Response:
        keys = org_filter_queryset(APIKey.objects.filter(is_active=True), request.user)
        results = [
            {
                "id": str(k.pk),
                "name": k.name,
                "prefix": k.key_prefix,
                "scopes": k.scopes,
                "createdAt": k.created_at.isoformat(),
                "requestCount": k.request_count,
                "lastUsedAt": k.last_used_at.isoformat() if k.last_used_at else None,
                "expiresAt": k.expires_at.isoformat() if k.expires_at else None,
            }
            for k in keys
        ]
        return Response({"results": results})

    def post(self, request: Request) -> Response:
        name = request.data.get("name")
        if not name:
            return Response(
                {"detail": "name is required", "code": "validation_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        org = request.user.organization if not request.user.is_superuser else None
        if request.user.is_superuser:
            org_id = request.data.get("organizationId")
            if org_id:
                try:
                    org = Organization.objects.get(pk=org_id)
                except Organization.DoesNotExist:
                    return Response(
                        {"detail": "Organization not found"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            else:
                return Response(
                    {"detail": "organizationId required for superuser"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        from django.utils.dateparse import parse_datetime

        expires_at = None
        if request.data.get("expiresAt"):
            expires_at = parse_datetime(request.data["expiresAt"])

        key_obj, raw_key = APIKey.generate(
            organization=org,
            name=name,
            created_by=request.user,
            expires_at=expires_at,
        )
        return Response(
            {
                "id": str(key_obj.pk),
                "name": key_obj.name,
                "prefix": key_obj.key_prefix,
                "key": raw_key,  # Only returned once at creation
            },
            status=status.HTTP_201_CREATED,
        )


class APIKeyDetailView(APIView):
    permission_classes = [IsAdminOrSuperuser]

    def delete(self, request: Request, key_id: str) -> Response:
        try:
            key_obj = org_filter_queryset(APIKey.objects.all(), request.user).get(pk=key_id)
        except APIKey.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        key_obj.is_active = False
        key_obj.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class APIKeyRotateView(APIView):
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request: Request, key_id: str) -> Response:
        try:
            old_key = org_filter_queryset(APIKey.objects.all(), request.user).get(pk=key_id)
        except APIKey.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        # Revoke old key
        old_key.is_active = False
        old_key.save(update_fields=["is_active"])

        # Create new key with same config
        new_key, raw_key = APIKey.generate(
            organization=old_key.organization,
            name=old_key.name,
            created_by=request.user,
            expires_at=old_key.expires_at,
            scopes=old_key.scopes,
        )
        return Response(
            {
                "id": str(new_key.pk),
                "name": new_key.name,
                "prefix": new_key.key_prefix,
                "key": raw_key,
            }
        )
