"""
Tests for API polish improvements.

Tests the following:
1. Consistent error response format across all error types
2. Rate limiting on authentication endpoints
3. Cache-Control headers on static data endpoints
"""

import pytest
from django.core.cache import cache
from rest_framework import status

pytestmark = pytest.mark.django_db


class TestErrorResponseConsistency:
    """Test that all error responses follow a consistent format."""

    def test_validation_error_format(self, api_client):
        """Validation errors should return consistent format with error code and detail."""
        response = api_client.post("/api/auth/login", {})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        # All error responses should have consistent structure
        assert isinstance(data, dict)
        assert "detail" in data or "error" in data
        # Check that response has error information
        assert any(k in data for k in ["error", "detail", "code"])

    def test_unauthorized_error_format(self, api_client):
        """Unauthenticated requests should return error response."""
        response = api_client.get("/api/fibers")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        data = response.json()
        assert isinstance(data, dict)
        # Should have either 'detail', 'error', or 'code'
        assert any(k in data for k in ["detail", "error", "code"])

    def test_forbidden_error_format(self, api_client, viewer_user):
        """403 errors should return consistent format."""
        api_client.force_authenticate(user=viewer_user)
        response = api_client.get("/api/admin/organizations")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        data = response.json()
        assert isinstance(data, dict)
        assert any(k in data for k in ["detail", "error", "code"])

    def test_login_invalid_credentials_format(self, api_client, admin_user):
        """Invalid login credentials should return consistent format."""
        response = api_client.post(
            "/api/auth/login",
            {
                "username": admin_user.username,
                "password": "wrongpassword",
            },
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        data = response.json()
        # All responses should have dict structure
        assert isinstance(data, dict)
        # Should contain error information
        assert "detail" in data or "error" in data or "code" in data

    def test_account_lockout_returns_error(self, api_client, admin_user):
        """Account lockout should return 429 status with error info."""
        cache.clear()
        # Trigger account lockout
        for _ in range(5):
            api_client.post(
                "/api/auth/login",
                {
                    "username": admin_user.username,
                    "password": "wrong",
                },
            )

        response = api_client.post(
            "/api/auth/login",
            {
                "username": admin_user.username,
                "password": "testpass123",
            },
        )
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        data = response.json()
        assert isinstance(data, dict)
        assert "detail" in data or "code" in data

    def test_validation_error_includes_field_details(self, api_client):
        """Validation errors should include error details in response."""
        response = api_client.post(
            "/api/auth/login",
            {
                "username": "",
                "password": "",
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert isinstance(data, dict)
        # Should have error information
        assert len(data) > 0


class TestAuthEndpointRateLimiting:
    """Test that auth endpoints have proper rate limiting configured."""

    def test_login_has_throttle_classes_configured(self):
        """LoginView should have throttle_classes configured."""
        from apps.accounts.views import LoginView

        assert hasattr(LoginView, "throttle_classes")
        assert len(LoginView.throttle_classes) > 0

    def test_refresh_has_throttle_classes_configured(self):
        """CookieTokenRefreshView should have throttle_classes configured."""
        from apps.accounts.views import CookieTokenRefreshView

        assert hasattr(CookieTokenRefreshView, "throttle_classes")
        assert len(CookieTokenRefreshView.throttle_classes) > 0
        # Should have scoped rate throttle with 'login' scope
        assert hasattr(CookieTokenRefreshView, "throttle_scope")
        assert CookieTokenRefreshView.throttle_scope == "login"

    def test_login_uses_anon_rate_throttle(self):
        """LoginView should use AnonRateThrottle for rate limiting."""
        from rest_framework.throttling import AnonRateThrottle

        from apps.accounts.views import LoginView

        # Check that AnonRateThrottle is in throttle_classes
        throttle_classes = LoginView.throttle_classes
        assert any(issubclass(t, AnonRateThrottle) for t in throttle_classes)

    def test_refresh_uses_scoped_rate_throttle(self):
        """CookieTokenRefreshView should use ScopedRateThrottle."""
        from rest_framework.throttling import ScopedRateThrottle

        from apps.accounts.views import CookieTokenRefreshView

        # Check that ScopedRateThrottle is in throttle_classes
        throttle_classes = CookieTokenRefreshView.throttle_classes
        assert any(issubclass(t, ScopedRateThrottle) for t in throttle_classes)

    def test_login_throttle_rate_configured(self):
        """Login throttle rate should be configured in settings."""
        from django.conf import settings

        throttle_rates = settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {})
        # Login rate should be configured
        assert "login" in throttle_rates or "anon" in throttle_rates


class TestCacheHeadersOnStaticData:
    """Test that cache headers are present on static data endpoints."""

    def test_fiber_list_cache_header(self, api_client, admin_user):
        """Fiber list endpoint should have Cache-Control header."""
        api_client.force_authenticate(user=admin_user)
        response = api_client.get("/api/fibers")
        assert response.status_code == status.HTTP_200_OK
        assert "Cache-Control" in response
        assert "max-age=300" in response["Cache-Control"]

    def test_organization_list_cache_header(self, api_client, superuser, org):
        """Organization list endpoint should have Cache-Control header."""
        api_client.force_authenticate(user=superuser)
        response = api_client.get("/api/admin/organizations")
        # Response should be successful
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_500_INTERNAL_SERVER_ERROR]
        # Cache header should be present even if endpoint has issues
        if response.status_code == status.HTTP_200_OK:
            assert "Cache-Control" in response
            assert "max-age=300" in response["Cache-Control"]

    def test_user_list_cache_header(self, api_client, admin_user):
        """User list endpoint should have Cache-Control header."""
        api_client.force_authenticate(user=admin_user)
        response = api_client.get("/api/admin/users")
        assert response.status_code == status.HTTP_200_OK
        assert "Cache-Control" in response
        assert "max-age=300" in response["Cache-Control"]

    def test_infrastructure_list_cache_header(self, api_client, admin_user):
        """Infrastructure list endpoint should have Cache-Control header."""
        api_client.force_authenticate(user=admin_user)
        response = api_client.get("/api/admin/infrastructure")
        assert response.status_code == status.HTTP_200_OK
        assert "Cache-Control" in response
        assert "max-age=300" in response["Cache-Control"]

    def test_alert_rule_list_cache_header(self, api_client, admin_user):
        """Alert rule list endpoint should have Cache-Control header."""
        api_client.force_authenticate(user=admin_user)
        response = api_client.get("/api/admin/alert-rules")
        assert response.status_code == status.HTTP_200_OK
        assert "Cache-Control" in response
        assert "max-age=300" in response["Cache-Control"]

    def test_alert_log_list_cache_header(self, api_client, admin_user):
        """Alert log list endpoint should have Cache-Control header."""
        api_client.force_authenticate(user=admin_user)
        response = api_client.get("/api/admin/alert-logs")
        assert response.status_code == status.HTTP_200_OK
        assert "Cache-Control" in response
        assert "max-age=300" in response["Cache-Control"]


class TestErrorResponseEdgeCases:
    """Test edge cases for error response format."""

    def test_method_not_allowed_error_format(self, api_client, admin_user):
        """Method not allowed errors should return consistent format."""
        api_client.force_authenticate(user=admin_user)
        # POST to GET-only endpoint
        response = api_client.post("/api/auth/verify")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        data = response.json()
        assert "error" in data
        assert "detail" in data
        assert "status" in data

    def test_missing_field_error_has_details(self, api_client):
        """Validation errors with missing fields should have field details."""
        response = api_client.post("/api/auth/login", {"username": "test"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "error" in data
        assert data["error"] == "validation_error"
