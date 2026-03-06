"""
Tests for FiberAssignmentListView and FiberAssignmentDetailView.
"""

import pytest
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.fibers.models import FiberAssignment
from apps.organizations.models import Organization, OrganizationSettings


@pytest.mark.django_db
class TestFiberAssignmentViews(TestCase):
    """Test fiber assignment endpoints (superuser only)."""

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="Fiber Test Org", slug="fiber-test-org")
        OrganizationSettings.objects.create(organization=cls.org)
        cls.other_org = Organization.objects.create(name="Other Fiber Org", slug="other-fiber-org")
        OrganizationSettings.objects.create(organization=cls.other_org)

        cls.superuser = User.objects.create_superuser(
            username="su_fiber", password="pass123", email="su@test.com"
        )
        cls.admin_user = User.objects.create_user(
            username="admin_fiber",
            password="pass123",
            organization=cls.org,
            role="admin",
        )

    def setUp(self):
        self.client = APIClient()

    def test_list_fiber_assignments_superuser(self):
        """Superuser can list fiber assignments for an org."""
        assignment = FiberAssignment.objects.create(organization=self.org, fiber_id="carros")
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.get(f"/api/admin/organizations/{self.org.pk}/fibers")
        assert resp.status_code == 200
        assert "results" in resp.data
        assert len(resp.data["results"]) >= 1
        result = [r for r in resp.data["results"] if r["fiberId"] == "carros"][0]
        assert result["id"] == str(assignment.pk)
        assert result["fiberId"] == "carros"
        assert "assignedAt" in result

    def test_list_fiber_assignments_empty(self):
        """Listing fiber assignments for org with none returns empty list."""
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.get(f"/api/admin/organizations/{self.org.pk}/fibers")
        assert resp.status_code == 200
        assert resp.data["results"] == []

    def test_create_fiber_assignment_superuser(self):
        """Superuser can create fiber assignment."""
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.post(
            f"/api/admin/organizations/{self.org.pk}/fibers",
            {"fiberId": "new-fiber"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["fiberId"] == "new-fiber"
        assert "id" in resp.data
        assert "assignedAt" in resp.data
        # Verify in DB
        assert FiberAssignment.objects.filter(organization=self.org, fiber_id="new-fiber").exists()

    def test_create_fiber_assignment_requires_fiber_id(self):
        """Creating fiber assignment requires fiberId."""
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.post(f"/api/admin/organizations/{self.org.pk}/fibers", {}, format="json")
        assert resp.status_code == 400
        assert "fiberId is required" in resp.data["detail"]

    def test_create_fiber_assignment_nonexistent_org(self):
        """Creating fiber assignment for nonexistent org returns 404."""
        self.client.force_authenticate(user=self.superuser)
        fake_org_id = "00000000-0000-0000-0000-000000000000"
        resp = self.client.post(
            f"/api/admin/organizations/{fake_org_id}/fibers", {"fiberId": "fiber-1"}, format="json"
        )
        assert resp.status_code == 404
        assert "Organization not found" in resp.data["detail"]

    def test_create_duplicate_fiber_assignment_returns_400(self):
        """Creating duplicate fiber assignment returns 400."""
        FiberAssignment.objects.create(organization=self.org, fiber_id="duplicate-fiber")
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.post(
            f"/api/admin/organizations/{self.org.pk}/fibers",
            {"fiberId": "duplicate-fiber"},
            format="json",
        )
        assert resp.status_code == 400
        assert "already assigned" in resp.data["detail"]

    def test_delete_fiber_assignment_superuser(self):
        """Superuser can delete fiber assignment."""
        assignment = FiberAssignment.objects.create(organization=self.org, fiber_id="to-delete")
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.delete(f"/api/admin/organizations/{self.org.pk}/fibers/{assignment.pk}")
        assert resp.status_code == 204
        assert not FiberAssignment.objects.filter(pk=assignment.pk).exists()

    def test_delete_nonexistent_assignment_returns_404(self):
        """Deleting nonexistent fiber assignment returns 404."""
        self.client.force_authenticate(user=self.superuser)
        fake_assignment_id = "00000000-0000-0000-0000-000000000000"
        resp = self.client.delete(
            f"/api/admin/organizations/{self.org.pk}/fibers/{fake_assignment_id}"
        )
        assert resp.status_code == 404

    def test_org_admin_cannot_list_fiber_assignments(self):
        """Org admin cannot list fiber assignments (403)."""
        self.client.force_authenticate(user=self.admin_user)
        resp = self.client.get(f"/api/admin/organizations/{self.org.pk}/fibers")
        assert resp.status_code == 403

    def test_org_admin_cannot_create_fiber_assignment(self):
        """Org admin cannot create fiber assignment (403)."""
        self.client.force_authenticate(user=self.admin_user)
        resp = self.client.post(
            f"/api/admin/organizations/{self.org.pk}/fibers",
            {"fiberId": "new-fiber"},
            format="json",
        )
        assert resp.status_code == 403

    def test_org_admin_cannot_delete_fiber_assignment(self):
        """Org admin cannot delete fiber assignment (403)."""
        assignment = FiberAssignment.objects.create(organization=self.org, fiber_id="some-fiber")
        self.client.force_authenticate(user=self.admin_user)
        resp = self.client.delete(f"/api/admin/organizations/{self.org.pk}/fibers/{assignment.pk}")
        assert resp.status_code == 403

    def test_delete_assignment_from_wrong_org(self):
        """Deleting assignment from wrong org returns 404."""
        assignment = FiberAssignment.objects.create(
            organization=self.other_org, fiber_id="other-fiber"
        )
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.delete(f"/api/admin/organizations/{self.org.pk}/fibers/{assignment.pk}")
        assert resp.status_code == 404
