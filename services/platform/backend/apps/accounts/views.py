"""
Authentication views.

Implements JWT RS256 login with httpOnly refresh cookie,
account lockout, token refresh, verify, and logout.
"""

import contextlib
import logging
from typing import Any

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.core.cache import cache
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as s
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.serializers import LoginSerializer
from apps.shared.audit import AuditService
from apps.shared.models import AuditLog

logger = logging.getLogger("sequoia")
User = get_user_model()

# Account lockout settings
LOCKOUT_MAX_ATTEMPTS = 5
LOCKOUT_DURATION = 15 * 60  # 15 minutes
LOCKOUT_CACHE_PREFIX = "login_fail_"


def _set_refresh_cookie(response: Response, refresh_token_str: str) -> None:
    """Set the refresh token as an httpOnly cookie on the response."""
    response.set_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        value=refresh_token_str,
        httponly=settings.REFRESH_TOKEN_COOKIE_HTTPONLY,
        secure=getattr(settings, "REFRESH_TOKEN_COOKIE_SECURE", True),
        samesite=settings.REFRESH_TOKEN_COOKIE_SAMESITE,
        path=settings.REFRESH_TOKEN_COOKIE_PATH,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
    )


def _delete_refresh_cookie(response: Response) -> None:
    """Delete the refresh token cookie from the response."""
    response.delete_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        path=settings.REFRESH_TOKEN_COOKIE_PATH,
    )


def _set_session_hint(response: Response) -> None:
    """Set a JS-readable cookie so the frontend knows a session exists."""
    response.set_cookie(
        key=settings.SESSION_HINT_COOKIE_NAME,
        value="1",
        httponly=False,
        secure=getattr(settings, "REFRESH_TOKEN_COOKIE_SECURE", True),
        samesite=settings.REFRESH_TOKEN_COOKIE_SAMESITE,
        path="/",
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
    )


def _delete_session_hint(response: Response) -> None:
    """Delete the session hint cookie."""
    response.delete_cookie(
        key=settings.SESSION_HINT_COOKIE_NAME,
        path="/",
    )


class LoginView(APIView):
    """
    Login endpoint — authenticates with username/password.

    Returns access token + user info in JSON body.
    Sets refresh token as httpOnly cookie.
    Implements account lockout after repeated failed attempts.
    Uses AnonRateThrottle for rate limiting to prevent brute force attacks.
    """

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes = [AnonRateThrottle]

    @staticmethod
    def _lockout_key(username: str) -> str:
        return f"{LOCKOUT_CACHE_PREFIX}{username.lower().strip()}"

    @extend_schema(
        request=LoginSerializer,
        responses={
            200: inline_serializer(
                "LoginResponse",
                fields={
                    "token": s.CharField(),
                    "username": s.CharField(),
                    "allowedWidgets": s.ListField(child=s.CharField()),
                    "allowedLayers": s.ListField(child=s.CharField()),
                },
            )
        },
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        username = serializer.validated_data["username"]
        password = serializer.validated_data["password"]

        # Check lockout
        cache_key = self._lockout_key(username)
        attempts = cache.get(cache_key, 0)
        if attempts >= LOCKOUT_MAX_ATTEMPTS:
            logger.warning("Login blocked for locked account: %s", username)
            return Response(
                {
                    "detail": "Account temporarily locked. Try again later.",
                    "code": "account_locked",
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Authenticate
        user = authenticate(request, username=username, password=password)

        if user is not None and user.is_active:
            # Success — clear lockout, generate tokens
            cache.delete(cache_key)

            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)

            response = Response(
                {
                    "token": access_token,
                    "username": user.username,
                    "allowedWidgets": user.allowed_widgets,
                    "allowedLayers": user.allowed_layers,
                    "organizationId": str(user.organization_id) if user.organization_id else None,
                    "organizationName": user.organization.name if user.organization else None,
                    "role": user.role,
                    "isSuperuser": user.is_superuser,
                }
            )
            _set_refresh_cookie(response, str(refresh))
            _set_session_hint(response)

            AuditService.log(
                request=request,
                action=AuditLog.Action.LOGIN_SUCCESS,  # type: ignore[arg-type]  # TextChoices is str at runtime; no django-stubs
                object_type="User",
                object_id=str(user.id),
                changes={"username": username},
                user=user,
                organization=user.organization,
            )
            return response
        else:
            # Failed — increment lockout counter
            attempts = cache.get(cache_key, 0)
            cache.set(cache_key, attempts + 1, timeout=LOCKOUT_DURATION)
            remaining = LOCKOUT_MAX_ATTEMPTS - (attempts + 1)

            if remaining <= 0:
                logger.warning(
                    "Account locked after %d failed attempts: %s", LOCKOUT_MAX_ATTEMPTS, username
                )
            elif remaining <= 2:
                logger.info(
                    "Login attempt %d/%d for: %s", attempts + 1, LOCKOUT_MAX_ATTEMPTS, username
                )

            # Audit the failed attempt
            try:
                target_user = User.objects.select_related("organization").get(username=username)
            except User.DoesNotExist:
                target_user = None

            AuditService.log(
                request=request,
                action=AuditLog.Action.LOGIN_FAILED,  # type: ignore[arg-type]  # TextChoices is str at runtime; no django-stubs
                changes={"username": username, "attempt": attempts + 1},
                user=target_user,
                organization=target_user.organization if target_user else None,
            )

            return Response(
                {"detail": "Invalid credentials.", "code": "invalid_credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )


class VerifyView(APIView):
    """
    Verify the current access token and return user info.
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


class CookieTokenRefreshView(APIView):
    """
    Refresh access token using the refresh token from httpOnly cookie.
    Returns new access token in body and rotates refresh cookie.

    Uses rate limiting to prevent brute force attacks on token refresh.
    """

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"  # Same aggressive rate limit as login

    @extend_schema(
        request=None,
        responses={
            200: inline_serializer(
                "RefreshResponse",
                fields={
                    "token": s.CharField(),
                },
            )
        },
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        refresh_token_str = request.COOKIES.get(settings.REFRESH_TOKEN_COOKIE_NAME)
        if not refresh_token_str:
            return Response(
                {"detail": "Refresh token missing.", "code": "refresh_missing"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            token = RefreshToken(refresh_token_str)
            access = str(token.access_token)
            response = Response({"token": access})

            # Rotate refresh token if configured
            if settings.SIMPLE_JWT.get("ROTATE_REFRESH_TOKENS", False):
                if settings.SIMPLE_JWT.get("BLACKLIST_AFTER_ROTATION", False):
                    with contextlib.suppress(AttributeError):
                        token.blacklist()
                user = User.objects.get(id=token.payload["user_id"])
                new_token = RefreshToken.for_user(user)
                _set_refresh_cookie(response, str(new_token))
            else:
                _set_refresh_cookie(response, refresh_token_str)

            _set_session_hint(response)
            return response
        except (TokenError, User.DoesNotExist):
            response = Response(
                {"detail": "Invalid or expired token.", "code": "invalid_token"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            _delete_refresh_cookie(response)
            _delete_session_hint(response)
            return response


class LogoutView(APIView):
    """
    Logout — blacklists the refresh token from cookie and clears it.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={205: None}, tags=["auth"])
    def post(self, request: Request) -> Response:
        refresh_token = request.COOKIES.get(settings.REFRESH_TOKEN_COOKIE_NAME)
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except TokenError:
                pass
        response = Response(status=status.HTTP_205_RESET_CONTENT)
        _delete_refresh_cookie(response)
        _delete_session_hint(response)
        return response
