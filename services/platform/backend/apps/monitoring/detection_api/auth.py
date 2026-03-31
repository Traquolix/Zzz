"""
Public API authentication and rate limiting.

API key only (X-API-Key: sqk_...). JWT is not accepted on these endpoints.
Rate limit: 300 requests/hour per API key.
"""

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from apps.api_keys.models import APIKey


class PublicAPIThrottle(SimpleRateThrottle):
    """Rate limiter for public API endpoints, keyed by API key."""

    scope = "public_api"

    def get_cache_key(self, request: Request, view: APIView) -> str | None:
        # Key by the API key hash, not the user
        api_key = getattr(request, "auth", None)
        if isinstance(api_key, APIKey):
            key: str = self.cache_format % {"scope": self.scope, "ident": api_key.key_hash[:16]}
            return key
        # Fallback: shouldn't happen since IsAPIKeyUser rejects non-API-key requests
        return None


class IsAPIKeyUser(BasePermission):
    """
    Allows access only to requests authenticated via API key.

    Rejects JWT-authenticated requests to keep the public API cleanly separated.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        # request.auth is set to the APIKey instance by APIKeyAuthentication
        return isinstance(getattr(request, "auth", None), APIKey)
