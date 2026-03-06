"""
WebSocket authentication middleware.

All connections start as AnonymousUser with _pending_auth=True.
The consumer handles message-based auth: send {"action": "authenticate", "token": "xxx"}
after connecting.

This is more secure than URL-based tokens which appear in server logs,
browser history, and proxy logs.

The get_user_from_token() function is used by the consumer for message-based auth.
"""

import logging

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken

logger = logging.getLogger("sequoia.realtime")
User = get_user_model()


@database_sync_to_async
def get_user_from_token(token_str):
    """Validate JWT access token and return the user, or AnonymousUser."""
    try:
        token = AccessToken(token_str)
        user_id = token.payload.get("user_id")
        if user_id is None:
            return AnonymousUser()
        user = User.objects.select_related("organization").get(id=user_id)
        if not user.is_active:
            return AnonymousUser()
        # Check org is active (mirrors IsActiveUser permission)
        if not user.is_superuser:
            org = getattr(user, "organization", None)
            if org is None or not org.is_active:
                return AnonymousUser()
        return user
    except Exception:
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """
    WebSocket JWT authentication middleware.

    All connections start unauthenticated. The consumer accepts the connection
    and waits for an 'authenticate' message with a valid JWT token.
    """

    async def __call__(self, scope, receive, send):
        scope["user"] = AnonymousUser()
        scope["_pending_auth"] = True
        return await super().__call__(scope, receive, send)
