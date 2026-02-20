"""
WebSocket authentication middleware.

Supports two authentication methods:
1. Query string token (?token=xxx) - DEPRECATED, kept for backwards compatibility
2. Message-based auth (send {"action": "authenticate", "token": "xxx"} after connect)

Method 2 is preferred as tokens in URLs appear in server logs, browser history,
and proxy logs, creating security risks.

The consumer handles the 'authenticate' action and validates the token.
"""

import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken

logger = logging.getLogger('sequoia.realtime')
User = get_user_model()


@database_sync_to_async
def get_user_from_token(token_str):
    """Validate JWT access token and return the user, or AnonymousUser."""
    try:
        token = AccessToken(token_str)
        user_id = token.payload.get('user_id')
        if user_id is None:
            return AnonymousUser()
        user = User.objects.select_related('organization').get(id=user_id)
        if not user.is_active:
            return AnonymousUser()
        # Check org is active (mirrors IsActiveUser permission)
        if not user.is_superuser:
            org = getattr(user, 'organization', None)
            if org is None or not org.is_active:
                return AnonymousUser()
        return user
    except Exception:
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """
    Supports JWT authentication via query string (deprecated) or message.

    Query string auth (DEPRECATED - security risk):
        ws://host/?token=<jwt>

    Message-based auth (PREFERRED):
        Connect without token, then send: {"action": "authenticate", "token": "<jwt>"}

    If no token is provided at connect time, scope['user'] is AnonymousUser.
    The consumer accepts the connection and waits for an 'authenticate' message.
    """

    async def __call__(self, scope, receive, send):
        query_string = scope.get('query_string', b'').decode('utf-8')
        params = parse_qs(query_string)
        token_list = params.get('token', [])

        if token_list:
            # DEPRECATED: URL-based token auth (kept for backwards compatibility)
            logger.debug('WebSocket auth via URL token (deprecated)')
            scope['user'] = await get_user_from_token(token_list[0])
        else:
            # No token in URL - consumer will handle message-based auth
            scope['user'] = AnonymousUser()
            scope['_pending_auth'] = True  # Flag for consumer to expect auth message

        return await super().__call__(scope, receive, send)
