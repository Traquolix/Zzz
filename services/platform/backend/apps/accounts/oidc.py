"""
Authentik OIDC token validation for Django REST Framework.

Validates Bearer tokens issued by Authentik against its JWKS endpoint.
Creates or updates local User records from token claims on each request.
"""

import logging
from typing import Any

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from jwt import PyJWKClient
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

logger = logging.getLogger("sequoia.accounts.oidc")
User = get_user_model()

# Module-level JWKS client — reused across requests, caches keys internally.
_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    """Get or create the JWKS client singleton."""
    global _jwks_client
    if _jwks_client is None:
        jwks_url = settings.OIDC_JWKS_URL
        if not jwks_url:
            raise AuthenticationFailed("OIDC_JWKS_URL not configured")
        _jwks_client = PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)
    return _jwks_client


def decode_oidc_token(token: str) -> dict[str, Any]:
    """Decode and validate an Authentik OIDC access token.

    Verifies: signature (RS256 via JWKS), issuer, audience, expiry.
    Returns the decoded token payload.

    Raises AuthenticationFailed on any validation failure.
    """
    client = _get_jwks_client()

    try:
        signing_key = client.get_signing_key_from_jwt(token)
    except jwt.exceptions.PyJWKClientError as e:
        raise AuthenticationFailed(f"Could not fetch signing key: {e}") from e

    try:
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.OIDC_ISSUER_URL,
            audience=settings.OIDC_AUDIENCE,
            options={
                "verify_signature": True,
                "verify_iss": True,
                "verify_aud": True,
                "verify_exp": True,
                "verify_iat": True,
            },
        )
    except jwt.ExpiredSignatureError as e:
        raise AuthenticationFailed("Token expired") from e
    except jwt.InvalidIssuerError as e:
        raise AuthenticationFailed("Invalid token issuer") from e
    except jwt.InvalidAudienceError as e:
        raise AuthenticationFailed("Invalid token audience") from e
    except jwt.InvalidTokenError as e:
        raise AuthenticationFailed(f"Invalid token: {e}") from e

    return payload


def get_or_create_user_from_oidc(payload: dict[str, Any]) -> Any:
    """Look up or create a local Django User from OIDC token claims.

    Claim mapping:
        sub               → looked up first, used as fallback username
        preferred_username → username (if present)
        email             → email
        given_name        → first_name
        name              → last_name (family name, or full name as fallback)
        groups            → first matching Organization
    """
    from apps.organizations.models import Organization

    sub = payload.get("sub")
    if not sub:
        raise AuthenticationFailed("Token missing 'sub' claim")

    username = payload.get("preferred_username") or sub
    email = payload.get("email", "")
    first_name = payload.get("given_name", "")
    last_name = payload.get("family_name", payload.get("name", ""))
    groups = payload.get("groups", [])

    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
        },
    )

    if created:
        user.set_unusable_password()

    # Update user fields from token claims on every login
    changed = False
    if user.email != email and email:
        user.email = email
        changed = True
    if user.first_name != first_name and first_name:
        user.first_name = first_name
        changed = True
    if user.last_name != last_name and last_name:
        user.last_name = last_name
        changed = True

    # Map first matching group to Organization
    if groups:
        org = None
        for group_name in groups:
            org = Organization.objects.filter(name__iexact=group_name).first()
            if org:
                break
        if org and user.organization_id != org.id:
            user.organization = org
            changed = True

    if changed or created:
        user.save()

    if created:
        logger.info(
            "Created user '%s' from OIDC (org=%s)",
            username,
            user.organization.name if user.organization else "none",
        )

    return user


class AuthentikOIDCAuthentication(BaseAuthentication):
    """DRF authentication class for Authentik OIDC access tokens.

    Validates Bearer tokens against Authentik's JWKS endpoint and
    creates/updates local User records from token claims.

    Sits alongside existing authentication classes — if the token
    is not a valid Authentik JWT, returns None to let the next
    authenticator try (e.g. SimpleJWT, API key).
    """

    def authenticate(self, request: Request) -> tuple[Any, dict] | None:
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[7:]
        if not token:
            return None

        # Only attempt OIDC validation if configured
        if not getattr(settings, "OIDC_JWKS_URL", ""):
            return None

        try:
            payload = decode_oidc_token(token)
        except AuthenticationFailed:
            # Not a valid Authentik token — let next authenticator try.
            # This allows SimpleJWT tokens to pass through during migration.
            return None

        user = get_or_create_user_from_oidc(payload)

        if not user.is_active:
            raise AuthenticationFailed("User account is disabled")

        return (user, payload)

    def authenticate_header(self, request: Request) -> str:
        return "Bearer"
