"""
Tests for health check endpoints.
"""

from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db


class TestHealthCheck:
    def test_health_check(self, api_client):
        response = api_client.get("/api/health")
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "ok"}

    def test_health_check_no_auth_required(self, api_client):
        """Health check should work without authentication."""
        response = api_client.get("/api/health")
        assert response.status_code == status.HTTP_200_OK


class TestReadinessCheck:
    """
    Readiness check verifies database, clickhouse, cache, and kafka.
    All four critical services must return 'ok' for a 200.
    """

    @patch("apps.shared.clickhouse.health")
    @patch("apps.shared.clickhouse.get_client")
    def test_readiness_clickhouse_ok(self, mock_get_client, mock_ch_health, api_client):
        """When clickhouse is healthy, its check returns 'ok'."""
        mock_ch_health.return_value = {
            "consecutive_failures": 0,
            "in_cooldown": False,
            "last_failure": 0,
        }
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        response = api_client.get("/api/health/ready")
        data = response.json()
        assert data["checks"]["clickhouse"] == "ok"
        assert data["checks"]["database"] == "ok"

    @patch("apps.shared.clickhouse.health")
    @patch("apps.shared.clickhouse.get_client")
    def test_readiness_no_auth_required(self, mock_get_client, mock_ch_health, api_client):
        mock_ch_health.return_value = {
            "consecutive_failures": 0,
            "in_cooldown": False,
            "last_failure": 0,
        }
        mock_get_client.return_value = MagicMock()
        response = api_client.get("/api/health/ready")
        # Endpoint is accessible without authentication (no 401/403)
        assert response.status_code in (200, 503)

    @patch("apps.shared.clickhouse.health")
    @patch("apps.shared.clickhouse.get_client")
    def test_readiness_degraded_when_clickhouse_in_cooldown(
        self, mock_get_client, mock_ch_health, api_client
    ):
        """Circuit breaker in cooldown -> clickhouse 'unavailable'."""
        mock_ch_health.return_value = {
            "consecutive_failures": 5,
            "in_cooldown": True,
            "last_failure": 0,
        }
        response = api_client.get("/api/health/ready")
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        assert data["status"] == "degraded"
        assert data["checks"]["clickhouse"] == "unavailable"

    @patch("apps.shared.clickhouse.health")
    @patch("apps.shared.clickhouse.get_client")
    def test_readiness_degraded_when_clickhouse_query_fails(
        self, mock_get_client, mock_ch_health, api_client
    ):
        """Even if circuit breaker is clear, a query failure marks clickhouse unavailable."""
        mock_ch_health.return_value = {
            "consecutive_failures": 0,
            "in_cooldown": False,
            "last_failure": 0,
        }
        mock_get_client.side_effect = Exception("Connection refused")
        response = api_client.get("/api/health/ready")
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        assert data["checks"]["clickhouse"] == "unavailable"

    def test_readiness_returns_all_check_keys(self, api_client):
        """Response always contains all check keys regardless of status."""
        response = api_client.get("/api/health/ready")
        data = response.json()
        assert "checks" in data
        for key in ("database", "clickhouse", "cache", "kafka"):
            assert key in data["checks"]
