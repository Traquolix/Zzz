"""
TDD tests for Fix #2: Superuser report org ambiguity.

Superusers must provide an explicit organizationId when generating reports.
Regular users always use their own organization (organizationId ignored).
"""

import uuid
from unittest.mock import patch

import pytest
from django.test import TestCase
from rest_framework.test import APIClient

from tests.factories import FiberAssignmentFactory, OrganizationFactory, UserFactory


@pytest.mark.django_db
class TestSuperuserReportOrgSelection(TestCase):
    """Superuser must explicitly select an organization for report generation."""

    def setUp(self):
        self.org_a = OrganizationFactory(name="Org A")
        self.org_b = OrganizationFactory(name="Org B")
        self.superuser = UserFactory(
            organization=self.org_a,
            is_superuser=True,
            username="superadmin",
        )
        self.fiber = FiberAssignmentFactory(organization=self.org_a, fiber_id="carros")
        self.client = APIClient()
        self.client.force_authenticate(user=self.superuser)
        self.valid_payload = {
            "title": "Test Report",
            "startTime": "2026-02-01T00:00:00Z",
            "endTime": "2026-02-28T00:00:00Z",
            "fiberIds": ["carros"],
            "sections": ["incidents"],
        }

    @patch("apps.reporting.views.enqueue_report_generation")
    def test_superuser_without_org_id_gets_400(self, _mock_build):
        """Superuser must provide organizationId — omitting it returns 400."""
        response = self.client.post("/api/reports/generate", self.valid_payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "org_required")

    @patch("apps.reporting.views.enqueue_report_generation")
    def test_superuser_with_valid_org_id_creates_report(self, _mock_build):
        """Superuser with valid organizationId creates report under that org."""
        payload = {**self.valid_payload, "organizationId": str(self.org_a.pk)}
        response = self.client.post("/api/reports/generate", payload, format="json")
        self.assertEqual(response.status_code, 201)

        from apps.reporting.models import Report

        report = Report.objects.get(pk=response.json()["id"])
        self.assertEqual(report.organization_id, self.org_a.pk)

    @patch("apps.reporting.views.enqueue_report_generation")
    def test_superuser_with_invalid_org_id_gets_400(self, _mock_build):
        """Nonexistent organizationId returns 400."""
        payload = {**self.valid_payload, "organizationId": str(uuid.uuid4())}
        response = self.client.post("/api/reports/generate", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "org_invalid")

    @patch("apps.reporting.views.enqueue_report_generation")
    def test_superuser_fiber_not_in_org_gets_403(self, _mock_build):
        """Fiber not assigned to the specified org returns 403."""
        payload = {**self.valid_payload, "organizationId": str(self.org_b.pk)}
        response = self.client.post("/api/reports/generate", payload, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "fiber_access_denied")


@pytest.mark.django_db
class TestRegularUserReportOrgSelection(TestCase):
    """Regular user always uses their own organization — organizationId ignored."""

    def setUp(self):
        self.org = OrganizationFactory(name="My Org")
        self.other_org = OrganizationFactory(name="Other Org")
        self.user = UserFactory(organization=self.org, username="regular")
        self.fiber = FiberAssignmentFactory(organization=self.org, fiber_id="carros")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.valid_payload = {
            "title": "Test Report",
            "startTime": "2026-02-01T00:00:00Z",
            "endTime": "2026-02-28T00:00:00Z",
            "fiberIds": ["carros"],
            "sections": ["incidents"],
        }

    @patch("apps.reporting.views.enqueue_report_generation")
    def test_regular_user_ignores_org_id(self, _mock_build):
        """Even if organizationId is sent, regular user's own org is used."""
        payload = {**self.valid_payload, "organizationId": str(self.other_org.pk)}
        response = self.client.post("/api/reports/generate", payload, format="json")
        self.assertEqual(response.status_code, 201)

        from apps.reporting.models import Report

        report = Report.objects.get(pk=response.json()["id"])
        self.assertEqual(report.organization_id, self.org.pk)
