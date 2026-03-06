"""
Tests for API Key authentication and CRUD.

API keys provide programmatic access to the SequoIA platform.
Keys are hashed (SHA-256) at rest and prefixed with 'sqk_'.
Authentication uses X-API-Key header with viewer-role service users.
"""

import hashlib
from datetime import timedelta

import pytest
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.api_keys.models import APIKey
from tests.factories import OrganizationFactory, UserFactory


@pytest.mark.django_db
class TestAPIKeyModel(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = OrganizationFactory()
        cls.admin = UserFactory(organization=cls.org, role="admin")

    def test_api_key_generate_creates_hashed_key(self):
        """APIKey.generate() should return an instance with hashed key and a raw key starting with sqk_."""
        key_obj, raw_key = APIKey.generate(
            organization=self.org, name="Test", created_by=self.admin
        )
        assert raw_key.startswith("sqk_")
        assert key_obj.key_hash  # SHA-256 hex
        assert key_obj.key_prefix == raw_key[4:12]  # First 8 chars after prefix

    def test_api_key_hash_matches(self):
        """Hashing the raw key should match the stored hash."""
        key_obj, raw_key = APIKey.generate(
            organization=self.org, name="Test", created_by=self.admin
        )
        computed = hashlib.sha256(raw_key[4:].encode()).hexdigest()
        assert computed == key_obj.key_hash


@pytest.mark.django_db
class TestAPIKeyAuthentication(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = OrganizationFactory()
        cls.admin = UserFactory(organization=cls.org, role="admin")

    def test_valid_api_key_authenticates(self):
        """A request with a valid X-API-Key header should authenticate successfully."""
        _, raw_key = APIKey.generate(organization=self.org, name="Test", created_by=self.admin)
        client = APIClient()
        response = client.get("/api/fibers", HTTP_X_API_KEY=raw_key)
        assert response.status_code != 401

    def test_invalid_api_key_returns_401(self):
        """An invalid API key should return 401."""
        client = APIClient()
        response = client.get("/api/fibers", HTTP_X_API_KEY="sqk_invalid_key_here")
        assert response.status_code == 401

    def test_expired_api_key_returns_401(self):
        """An expired API key should return 401."""
        _, raw_key = APIKey.generate(
            organization=self.org,
            name="Test",
            created_by=self.admin,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        client = APIClient()
        response = client.get("/api/fibers", HTTP_X_API_KEY=raw_key)
        assert response.status_code == 401

    def test_revoked_api_key_returns_401(self):
        """A revoked (is_active=False) API key should return 401."""
        key_obj, raw_key = APIKey.generate(
            organization=self.org, name="Test", created_by=self.admin
        )
        key_obj.is_active = False
        key_obj.save()
        client = APIClient()
        response = client.get("/api/fibers", HTTP_X_API_KEY=raw_key)
        assert response.status_code == 401

    def test_api_key_updates_last_used(self):
        """Successful auth should update last_used_at."""
        key_obj, raw_key = APIKey.generate(
            organization=self.org, name="Test", created_by=self.admin
        )
        assert key_obj.last_used_at is None
        client = APIClient()
        client.get("/api/fibers", HTTP_X_API_KEY=raw_key)
        key_obj.refresh_from_db()
        assert key_obj.last_used_at is not None

    def test_api_key_is_read_only(self):
        """API key with viewer role cannot perform write operations (report generation)."""
        _, raw_key = APIKey.generate(organization=self.org, name="Test", created_by=self.admin)
        client = APIClient()
        response = client.post(
            "/api/reports/generate",
            HTTP_X_API_KEY=raw_key,
            data={},
            content_type="application/json",
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestAPIKeyCRUD(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = OrganizationFactory()
        cls.admin = UserFactory(organization=cls.org, role="admin")
        cls.viewer = UserFactory(organization=cls.org, role="viewer", username="viewer_apikey")

    def setUp(self):
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=self.admin)
        self.viewer_client = APIClient()
        self.viewer_client.force_authenticate(user=self.viewer)

    def test_admin_can_create_api_key(self):
        """Admin users can create API keys via POST /api/admin/api-keys."""
        response = self.admin_client.post(
            "/api/admin/api-keys", data={"name": "My Key"}, content_type="application/json"
        )
        assert response.status_code == 201
        assert "key" in response.json()  # Raw key returned once
        assert response.json()["key"].startswith("sqk_")

    def test_list_api_keys_hides_raw_key(self):
        """GET /api/admin/api-keys should show prefix but never the full key."""
        APIKey.generate(organization=self.org, name="Test", created_by=self.admin)
        response = self.admin_client.get("/api/admin/api-keys")
        assert response.status_code == 200
        for key_data in response.json()["results"]:
            assert "key" not in key_data  # No raw key
            assert "prefix" in key_data

    def test_delete_api_key(self):
        """DELETE /api/admin/api-keys/<id> should revoke the key."""
        key_obj, _ = APIKey.generate(organization=self.org, name="Test", created_by=self.admin)
        response = self.admin_client.delete(f"/api/admin/api-keys/{key_obj.pk}")
        assert response.status_code == 204
        key_obj.refresh_from_db()
        assert key_obj.is_active is False

    def test_rotate_api_key(self):
        """POST /api/admin/api-keys/<id>/rotate should revoke old and return new."""
        key_obj, old_raw = APIKey.generate(
            organization=self.org, name="Test", created_by=self.admin
        )
        response = self.admin_client.post(f"/api/admin/api-keys/{key_obj.pk}/rotate")
        assert response.status_code == 200
        new_raw = response.json()["key"]
        assert new_raw != old_raw
        key_obj.refresh_from_db()
        assert key_obj.is_active is False  # Old key revoked

    def test_viewer_cannot_manage_api_keys(self):
        """Viewer users cannot create API keys."""
        response = self.viewer_client.post(
            "/api/admin/api-keys", data={"name": "X"}, content_type="application/json"
        )
        assert response.status_code == 403
