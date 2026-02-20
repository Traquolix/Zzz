"""
Tests for health check endpoints.
"""

from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status


pytestmark = pytest.mark.django_db


class TestHealthCheck:
    def test_health_check(self, api_client):
        response = api_client.get('/api/health')
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {'status': 'ok'}

    def test_health_check_no_auth_required(self, api_client):
        """Health check should work without authentication."""
        response = api_client.get('/api/health')
        assert response.status_code == status.HTTP_200_OK


class TestReadinessCheck:
    @patch('apps.shared.clickhouse.get_client')
    def test_readiness_check(self, mock_get_client, api_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        response = api_client.get('/api/health/ready')
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['status'] == 'ready'
        assert data['checks']['database'] == 'ok'
        assert data['checks']['clickhouse'] == 'ok'

    @patch('apps.shared.clickhouse.get_client')
    def test_readiness_no_auth_required(self, mock_get_client, api_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        response = api_client.get('/api/health/ready')
        assert response.status_code == status.HTTP_200_OK

    @patch('apps.shared.clickhouse.get_client')
    def test_readiness_degraded_when_clickhouse_down(self, mock_get_client, api_client):
        mock_get_client.side_effect = Exception('Connection refused')
        response = api_client.get('/api/health/ready')
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        assert data['status'] == 'degraded'
        assert data['checks']['clickhouse'] == 'unavailable'
