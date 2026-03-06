"""
Tests for UserDetailView — user-level management endpoint.
"""

import pytest
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.organizations.models import Organization, OrganizationSettings


@pytest.mark.django_db
class TestUserDetailView(TestCase):
    """Test user detail endpoint (PATCH)."""

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(
            name="User Detail Test Org", slug="user-detail-test-org"
        )
        OrganizationSettings.objects.create(organization=cls.org)
        cls.other_org = Organization.objects.create(name="Other Org", slug="other-org-ud")
        OrganizationSettings.objects.create(organization=cls.other_org)

        cls.superuser = User.objects.create_superuser(
            username="su_user_detail", password="pass123", email="su@test.com"
        )
        cls.admin_user = User.objects.create_user(
            username="admin_user_detail",
            password="pass123",
            organization=cls.org,
            role="admin",
        )
        cls.target_user = User.objects.create_user(
            username="target_user",
            password="pass123",
            email="target@test.com",
            organization=cls.org,
            role="viewer",
        )
        cls.other_org_user = User.objects.create_user(
            username="other_org_user_detail",
            password="pass123",
            organization=cls.other_org,
            role="viewer",
        )

    def setUp(self):
        self.client = APIClient()

    def test_patch_user_role_superuser(self):
        """Superuser can patch user role."""
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.patch(
            f"/api/admin/users/{self.target_user.pk}", {"role": "operator"}, format="json"
        )
        assert resp.status_code == 200
        self.target_user.refresh_from_db()
        assert self.target_user.role == "operator"

    def test_patch_user_email_superuser(self):
        """Superuser can patch user email."""
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.patch(
            f"/api/admin/users/{self.target_user.pk}", {"email": "newemail@test.com"}, format="json"
        )
        assert resp.status_code == 200
        self.target_user.refresh_from_db()
        assert self.target_user.email == "newemail@test.com"

    def test_patch_user_is_active(self):
        """Superuser can patch user isActive."""
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.patch(
            f"/api/admin/users/{self.target_user.pk}", {"isActive": False}, format="json"
        )
        assert resp.status_code == 200
        self.target_user.refresh_from_db()
        assert self.target_user.is_active is False

    def test_patch_user_widgets_validates_invalid_keys(self):
        """Patch with invalid widget keys returns 400."""
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.patch(
            f"/api/admin/users/{self.target_user.pk}",
            {"allowedWidgets": ["map", "invalid_widget"]},
            format="json",
        )
        assert resp.status_code == 400
        assert "Invalid widget keys" in resp.data["detail"]

    def test_patch_user_widgets_succeeds(self):
        """Patch with valid widget keys succeeds."""
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.patch(
            f"/api/admin/users/{self.target_user.pk}",
            {"allowedWidgets": ["map", "incidents"]},
            format="json",
        )
        assert resp.status_code == 200
        self.target_user.refresh_from_db()
        assert self.target_user.allowed_widgets == ["map", "incidents"]

    def test_patch_user_layers_validates_invalid_keys(self):
        """Patch with invalid layer keys returns 400."""
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.patch(
            f"/api/admin/users/{self.target_user.pk}",
            {"allowedLayers": ["cables", "invalid_layer"]},
            format="json",
        )
        assert resp.status_code == 400
        assert "Invalid layer keys" in resp.data["detail"]

    def test_patch_user_layers_succeeds(self):
        """Patch with valid layer keys succeeds."""
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.patch(
            f"/api/admin/users/{self.target_user.pk}",
            {"allowedLayers": ["cables", "fibers"]},
            format="json",
        )
        assert resp.status_code == 200
        self.target_user.refresh_from_db()
        assert self.target_user.allowed_layers == ["cables", "fibers"]

    def test_patch_user_returns_correct_shape(self):
        """Patch response includes all user fields."""
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.patch(
            f"/api/admin/users/{self.target_user.pk}", {"role": "admin"}, format="json"
        )
        assert resp.status_code == 200
        assert "id" in resp.data
        assert "username" in resp.data
        assert "email" in resp.data
        assert "role" in resp.data
        assert "isActive" in resp.data
        assert "allowedWidgets" in resp.data
        assert "allowedLayers" in resp.data
        assert "organizationId" in resp.data

    def test_org_admin_can_patch_own_org_user(self):
        """Org admin can patch users in their own org."""
        self.client.force_authenticate(user=self.admin_user)
        resp = self.client.patch(
            f"/api/admin/users/{self.target_user.pk}", {"role": "operator"}, format="json"
        )
        assert resp.status_code == 200
        self.target_user.refresh_from_db()
        assert self.target_user.role == "operator"

    def test_org_admin_cannot_patch_other_org_user(self):
        """Org admin cannot patch users in other orgs (404 due to scoping)."""
        self.client.force_authenticate(user=self.admin_user)
        resp = self.client.patch(
            f"/api/admin/users/{self.other_org_user.pk}", {"role": "operator"}, format="json"
        )
        assert resp.status_code == 404

    def test_patch_nonexistent_user_returns_404(self):
        """Patching nonexistent user returns 404."""
        self.client.force_authenticate(user=self.superuser)
        fake_user_id = "00000000-0000-0000-0000-000000000000"
        resp = self.client.patch(
            f"/api/admin/users/{fake_user_id}", {"role": "admin"}, format="json"
        )
        assert resp.status_code == 404

    def test_patch_multiple_fields_at_once(self):
        """Patch can update multiple fields at once."""
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.patch(
            f"/api/admin/users/{self.target_user.pk}",
            {
                "role": "admin",
                "email": "updated@test.com",
                "isActive": False,
                "allowedWidgets": ["map"],
            },
            format="json",
        )
        assert resp.status_code == 200
        self.target_user.refresh_from_db()
        assert self.target_user.role == "admin"
        assert self.target_user.email == "updated@test.com"
        assert self.target_user.is_active is False
        assert self.target_user.allowed_widgets == ["map"]
