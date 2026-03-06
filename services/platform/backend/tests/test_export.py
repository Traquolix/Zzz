"""
Tests for bulk data export endpoints.

Export endpoints provide CSV/JSON downloads of incidents and detections
with automatic tier selection based on time range.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase
from rest_framework.test import APIClient

from apps.api_keys.models import APIKey
from tests.factories import FiberAssignmentFactory, OrganizationFactory, UserFactory


@pytest.mark.django_db
class TestExportIncidents(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = OrganizationFactory()
        cls.admin = UserFactory(organization=cls.org, role="admin")
        FiberAssignmentFactory(organization=cls.org, fiber_id="carros")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_export_incidents_csv(
        self,
    ):
        """GET /api/export/incidents?format=csv should return CSV with correct headers."""
        mock_result = MagicMock()
        mock_result.column_names = ["incident_id", "fiber_id", "type", "severity", "detected_at"]
        mock_result.result_rows = [
            ("inc-1", "carros:0", "congestion", "medium", "2026-01-01T10:00:00"),
        ]

        mock_client = MagicMock()
        mock_client.query.return_value = mock_result

        with patch("apps.monitoring.export_views.get_client", return_value=mock_client):
            response = self.client.get(
                "/api/export/incidents?fiber_id=carros:0&start=2026-01-01&end=2026-01-02&fmt=csv"
            )
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"
        content = b"".join(response.streaming_content).decode()
        assert "incident_id" in content

    def test_export_incidents_json(self):
        """GET /api/export/incidents?format=json should return JSON array."""
        mock_result = MagicMock()
        mock_result.column_names = ["incident_id", "fiber_id", "type", "severity", "detected_at"]
        mock_result.result_rows = [
            ("inc-1", "carros:0", "congestion", "medium", "2026-01-01T10:00:00"),
        ]

        mock_client = MagicMock()
        mock_client.query.return_value = mock_result

        with patch("apps.monitoring.export_views.get_client", return_value=mock_client):
            response = self.client.get(
                "/api/export/incidents?fiber_id=carros:0&start=2026-01-01&end=2026-01-02&fmt=json"
            )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


@pytest.mark.django_db
class TestExportValidation(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = OrganizationFactory()
        cls.admin = UserFactory(organization=cls.org, role="admin")
        FiberAssignmentFactory(organization=cls.org, fiber_id="carros")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_export_requires_fiber_id(self):
        response = self.client.get("/api/export/detections?start=2026-01-01&end=2026-01-02")
        assert response.status_code == 400

    def test_export_requires_time_range(self):
        response = self.client.get("/api/export/detections?fiber_id=carros:0")
        assert response.status_code == 400

    def test_export_rejects_excessive_hires_range(self):
        """Hires export >7 days should be rejected."""
        response = self.client.get(
            "/api/export/detections?fiber_id=carros:0&start=2026-01-01&end=2026-01-20&tier=hires"
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestExportTierSelection(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = OrganizationFactory()
        cls.admin = UserFactory(organization=cls.org, role="admin")
        FiberAssignmentFactory(organization=cls.org, fiber_id="carros")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_export_detections_uses_hires_for_short_range(self):
        """Time range <=48h should query the detection_hires table."""
        mock_result = MagicMock()
        mock_result.column_names = ["ts", "fiber_id", "channel", "speed"]
        mock_result.result_rows = []
        mock_client = MagicMock()
        mock_client.query.return_value = mock_result

        with patch("apps.monitoring.export_views.get_client", return_value=mock_client):
            self.client.get(
                "/api/export/detections?fiber_id=carros:0&start=2026-01-01T00:00:00&end=2026-01-01T12:00:00"
            )
        query = mock_client.query.call_args[0][0]
        assert "detection_hires" in query

    def test_export_detections_uses_1m_for_medium_range(self):
        """Time range >48h <=90d should query detection_1m table."""
        mock_result = MagicMock()
        mock_result.column_names = ["ts", "fiber_id", "channel", "speed_avg"]
        mock_result.result_rows = []
        mock_client = MagicMock()
        mock_client.query.return_value = mock_result

        with patch("apps.monitoring.export_views.get_client", return_value=mock_client):
            self.client.get(
                "/api/export/detections?fiber_id=carros:0&start=2026-01-01&end=2026-02-01"
            )
        query = mock_client.query.call_args[0][0]
        assert "detection_1m" in query

    def test_export_detections_uses_1h_for_long_range(self):
        """Time range >90d should query detection_1h table."""
        mock_result = MagicMock()
        mock_result.column_names = ["ts", "fiber_id", "channel", "speed_avg"]
        mock_result.result_rows = []
        mock_client = MagicMock()
        mock_client.query.return_value = mock_result

        with patch("apps.monitoring.export_views.get_client", return_value=mock_client):
            self.client.get(
                "/api/export/detections?fiber_id=carros:0&start=2025-01-01&end=2026-01-01"
            )
        query = mock_client.query.call_args[0][0]
        assert "detection_1h" in query


@pytest.mark.django_db
class TestExportOrgScoping(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = OrganizationFactory()
        cls.admin = UserFactory(organization=cls.org, role="admin")
        FiberAssignmentFactory(organization=cls.org, fiber_id="carros")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_export_rejects_foreign_fiber(self):
        """Cannot export data for a fiber not assigned to your org."""
        response = self.client.get(
            "/api/export/detections?fiber_id=other-org-fiber:0&start=2026-01-01&end=2026-01-02"
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestExportAPIKey(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = OrganizationFactory()
        cls.admin = UserFactory(organization=cls.org, role="admin")
        FiberAssignmentFactory(organization=cls.org, fiber_id="carros")

    def test_export_works_with_api_key(self):
        """Export endpoints should work with API key authentication."""
        _, raw_key = APIKey.generate(organization=self.org, name="Test", created_by=self.admin)

        mock_result = MagicMock()
        mock_result.column_names = ["incident_id", "fiber_id", "type", "severity", "detected_at"]
        mock_result.result_rows = []
        mock_client = MagicMock()
        mock_client.query.return_value = mock_result

        client = APIClient()
        with patch("apps.monitoring.export_views.get_client", return_value=mock_client):
            response = client.get(
                "/api/export/incidents?fiber_id=carros:0&start=2026-01-01&end=2026-01-02",
                HTTP_X_API_KEY=raw_key,
            )
        assert response.status_code == 200
