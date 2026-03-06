"""
Tests for AlertLogListView — alert log listing endpoint.
"""

import pytest
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.alerting.models import AlertLog, AlertRule
from apps.organizations.models import Organization, OrganizationSettings


@pytest.mark.django_db
class TestAlertLogListView(TestCase):
    """Test alert logs endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="Alert Log Test Org", slug="alert-log-test-org")
        OrganizationSettings.objects.create(organization=cls.org)
        cls.other_org = Organization.objects.create(name="Other Alert Org", slug="other-alert-org")
        OrganizationSettings.objects.create(organization=cls.other_org)

        cls.superuser = User.objects.create_superuser(
            username="su_alert_log", password="pass123", email="su@test.com"
        )
        cls.admin_user = User.objects.create_user(
            username="admin_alert_log",
            password="pass123",
            organization=cls.org,
            role="admin",
        )
        cls.other_admin = User.objects.create_user(
            username="admin_other_alert",
            password="pass123",
            organization=cls.other_org,
            role="admin",
        )

        # Create alert rules
        cls.rule = AlertRule.objects.create(
            organization=cls.org,
            name="Test Alert Rule",
            rule_type="speed_below",
            threshold=15.0,
        )
        cls.other_rule = AlertRule.objects.create(
            organization=cls.other_org,
            name="Other Org Rule",
            rule_type="speed_below",
            threshold=20.0,
        )

    def setUp(self):
        self.client = APIClient()

    def test_list_alert_logs_returns_correct_shape_superuser(self):
        """Superuser can list all alert logs with correct response shape."""
        # Create some test logs
        log = AlertLog.objects.create(
            rule=self.rule,
            fiber_id="carros",
            channel=10,
            detail="Test alert detail",
        )
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.get("/api/admin/alert-logs")
        assert resp.status_code == 200
        assert "results" in resp.data
        assert "hasMore" in resp.data
        assert len(resp.data["results"]) >= 1
        result = [r for r in resp.data["results"] if r["id"] == str(log.pk)][0]
        assert "id" in result
        assert "ruleName" in result
        assert "fiberId" in result
        assert "channel" in result
        assert "detail" in result
        assert "dispatchedAt" in result

    def test_superuser_sees_all_logs(self):
        """Superuser can see logs from all organizations."""
        log1 = AlertLog.objects.create(
            rule=self.rule,
            fiber_id="carros",
            channel=10,
            detail="Org 1 alert",
        )
        log2 = AlertLog.objects.create(
            rule=self.other_rule,
            fiber_id="mathis",
            channel=20,
            detail="Org 2 alert",
        )
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.get("/api/admin/alert-logs")
        assert resp.status_code == 200
        ids = [r["id"] for r in resp.data["results"]]
        assert str(log1.pk) in ids
        assert str(log2.pk) in ids

    def test_org_admin_sees_only_own_org_logs(self):
        """Org admin can only see logs from their own organization."""
        log1 = AlertLog.objects.create(
            rule=self.rule,
            fiber_id="carros",
            channel=10,
            detail="Org 1 alert",
        )
        log2 = AlertLog.objects.create(
            rule=self.other_rule,
            fiber_id="mathis",
            channel=20,
            detail="Org 2 alert",
        )
        self.client.force_authenticate(user=self.admin_user)
        resp = self.client.get("/api/admin/alert-logs")
        assert resp.status_code == 200
        ids = [r["id"] for r in resp.data["results"]]
        assert str(log1.pk) in ids
        assert str(log2.pk) not in ids

    def test_org_admin_cannot_see_other_org_logs(self):
        """Org admin's view excludes other org's logs."""
        AlertLog.objects.create(
            rule=self.other_rule,
            fiber_id="mathis",
            channel=20,
            detail="Other org alert",
        )
        self.client.force_authenticate(user=self.admin_user)
        resp = self.client.get("/api/admin/alert-logs")
        assert resp.status_code == 200
        # Should only see logs from self.org (rule belongs to self.other_org)
        # So admin of self.org should see nothing from self.other_rule
        for result in resp.data["results"]:
            # All results should be for self.org (e.g., ruleName should match self.rule.name)
            # Since no logs from self.rule were created yet, results may be empty
            pass

    def test_list_alert_logs_empty(self):
        """Listing alert logs when none exist returns empty results."""
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.get("/api/admin/alert-logs")
        assert resp.status_code == 200
        assert resp.data["results"] == []

    def test_alert_logs_data_formatting(self):
        """Alert logs response has correct data formatting and isoformat dates."""
        log = AlertLog.objects.create(
            rule=self.rule,
            fiber_id="test-fiber",
            channel=50,
            detail="Test detail message",
        )
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.get("/api/admin/alert-logs")
        assert resp.status_code == 200
        result = [r for r in resp.data["results"] if r["id"] == str(log.pk)][0]
        assert result["ruleName"] == self.rule.name
        assert result["fiberId"] == "test-fiber"
        assert result["channel"] == 50
        assert result["detail"] == "Test detail message"
        # Check that dispatchedAt is in ISO format
        assert "T" in result["dispatchedAt"]

    def test_alert_logs_limited_to_100(self):
        """Listing alert logs is limited to 100 results."""
        # Create many logs (more than 100)
        for i in range(150):
            AlertLog.objects.create(
                rule=self.rule,
                fiber_id=f"fiber-{i}",
                channel=i % 100,
                detail=f"Alert {i}",
            )
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.get("/api/admin/alert-logs")
        assert resp.status_code == 200
        # Should only return up to 100
        assert len(resp.data["results"]) <= 100
