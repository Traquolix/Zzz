"""Tests for alerting integration with realtime consumers."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from asgiref.sync import async_to_sync

from apps.alerting.integration import check_alerts_for_detections, check_alerts_for_incident


@pytest.mark.django_db
class TestCheckAlertsForDetections:
    """Test detection-based alert evaluation in async context."""

    def test_no_rules_returns_zero(self):
        """No active rules for org → 0 alerts dispatched."""
        org_id = str(uuid.uuid4())
        result = async_to_sync(check_alerts_for_detections)(
            [{"fiberLine": "fiber:0", "speed": 30, "channel": 100}],
            org_id,
        )
        assert result == 0

    @patch("apps.alerting.integration.dispatch_alert", return_value=True)
    @patch("apps.alerting.integration.evaluate_detection")
    @patch("apps.alerting.integration.AlertRule")
    def test_matching_detection_dispatches(self, mock_model, mock_eval, mock_dispatch):
        """Detection matching a rule triggers dispatch."""
        org_id = str(uuid.uuid4())
        mock_rule = MagicMock()
        mock_rule.organization_id = org_id
        mock_model.objects.filter.return_value = [mock_rule]
        mock_eval.return_value = [(mock_rule, "speed below 40")]

        result = async_to_sync(check_alerts_for_detections)(
            [{"fiberLine": "fiber:0", "speed": 30}],
            org_id,
        )
        assert result == 1
        mock_dispatch.assert_called_once()

    @patch("apps.alerting.integration.dispatch_alert")
    @patch("apps.alerting.integration.evaluate_detection", return_value=[])
    @patch("apps.alerting.integration.AlertRule")
    def test_non_matching_detection_skips(self, mock_model, mock_eval, mock_dispatch):
        """Detection not matching any rule → no dispatch."""
        org_id = str(uuid.uuid4())
        mock_model.objects.filter.return_value = [MagicMock()]

        result = async_to_sync(check_alerts_for_detections)(
            [{"fiberLine": "fiber:0", "speed": 100}],
            org_id,
        )
        assert result == 0
        mock_dispatch.assert_not_called()

    @patch("apps.alerting.integration.dispatch_alert", return_value=True)
    @patch("apps.alerting.integration.evaluate_detection")
    @patch("apps.alerting.integration.AlertRule")
    def test_multiple_detections_evaluated(self, mock_model, mock_eval, mock_dispatch):
        """All detections in batch are evaluated."""
        org_id = str(uuid.uuid4())
        mock_rule = MagicMock()
        mock_model.objects.filter.return_value = [mock_rule]
        mock_eval.side_effect = [
            [(mock_rule, "alert 1")],
            [],
            [(mock_rule, "alert 3")],
        ]

        result = async_to_sync(check_alerts_for_detections)(
            [{"speed": 20}, {"speed": 80}, {"speed": 25}],
            org_id,
        )
        assert result == 2
        assert mock_eval.call_count == 3


@pytest.mark.django_db
class TestCheckAlertsForIncident:
    """Test incident-based alert evaluation."""

    def test_no_org_mapping_returns_zero(self):
        """Incident with unmapped fiberLine → 0 alerts."""
        result = async_to_sync(check_alerts_for_incident)(
            {"id": "inc-1", "fiberLine": "unknown:0", "type": "accident", "severity": "high"},
            {},
        )
        assert result == 0

    @patch("apps.alerting.integration.dispatch_alert", return_value=True)
    @patch("apps.alerting.integration.evaluate_incident")
    @patch("apps.alerting.integration.AlertRule")
    def test_matching_incident_dispatches(self, mock_model, mock_eval, mock_dispatch):
        """Incident matching a rule triggers dispatch."""
        org_id = str(uuid.uuid4())
        mock_rule = MagicMock()
        mock_model.objects.filter.return_value = [mock_rule]
        mock_eval.return_value = [(mock_rule, "accident detected")]

        result = async_to_sync(check_alerts_for_incident)(
            {"id": "inc-1", "fiberLine": "fiber:0", "type": "accident", "severity": "critical"},
            {"fiber": [org_id]},
        )
        assert result == 1

    @patch("apps.alerting.integration.dispatch_alert")
    @patch("apps.alerting.integration.evaluate_incident", return_value=[])
    @patch("apps.alerting.integration.AlertRule")
    def test_non_matching_incident_skips(self, mock_model, mock_eval, mock_dispatch):
        """Incident not matching rules → no dispatch."""
        org_id = str(uuid.uuid4())
        mock_model.objects.filter.return_value = [MagicMock()]

        result = async_to_sync(check_alerts_for_incident)(
            {"id": "inc-1", "fiberLine": "fiber:0", "type": "slowdown", "severity": "low"},
            {"fiber": [org_id]},
        )
        assert result == 0
        mock_dispatch.assert_not_called()
