"""
Tests for user preferences endpoints.
"""

import pytest
from rest_framework import status

from apps.preferences.models import UserPreferences


pytestmark = pytest.mark.django_db


class TestGetPreferences:
    url = '/api/user/preferences'

    def test_get_empty_preferences(self, authenticated_client):
        response = authenticated_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['dashboard'] == {}
        assert data['map'] == {}

    def test_get_existing_preferences(self, authenticated_client, admin_user):
        UserPreferences.objects.create(
            user=admin_user,
            dashboard={'layouts': {'lg': []}},
            map_config={'center': [7.26, 43.7]},
        )
        response = authenticated_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['dashboard']['layouts'] == {'lg': []}
        assert data['map']['center'] == [7.26, 43.7]

    def test_get_preferences_unauthenticated(self, api_client):
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestPutPreferences:
    url = '/api/user/preferences'

    def test_update_dashboard(self, authenticated_client, admin_user):
        dashboard_data = {
            'layouts': {'lg': [{'i': 'map', 'x': 0, 'y': 0, 'w': 6, 'h': 4}]},
            'widgets': {'map': {'visible': True}},
        }
        response = authenticated_client.put(
            self.url,
            {'dashboard': dashboard_data},
            format='json',
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['dashboard'] == dashboard_data

        # Verify persisted
        prefs = UserPreferences.objects.get(user=admin_user)
        assert prefs.dashboard == dashboard_data

    def test_update_map(self, authenticated_client, admin_user):
        map_data = {
            'landmarks': [{'channel': 10, 'name': 'Test'}],
            'layerVisibility': {'fibers': True, 'heatmap': False},
        }
        response = authenticated_client.put(
            self.url,
            {'map': map_data},
            format='json',
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['map'] == map_data

    def test_update_both(self, authenticated_client, admin_user):
        payload = {
            'dashboard': {'test': True},
            'map': {'zoom': 12},
        }
        response = authenticated_client.put(self.url, payload, format='json')
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['dashboard'] == {'test': True}
        assert data['map'] == {'zoom': 12}

    def test_partial_update_preserves_other(self, authenticated_client, admin_user):
        # Set initial preferences
        authenticated_client.put(
            self.url,
            {'dashboard': {'a': 1}, 'map': {'b': 2}},
            format='json',
        )

        # Update only dashboard
        response = authenticated_client.put(
            self.url,
            {'dashboard': {'a': 99}},
            format='json',
        )
        data = response.json()
        assert data['dashboard'] == {'a': 99}
        assert data['map'] == {'b': 2}  # Preserved

    def test_preferences_isolated_per_user(self, admin_user, viewer_user):
        from rest_framework.test import APIClient

        # Admin sets preferences with a dedicated client
        admin_api = APIClient()
        admin_api.force_authenticate(user=admin_user)
        admin_api.put(
            self.url,
            {'dashboard': {'admin': True}},
            format='json',
        )

        # Viewer gets empty preferences with a separate client
        viewer_api = APIClient()
        viewer_api.force_authenticate(user=viewer_user)
        response = viewer_api.get(self.url)
        data = response.json()
        assert data['dashboard'] == {}

    def test_update_preferences_unauthenticated(self, api_client):
        response = api_client.put(self.url, {'dashboard': {}}, format='json')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
