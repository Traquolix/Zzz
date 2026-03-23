"""
DRF authentication backend for API keys.

Checks the X-API-Key header, validates against stored hashes,
and returns a service user scoped to the key's organization.
"""

import hashlib
import logging
from typing import Any

from django.db.models import F
from django.utils import timezone
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

from apps.api_keys.models import APIKey

logger = logging.getLogger("sequoia.api_keys")


class APIKeyAuthenticationScheme(OpenApiAuthenticationExtension):
    """Tell drf-spectacular how to document APIKeyAuthentication in the OpenAPI schema."""

    target_class = "apps.api_keys.authentication.APIKeyAuthentication"
    name = "apiKeyAuth"

    def get_security_definition(self, auto_schema: Any) -> dict[str, Any]:
        return {"type": "apiKey", "in": "header", "name": "X-API-Key"}


class APIKeyAuthentication(BaseAuthentication):
    """
    Authenticate requests using the X-API-Key header.

    The key format is 'sqk_<secret>'. We hash the secret part and
    look it up in the database.

    On success, returns (user, api_key) where user is a service account
    with role='viewer' scoped to the key's organization.
    """

    def authenticate(self, request: Request) -> tuple[Any, APIKey] | None:
        raw_key = request.META.get("HTTP_X_API_KEY")
        if not raw_key:
            return None  # Not an API key request — let other auth backends try

        if not raw_key.startswith("sqk_"):
            raise AuthenticationFailed("Invalid API key format.")

        secret = raw_key[4:]  # Strip 'sqk_' prefix
        key_hash = hashlib.sha256(secret.encode()).hexdigest()

        try:
            api_key = APIKey.objects.select_related("organization").get(
                key_hash=key_hash,
            )
        except APIKey.DoesNotExist:
            raise AuthenticationFailed("Invalid API key.")

        if not api_key.is_active:
            raise AuthenticationFailed("API key has been revoked.")

        if api_key.expires_at and api_key.expires_at < timezone.now():
            raise AuthenticationFailed("API key has expired.")

        if not api_key.organization.is_active:
            raise AuthenticationFailed("Organization is inactive.")

        # Update last_used_at and request_count without triggering save() overhead
        APIKey.objects.filter(pk=api_key.pk).update(
            last_used_at=timezone.now(),
            request_count=F("request_count") + 1,
        )

        # Get or create a service user for this org
        user = self._get_service_user(api_key.organization)

        return (user, api_key)

    def _get_service_user(self, organization: Any) -> Any:
        """Get or create a viewer-role service user for API key access."""
        from django.contrib.auth import get_user_model

        User = get_user_model()

        username = f"apikey-{organization.slug}"
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "organization": organization,
                "role": "viewer",
                "is_active": True,
            },
        )
        if created:
            user.set_unusable_password()
            user.save()

        # Ensure org is always current
        if user.organization_id != organization.pk:
            user.organization = organization
            user.save(update_fields=["organization"])

        return user
