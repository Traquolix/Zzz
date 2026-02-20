"""
Tests for authentication endpoints.
"""

import pytest
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status

from apps.shared.models import AuditLog
from tests.factories import UserFactory


pytestmark = pytest.mark.django_db


class TestLogin:
    url = '/api/auth/login'

    def test_login_success(self, api_client, admin_user):
        response = api_client.post(self.url, {
            'username': admin_user.username,
            'password': 'testpass123',
        })
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert 'token' in data
        assert data['username'] == admin_user.username
        assert isinstance(data['allowedWidgets'], list)
        assert isinstance(data['allowedLayers'], list)

    def test_login_sets_refresh_cookie(self, api_client, admin_user):
        response = api_client.post(self.url, {
            'username': admin_user.username,
            'password': 'testpass123',
        })
        assert response.status_code == status.HTTP_200_OK
        assert 'sequoia_refresh' in response.cookies

    def test_login_wrong_password(self, api_client, admin_user):
        response = api_client.post(self.url, {
            'username': admin_user.username,
            'password': 'wrongpassword',
        })
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert 'Invalid credentials' in response.json()['detail']

    def test_login_nonexistent_user(self, api_client):
        response = api_client.post(self.url, {
            'username': 'doesnotexist',
            'password': 'password',
        })
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_missing_fields(self, api_client):
        response = api_client.post(self.url, {})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_login_inactive_user(self, api_client, org):
        user = UserFactory(organization=org, username='inactive', is_active=False)
        response = api_client.post(self.url, {
            'username': 'inactive',
            'password': 'testpass123',
        })
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_creates_audit_log(self, api_client, admin_user):
        api_client.post(self.url, {
            'username': admin_user.username,
            'password': 'testpass123',
        })
        assert AuditLog.objects.filter(
            action=AuditLog.Action.LOGIN_SUCCESS,
            user=admin_user,
        ).exists()

    def test_failed_login_creates_audit_log(self, api_client, admin_user):
        api_client.post(self.url, {
            'username': admin_user.username,
            'password': 'wrongpassword',
        })
        assert AuditLog.objects.filter(
            action=AuditLog.Action.LOGIN_FAILED,
        ).exists()

    def test_account_lockout(self, api_client, admin_user):
        cache.clear()
        # Make 5 failed attempts
        for _ in range(5):
            api_client.post(self.url, {
                'username': admin_user.username,
                'password': 'wrong',
            })

        # 6th attempt should be blocked even with correct password
        response = api_client.post(self.url, {
            'username': admin_user.username,
            'password': 'testpass123',
        })
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert 'locked' in response.json()['detail'].lower()

    def test_lockout_clears_on_success_before_threshold(self, api_client, admin_user):
        cache.clear()
        # 3 failed attempts
        for _ in range(3):
            api_client.post(self.url, {
                'username': admin_user.username,
                'password': 'wrong',
            })

        # Successful login clears counter
        response = api_client.post(self.url, {
            'username': admin_user.username,
            'password': 'testpass123',
        })
        assert response.status_code == status.HTTP_200_OK

        # Another failed attempt should start from 0
        api_client.post(self.url, {
            'username': admin_user.username,
            'password': 'wrong',
        })
        # Should still be able to login (only 1 failed attempt)
        response = api_client.post(self.url, {
            'username': admin_user.username,
            'password': 'testpass123',
        })
        assert response.status_code == status.HTTP_200_OK

    def test_login_returns_admin_widgets(self, api_client, admin_user):
        response = api_client.post(self.url, {
            'username': admin_user.username,
            'password': 'testpass123',
        })
        data = response.json()
        assert 'map' in data['allowedWidgets']
        assert 'traffic_monitor' in data['allowedWidgets']
        assert 'incidents' in data['allowedWidgets']
        assert 'shm' in data['allowedWidgets']

    def test_login_returns_viewer_widgets(self, api_client, viewer_user):
        response = api_client.post(self.url, {
            'username': viewer_user.username,
            'password': 'testpass123',
        })
        data = response.json()
        assert 'map' in data['allowedWidgets']
        assert 'incidents' in data['allowedWidgets']
        assert 'traffic_monitor' not in data['allowedWidgets']


class TestVerify:
    url = '/api/auth/verify'

    def test_verify_authenticated(self, authenticated_client, admin_user):
        response = authenticated_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['valid'] is True
        assert data['username'] == admin_user.username
        assert isinstance(data['allowedWidgets'], list)
        assert isinstance(data['allowedLayers'], list)

    def test_verify_unauthenticated(self, api_client):
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestRefresh:
    url = '/api/auth/refresh'

    def test_refresh_with_valid_cookie(self, api_client, admin_user):
        # First login to get refresh cookie
        login_response = api_client.post('/api/auth/login', {
            'username': admin_user.username,
            'password': 'testpass123',
        })
        assert login_response.status_code == status.HTTP_200_OK

        # Use the refresh cookie to get a new access token
        response = api_client.post(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert 'token' in response.json()

    def test_refresh_without_cookie(self, api_client):
        response = api_client.post(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_refresh_with_invalid_cookie(self, api_client):
        api_client.cookies['sequoia_refresh'] = 'invalid-token-value'
        response = api_client.post(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestLogout:
    url = '/api/auth/logout'

    def test_logout_authenticated(self, api_client, admin_user):
        # Login first
        api_client.post('/api/auth/login', {
            'username': admin_user.username,
            'password': 'testpass123',
        })
        # Authenticate the client for logout
        api_client.force_authenticate(user=admin_user)

        response = api_client.post(self.url)
        assert response.status_code == status.HTTP_205_RESET_CONTENT

    def test_logout_unauthenticated(self, api_client):
        response = api_client.post(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_logout_clears_cookie(self, api_client, admin_user):
        # Login first
        api_client.post('/api/auth/login', {
            'username': admin_user.username,
            'password': 'testpass123',
        })
        api_client.force_authenticate(user=admin_user)
        response = api_client.post(self.url)
        # Cookie should be deleted (max-age=0)
        cookie = response.cookies.get('sequoia_refresh')
        if cookie:
            assert cookie['max-age'] == 0
