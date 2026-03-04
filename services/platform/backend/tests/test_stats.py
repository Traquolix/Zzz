"""
Tests for stats endpoint (ClickHouse mocked).
"""

import pytest
from unittest.mock import patch
from rest_framework import status

from apps.fibers.models import FiberAssignment
from apps.shared.exceptions import ClickHouseUnavailableError


pytestmark = pytest.mark.django_db


class TestStats:
    url = '/api/stats'

    @patch('apps.monitoring.views.query_scalar')
    def test_stats_with_clickhouse(self, mock_scalar, authenticated_client, org):
        FiberAssignment.objects.create(organization=org, fiber_id='carros')

        mock_scalar.side_effect = [
            3,       # fiber_count
            2500,    # total_channels
            5,       # active_incidents
            42.5,    # detections per second
            17,      # active_vehicles (from count_hires)
        ]

        response = authenticated_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data['fiberCount'] == 3
        assert data['totalChannels'] == 2500
        assert data['activeIncidents'] == 5
        assert data['detectionsPerSecond'] == 42.5
        assert data['activeVehicles'] == 17
        assert 'systemUptime' in data

    @patch('apps.monitoring.views.query_scalar')
    def test_stats_clickhouse_unavailable(self, mock_scalar, authenticated_client, org):
        FiberAssignment.objects.create(organization=org, fiber_id='carros')
        mock_scalar.side_effect = ClickHouseUnavailableError("Connection refused")

        response = authenticated_client.get(self.url)
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        assert data['code'] == 'analytics_unavailable'

    def test_stats_no_fiber_assignments_returns_zeros(self, authenticated_client):
        """User with no fiber assignments gets zero stats."""
        response = authenticated_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['fiberCount'] == 0
        assert data['totalChannels'] == 0

    def test_stats_unauthenticated(self, api_client):
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
