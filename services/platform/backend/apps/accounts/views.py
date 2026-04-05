"""
Authentication views.

VerifyView: returns current user info for any authenticated user (OIDC or API key).
OIDCConfigView: returns Authentik OIDC endpoints for the frontend.
"""

import logging

from django.conf import settings
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as s
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class VerifyView(APIView):
    """
    Verify the current access token and return user info.
    Works with OIDC tokens (Authentik) and API key authentication.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={
            200: inline_serializer(
                "VerifyResponse",
                fields={
                    "valid": s.BooleanField(),
                    "username": s.CharField(),
                    "allowedWidgets": s.ListField(child=s.CharField()),
                    "allowedLayers": s.ListField(child=s.CharField()),
                },
            )
        },
        tags=["auth"],
    )
    def get(self, request: Request) -> Response:
        user = request.user
        return Response(
            {
                "valid": True,
                "username": user.username,
                "allowedWidgets": user.allowed_widgets,
                "allowedLayers": user.allowed_layers,
                "organizationId": str(user.organization_id) if user.organization_id else None,
                "organizationName": user.organization.name if user.organization else None,
                "role": user.role,
                "isSuperuser": user.is_superuser,
            }
        )


class OIDCConfigView(APIView):
    """
    Return OIDC provider configuration for the frontend.

    The frontend uses these endpoints to configure oidc-client-ts.
    This avoids hardcoding Authentik URLs in the frontend build.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(
        responses={
            200: inline_serializer(
                "OIDCConfigResponse",
                fields={
                    "authority": s.CharField(),
                    "client_id": s.CharField(),
                    "issuer": s.CharField(),
                },
            )
        },
        tags=["auth"],
    )
    def get(self, request: Request) -> Response:
        return Response(
            {
                "authority": settings.OIDC_ISSUER_URL.rstrip("/"),
                "client_id": settings.OIDC_AUDIENCE,
                "issuer": settings.OIDC_ISSUER_URL,
            }
        )
