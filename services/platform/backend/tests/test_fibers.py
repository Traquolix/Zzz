"""
Tests for fibers endpoint (ClickHouse mocked).

Each physical cable is expanded into two directional fibers (direction 0 and 1).
Response is wrapped in a paginated envelope: {results, hasMore, limit}.
"""

import pytest
from unittest.mock import patch, MagicMock
from rest_framework import status

from apps.fibers.models import FiberAssignment
from apps.shared.exceptions import ClickHouseUnavailableError


pytestmark = pytest.mark.django_db


def _mock_fiber_result():
    """Create a mock ClickHouse query result with fiber data."""
    mock_result = MagicMock()
    mock_result.named_results.return_value = [
        {
            'fiber_id': 'fiber-carros',
            'fiber_name': 'Carros',
            'color': '#ff0000',
            'channel_coordinates': [
                (7.1, 43.7),
                (7.2, 43.8),
                (None, None),
                (7.3, 43.9),
            ],
            'landmark_labels': ['Start', None, None, 'End'],
        },
        {
            'fiber_id': 'fiber-promenade',
            'fiber_name': 'Promenade',
            'color': '#00ff00',
            'channel_coordinates': [(7.25, 43.69), (7.26, 43.70)],
            'landmark_labels': [None, None],
        },
    ]
    return mock_result


class TestFiberList:
    url = '/api/fibers'

    @patch('apps.fibers.views.get_client')
    def test_list_fibers(self, mock_get_client, authenticated_client, org):
        # Create fiber assignments so the org-scoped view returns results
        FiberAssignment.objects.create(organization=org, fiber_id='fiber-carros')
        FiberAssignment.objects.create(organization=org, fiber_id='fiber-promenade')

        mock_client = MagicMock()
        mock_client.query.return_value = _mock_fiber_result()
        mock_get_client.return_value = mock_client

        response = authenticated_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Paginated envelope
        assert 'results' in data
        assert 'hasMore' in data
        assert data['hasMore'] is False
        results = data['results']

        # 2 physical cables x 2 directions = 4 directional fibers
        assert len(results) == 4

        # Direction 0 of carros
        fiber0 = results[0]
        assert fiber0['id'] == 'fiber-carros:0'
        assert fiber0['parentFiberId'] == 'fiber-carros'
        assert fiber0['direction'] == 0
        assert fiber0['name'] == 'Carros'
        assert fiber0['color'] == '#ff0000'
        assert len(fiber0['coordinates']) == 4
        assert fiber0['coordinates'][0] == [7.1, 43.7]
        assert fiber0['coordinates'][2] == [None, None]  # Null coords preserved

        # Direction 1 of carros
        fiber1 = results[1]
        assert fiber1['id'] == 'fiber-carros:1'
        assert fiber1['parentFiberId'] == 'fiber-carros'
        assert fiber1['direction'] == 1

    @patch('apps.fibers.views.get_client')
    def test_fiber_landmarks(self, mock_get_client, authenticated_client, org):
        FiberAssignment.objects.create(organization=org, fiber_id='fiber-carros')
        FiberAssignment.objects.create(organization=org, fiber_id='fiber-promenade')

        mock_client = MagicMock()
        mock_client.query.return_value = _mock_fiber_result()
        mock_get_client.return_value = mock_client

        response = authenticated_client.get(self.url)
        results = response.json()['results']

        # Carros direction 0
        carros = results[0]
        assert carros['landmarks'] is not None
        assert len(carros['landmarks']) == 2
        assert carros['landmarks'][0] == {'channel': 0, 'name': 'Start'}
        assert carros['landmarks'][1] == {'channel': 3, 'name': 'End'}

        # Promenade direction 0 (index 2: carros:0, carros:1, promenade:0)
        promenade = results[2]
        assert promenade['landmarks'] is None  # No non-null labels

    @patch('apps.fibers.views.get_client')
    def test_fibers_no_assignments_returns_empty(self, mock_get_client, authenticated_client):
        """If user's org has no fiber assignments, return empty list."""
        response = authenticated_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['results'] == []
        assert data['hasMore'] is False

    @patch('apps.fibers.views.get_client')
    def test_fibers_clickhouse_unavailable(self, mock_get_client, authenticated_client, org):
        FiberAssignment.objects.create(organization=org, fiber_id='fiber-carros')
        mock_get_client.side_effect = ClickHouseUnavailableError("Connection refused")

        response = authenticated_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        # Falls back to JSON files (which likely don't exist in test env)
        data = response.json()
        assert 'results' in data
        assert data['hasMore'] is False

    def test_fibers_unauthenticated(self, api_client):
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
