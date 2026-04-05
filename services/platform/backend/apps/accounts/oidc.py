"""
Authentik OIDC token validation for Django REST Framework.

Validates Bearer tokens issued by Authentik against its JWKS endpoint.
Creates or updates local User records from token claims on each request.
"""

import logging
import threading
from typing import Any

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from jwt import PyJWKClient
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

logger = logging.getLogger(__name__)
User = get_user_model()

# Thread-safe JWKS client singleton.
_jwks_client: PyJWKClient | None = None
_jwks_lock = threading.Lock()


def _get_jwks_client() -> PyJWKClient:
    """Get or create the JWKS client singleton (thread-safe)."""
    global _jwks_client
    if _jwks_client is not None:
        return _jwks_client
    with _jwks_lock:
        if _jwks_client is None:
            jwks_url = settings.OIDC_JWKS_URL
            if not jwks_url:
                raise AuthenticationFailed("OIDC_JWKS_URL not configured")
            _jwks_client = PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)
        return _jwks_client


class _OIDCTokenError(Exception):
    """Token is not an Authentik OIDC JWT (e.g. wrong key/format).

    Distinguished from tokens that ARE Authentik JWTs but are invalid
    (expired, wrong audience, etc.), which raise AuthenticationFailed.
    """


def decode_oidc_token(token: str) -> dict[str, Any]:
    """Decode and validate an Authentik OIDC access token.

    Verifies: signature (RS256 via JWKS), issuer, audience, expiry.
    Returns the decoded token payload.

    Raises:
        _OIDCTokenError: token is not an Authentik JWT (wrong key, bad format).
            Callers should fall through to the next authenticator.
        AuthenticationFailed: token IS an Authentik JWT but is invalid
            (expired, wrong audience, wrong issuer). Should be a hard 401.
    """
    client = _get_jwks_client()

    try:
        signing_key = client.get_signing_key_from_jwt(token)
    except (jwt.exceptions.PyJWKClientError, jwt.exceptions.DecodeError) as e:
        # Token doesn't match any key in Authentik's JWKS — not an Authentik token.
        raise _OIDCTokenError(str(e)) from e

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
        sub               → username (stable Authentik identity, used as lookup key)
        preferred_username → stored but not used for lookup (mutable in Authentik)
        email             → email
        given_name        → first_name
        family_name       → last_name
        groups            → first matching Organization

    The lookup is always by `sub` to avoid creating duplicate users when
    `preferred_username` changes in Authentik.
    """
    from apps.organizations.models import Organization

    sub = payload.get("sub")
    if not sub:
        raise AuthenticationFailed("Token missing 'sub' claim")

    email = payload.get("email", "")
    first_name = payload.get("given_name", "")
    last_name = payload.get("family_name", "")
    groups = payload.get("groups", [])

    # Resolve organization from groups BEFORE creating the user,
    # because User.save() calls full_clean() which requires organization
    # for non-superuser accounts.
    org = None
    if groups:
        for group_name in groups:
            org = Organization.objects.filter(name__iexact=group_name).first()
            if org:
                break

    if org is None:
        raise AuthenticationFailed(
            f"No matching organization for OIDC groups: {groups}. "
            f"Create a matching Organization in Django first."
        )

    user, created = User.objects.get_or_create(
        username=sub,
        defaults={
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "organization": org,
        },
    )

    if created:
        user.set_unusable_password()
        # save() already called by get_or_create, but set_unusable_password
        # needs a save — use update_fields to avoid full_clean.
        user.save(update_fields=["password"])

    # Update user fields from token claims on every request.
    # Use update_fields to avoid triggering full_clean() on unrelated fields.
    update_fields: list[str] = []
    if user.email != email and email:
        user.email = email
        update_fields.append("email")
    if user.first_name != first_name and first_name:
        user.first_name = first_name
        update_fields.append("first_name")
    if user.last_name != last_name and last_name:
        user.last_name = last_name
        update_fields.append("last_name")
    if user.organization_id != org.id:
        user.organization = org
        update_fields.append("organization_id")

    if update_fields:
        user.save(update_fields=update_fields)

    if created:
        logger.info(
            "Created user '%s' from OIDC (org=%s)",
            sub,
            org.name,
        )

    return user


class AuthentikOIDCAuthentication(BaseAuthentication):
    """DRF authentication class for Authentik OIDC access tokens.

    Validates Bearer tokens against Authentik's JWKS endpoint and
    creates/updates local User records from token claims.

    Behavior with multiple auth backends:
    - Token doesn't match Authentik JWKS → returns None (next backend tries)
    - Token matches Authentik but is invalid (expired, wrong aud) → raises 401
    - Token valid → returns (user, payload)
    """

    def authenticate(self, request: Request) -> tuple[Any, dict] | None:
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[7:]
        if not token:
            return None

        # Only attempt OIDC validation if fully configured
        if not getattr(settings, "OIDC_JWKS_URL", ""):
            return None
        if not getattr(settings, "OIDC_AUDIENCE", ""):
            return None

        try:
            payload = decode_oidc_token(token)
        except _OIDCTokenError:
            # Not an Authentik token (wrong key/format) — let next authenticator try.
            return None
        # AuthenticationFailed propagates as 401 (token IS Authentik but invalid).

        user = get_or_create_user_from_oidc(payload)

        if not user.is_active:
            raise AuthenticationFailed("User account is disabled")

        return (user, payload)

    def authenticate_header(self, request: Request) -> str:
        return "Bearer"
