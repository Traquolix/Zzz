"""
WebSocket authentication middleware.

All connections start as AnonymousUser with _pending_auth=True.
The consumer handles message-based auth: send {"action": "authenticate", "token": "xxx"}
after connecting.

This is more secure than URL-based tokens which appear in server logs,
browser history, and proxy logs.

The get_user_from_token() function is used by the consumer for message-based auth.
It validates Authentik OIDC access tokens via JWKS.
"""

import logging
from typing import Any

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.exceptions import AuthenticationFailed

logger = logging.getLogger(__name__)


@database_sync_to_async
def get_user_from_token(token_str: str) -> Any:
    """Validate an OIDC access token and return the user, or AnonymousUser.

    Uses the same OIDC validation as the REST API (AuthentikOIDCAuthentication):
    verifies signature via JWKS, checks issuer/audience/expiry, then looks up
    or creates the local User from token claims.
    """
    from apps.accounts.oidc import _OIDCTokenError, decode_oidc_token, get_or_create_user_from_oidc

    try:
        payload = decode_oidc_token(token_str)
        user = get_or_create_user_from_oidc(payload)
        if not user.is_active:
            return AnonymousUser()
        # Check org is active (mirrors IsActiveUser permission)
        if not user.is_superuser:
            org = getattr(user, "organization", None)
            if org is None or not org.is_active:
                return AnonymousUser()
        return user
    except (AuthenticationFailed, _OIDCTokenError, ObjectDoesNotExist):
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """
    WebSocket authentication middleware.

    All connections start unauthenticated. The consumer accepts the connection
    and waits for an 'authenticate' message with a valid OIDC token.
    """

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> Any:
        scope["user"] = AnonymousUser()
        scope["_pending_auth"] = True
        return await super().__call__(scope, receive, send)
