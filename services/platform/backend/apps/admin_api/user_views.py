"""
Admin API views — User CRUD.

Permission model:
- User management: org admin (scoped to own org) or superuser (all)
"""

import logging

from django.db.models import Q
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.organizations.models import Organization
from apps.shared.admin_permissions import IsAdminOrSuperuser
from apps.shared.utils import add_cache_control, org_filter_queryset, paginate_queryset

logger = logging.getLogger("sequoia.admin_api.user_views")


# ---------------------------------------------------------------------------
# Users (admin + superuser)
# ---------------------------------------------------------------------------


class UserListView(APIView):
    permission_classes = [IsAdminOrSuperuser]

    @add_cache_control()
    def get(self, request: Request) -> Response:
        search = request.GET.get("search", "").strip()
        users = org_filter_queryset(User.objects.select_related("organization"), request.user)

        # Apply search filter
        if search:
            users = users.filter(Q(username__icontains=search) | Q(email__icontains=search))

        # Apply pagination
        page, pagination_data = paginate_queryset(request, users)

        results = []
        for u in page:
            results.append(
                {
                    "id": str(u.pk),
                    "username": u.username,
                    "email": u.email,
                    "role": u.role,
                    "isActive": u.is_active,
                    "organizationId": str(u.organization_id) if u.organization_id else None,
                    "organizationName": u.organization.name if u.organization else None,
                    "allowedWidgets": u.allowed_widgets,
                    "allowedLayers": u.allowed_layers,
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
        username = request.data.get("username")
        password = request.data.get("password")
        role = request.data.get("role", "viewer")

        if not username or not password:
            return Response(
                {"detail": "Username and password are required", "code": "validation_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate role against allowed choices
        from apps.shared.constants import USER_ROLES

        valid_roles = [r[0] for r in USER_ROLES]
        if role not in valid_roles:
            return Response(
                {
                    "detail": f"Invalid role. Must be one of: {', '.join(valid_roles)}",
                    "code": "validation_error",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate password strength
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError

        try:
            validate_password(password)
        except DjangoValidationError as e:
            return Response(
                {"detail": e.messages[0], "code": "validation_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Determine org: admin creates in their own org; superuser can specify
        if request.user.is_superuser:
            org_id = request.data.get("organizationId")
            org = None
            if org_id:
                try:
                    org = Organization.objects.get(pk=org_id)
                except Organization.DoesNotExist:
                    return Response(
                        {"detail": "Organization not found", "code": "org_invalid"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        else:
            org = request.user.organization

        user = User.objects.create_user(
            username=username,
            password=password,
            email=request.data.get("email", ""),
            organization=org,
            role=role,
        )
        return Response(
            {
                "id": str(user.pk),
                "username": user.username,
                "role": user.role,
                "organizationId": str(user.organization_id) if user.organization_id else None,
            },
            status=status.HTTP_201_CREATED,
        )


class UserDetailView(APIView):
    permission_classes = [IsAdminOrSuperuser]

    def patch(self, request: Request, user_id: str) -> Response:
        try:
            user = org_filter_queryset(User.objects.all(), request.user).get(pk=user_id)
        except User.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        data = request.data

        # Prevent self-modification of role and active status
        if str(user.pk) == str(request.user.pk) and ("role" in data or "isActive" in data):
            return Response(
                {
                    "detail": "Cannot modify your own role or active status",
                    "code": "self_modification",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if "role" in data:
            from apps.shared.constants import USER_ROLES

            valid_roles = [r[0] for r in USER_ROLES]
            if data["role"] not in valid_roles:
                return Response(
                    {"detail": f"Invalid role. Must be one of: {', '.join(valid_roles)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user.role = data["role"]
        if "email" in data:
            user.email = data["email"]
        if "isActive" in data:
            user.is_active = data["isActive"]
        if "allowedWidgets" in data:
            from apps.shared.constants import ALL_WIDGETS

            invalid = [w for w in data["allowedWidgets"] if w not in ALL_WIDGETS]
            if invalid:
                return Response(
                    {"detail": f"Invalid widget keys: {', '.join(invalid)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user.allowed_widgets = data["allowedWidgets"]
        if "allowedLayers" in data:
            from apps.shared.constants import ALL_LAYERS

            invalid = [layer for layer in data["allowedLayers"] if layer not in ALL_LAYERS]
            if invalid:
                return Response(
                    {"detail": f"Invalid layer keys: {', '.join(invalid)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user.allowed_layers = data["allowedLayers"]

        user.save()
        return Response(
            {
                "id": str(user.pk),
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "isActive": user.is_active,
                "allowedWidgets": user.allowed_widgets,
                "allowedLayers": user.allowed_layers,
                "organizationId": str(user.organization_id) if user.organization_id else None,
            }
        )
