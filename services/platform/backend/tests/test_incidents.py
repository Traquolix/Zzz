"""
Tests for incidents endpoints (ClickHouse mocked).

The incident list view uses incident_service.query_recent which internally
calls apps.shared.clickhouse.query. We mock at the incident_service.query
level so the full transform pipeline runs.

The snapshot view calls apps.monitoring.views.query (from shared.clickhouse)
directly, so we mock there.
"""

import pytest
from datetime import datetime
from unittest.mock import patch
from rest_framework import status

from apps.fibers.models import FiberAssignment
from apps.shared.exceptions import ClickHouseUnavailableError


pytestmark = pytest.mark.django_db


class TestIncidentList:
    url = '/api/incidents'

    @patch('apps.monitoring.incident_service.query')
    def test_list_incidents(self, mock_query, authenticated_client, org):
        FiberAssignment.objects.create(organization=org, fiber_id='fiber-carros')
        FiberAssignment.objects.create(organization=org, fiber_id='fiber-promenade')
        mock_query.return_value = [
            {
                'incident_id': 'inc-001',
                'incident_type': 'accident',
                'severity': 'high',
                'fiber_id': 'fiber-carros',
                'channel_start': 150,
                'timestamp': datetime(2025, 6, 1, 12, 0, 0),
                'status': 'active',
                'duration_seconds': 300,
            },
            {
                'incident_id': 'inc-002',
                'incident_type': 'congestion',
                'severity': 'medium',
                'fiber_id': 'fiber-promenade',
                'channel_start': 80,
                'timestamp': datetime(2025, 6, 1, 11, 30, 0),
                'status': 'resolved',
                'duration_seconds': None,
            },
        ]

        response = authenticated_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        results = data['results']
        assert len(results) == 2

        inc = results[0]
        assert inc['id'] == 'inc-001'
        assert inc['type'] == 'accident'
        assert inc['severity'] == 'high'
        assert inc['fiberLine'] == 'fiber-carros:0'  # Normalized with directional suffix
        assert inc['channel'] == 150
        assert inc['status'] == 'active'
        assert inc['duration'] == 300_000  # Converted to ms

        inc2 = results[1]
        assert inc2['fiberLine'] == 'fiber-promenade:0'  # Normalized
        assert inc2['duration'] is None

        assert data['hasMore'] is False

    @patch('apps.monitoring.incident_service.query')
    def test_incidents_clickhouse_unavailable(self, mock_query, authenticated_client, org):
        FiberAssignment.objects.create(organization=org, fiber_id='fiber-carros')
        mock_query.side_effect = ClickHouseUnavailableError("Connection refused")

        response = authenticated_client.get(self.url)
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        assert data['code'] == 'clickhouse_unavailable'

    def test_incidents_unauthenticated(self, api_client):
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestIncidentSnapshot:

    @patch('apps.monitoring.views.query')
    def test_snapshot_found(self, mock_query, authenticated_client, org):
        FiberAssignment.objects.create(organization=org, fiber_id='fiber-carros')
        # First call returns incident details, second returns speed data
        mock_query.side_effect = [
            # Incident lookup
            [{
                'fiber_id': 'fiber-carros',
                'channel_start': 100,
                'channel_end': 110,
                'timestamp_ns': 1717200000000000000,
            }],
            # Detection hires data
            [
                {
                    'fiber_id': 'fiber-carros',
                    'ch': 105,
                    'speed': 85.0,
                    'direction': 1,
                    'vehicle_count': 1,
                    'n_cars': 1,
                    'n_trucks': 0,
                    'timestamp': 1717200000000,
                },
                {
                    'fiber_id': 'fiber-carros',
                    'ch': 106,
                    'speed': 72.5,
                    'direction': 2,
                    'vehicle_count': 1,
                    'n_cars': 0,
                    'n_trucks': 1,
                    'timestamp': 1717200001000,
                },
            ],
        ]

        response = authenticated_client.get('/api/incidents/inc-001/snapshot')
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data['incidentId'] == 'inc-001'
        assert data['fiberLine'] == 'fiber-carros:0'  # Normalized with directional suffix
        assert data['centerChannel'] == 105  # (100 + 110) // 2
        assert isinstance(data['capturedAt'], int)
        assert len(data['detections']) == 2

        det = data['detections'][0]
        assert det['fiberLine'] == 'fiber-carros:0'  # Normalized
        assert det['channel'] == 105
        assert det['speed'] == 85.0
        assert det['direction'] == 0  # Positive speed

        det2 = data['detections'][1]
        assert det2['speed'] == 72.5  # abs(-72.5)
        assert det2['direction'] == 1  # Negative speed

    @patch('apps.monitoring.views.query')
    def test_snapshot_incident_not_found(self, mock_query, authenticated_client):
        mock_query.return_value = []

        response = authenticated_client.get('/api/incidents/nonexistent/snapshot')
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch('apps.monitoring.views.query')
    def test_snapshot_clickhouse_unavailable(self, mock_query, authenticated_client):
        mock_query.side_effect = ClickHouseUnavailableError("Connection refused")

        response = authenticated_client.get('/api/incidents/inc-001/snapshot')
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_snapshot_unauthenticated(self, api_client):
        response = api_client.get('/api/incidents/inc-001/snapshot')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
