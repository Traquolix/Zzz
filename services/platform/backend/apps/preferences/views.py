"""
User preferences views — stored in PostgreSQL.
"""

import json
from typing import Any

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as s
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.preferences.models import UserPreferences
from apps.shared.audit import AuditService
from apps.shared.models import AuditLog
from apps.shared.permissions import IsActiveUser

MAX_PREFERENCES_SIZE = 64 * 1024  # 64KB max payload
MAX_NESTING_DEPTH = 10  # Prevent deeply nested structures
MAX_ARRAY_LENGTH = 1000  # Prevent huge arrays


def _validate_json_structure(data: Any, depth: int = 0, path: str = "root") -> list[str]:
    """
    Validate JSON structure to prevent abuse.

    Checks:
    - Maximum nesting depth
    - Maximum array length
    - Only allowed types (dict, list, str, int, float, bool, None)

    Returns list of validation errors (empty if valid).
    """
    errors = []

    if depth > MAX_NESTING_DEPTH:
        errors.append(f"{path}: exceeds maximum nesting depth of {MAX_NESTING_DEPTH}")
        return errors

    if isinstance(data, dict):
        for key, value in data.items():
            if not isinstance(key, str):
                errors.append(f"{path}: dict keys must be strings")
                continue
            errors.extend(_validate_json_structure(value, depth + 1, f"{path}.{key}"))

    elif isinstance(data, list):
        if len(data) > MAX_ARRAY_LENGTH:
            errors.append(f"{path}: array exceeds maximum length of {MAX_ARRAY_LENGTH}")
        for i, item in enumerate(data[:MAX_ARRAY_LENGTH]):
            errors.extend(_validate_json_structure(item, depth + 1, f"{path}[{i}]"))

    elif not isinstance(data, (str, int, float, bool, type(None))):
        errors.append(f"{path}: invalid type {type(data).__name__}")

    return errors


_PreferencesResponse = inline_serializer(
    "UserPreferencesResponse",
    fields={
        "dashboard": s.DictField(),
        "map": s.DictField(),
    },
)


class UserPreferencesView(APIView):
    """
    GET /api/user/preferences — returns current user's preferences.
    PUT /api/user/preferences — updates current user's preferences.

    Response matches frontend UserPreferences type:
    { dashboard?: { layouts?, widgets? }, map?: { landmarks?, sections?, layerVisibility?, speedLimitZones? } }
    """

    permission_classes = [IsActiveUser]

    @extend_schema(responses={200: _PreferencesResponse}, tags=["preferences"])
    def get(self, request: Request) -> Response:
        prefs, _ = UserPreferences.objects.get_or_create(user=request.user)
        return Response(
            {
                "dashboard": prefs.dashboard or {},
                "map": prefs.map_config or {},
            }
        )

    @extend_schema(
        request=inline_serializer(
            "UserPreferencesRequest",
            fields={
                "dashboard": s.DictField(required=False),
                "map": s.DictField(required=False),
            },
        ),
        responses={200: _PreferencesResponse},
        tags=["preferences"],
    )
    def put(self, request: Request) -> Response:
        # Validate payload size to prevent abuse
        payload_size = len(json.dumps(request.data).encode("utf-8"))
        if payload_size > MAX_PREFERENCES_SIZE:
            return Response(
                {
                    "detail": f"Payload too large ({payload_size} bytes, max {MAX_PREFERENCES_SIZE}).",
                    "code": "payload_too_large",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = request.data

        # Validate JSON structure to prevent malformed/malicious payloads
        validation_errors = []
        if "dashboard" in data:
            validation_errors.extend(_validate_json_structure(data["dashboard"], path="dashboard"))
        if "map" in data:
            validation_errors.extend(_validate_json_structure(data["map"], path="map"))

        if validation_errors:
            return Response(
                {
                    "detail": "Invalid preferences structure",
                    "errors": validation_errors[:10],
                    "code": "validation_error",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        prefs, _ = UserPreferences.objects.get_or_create(user=request.user)

        if "dashboard" in data:
            prefs.dashboard = data["dashboard"]
        if "map" in data:
            prefs.map_config = data["map"]

        prefs.save()

        AuditService.log(
            request=request,
            action=AuditLog.Action.PREFERENCES_UPDATED,  # type: ignore[arg-type]  # TextChoices is str at runtime; no django-stubs
            object_type="UserPreferences",
            object_id=str(request.user.id),
            changes={"updated_keys": [k for k in ("dashboard", "map") if k in data]},
        )

        return Response(
            {
                "dashboard": prefs.dashboard or {},
                "map": prefs.map_config or {},
            }
        )
