"""
Tests for webhook improvements: HMAC signing, retry logic, delivery status tracking.
"""

import hashlib
import hmac as hmac_module
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase

from apps.alerting.dispatch import dispatch_alert
from apps.alerting.models import AlertLog, AlertRule
from tests.factories import OrganizationFactory


@pytest.mark.django_db
@patch("apps.alerting.dispatch._SYNC_MODE", True)
@patch("apps.alerting.dispatch.validate_webhook_url", return_value=None)
class TestWebhookHMAC(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = OrganizationFactory()

    @patch("apps.alerting.dispatch.http_requests.post")
    @patch("apps.alerting.dispatch.time.sleep")
    def test_webhook_sends_hmac_signature(self, mock_sleep, mock_post, *_):
        """When webhook_secret is set, X-Sequoia-Signature header should be present."""
        mock_post.return_value = MagicMock(status_code=200)
        rule = AlertRule.objects.create(
            organization=self.org,
            name="HMAC test",
            rule_type="speed_below",
            threshold=20.0,
            dispatch_channel="webhook",
            webhook_url="https://example.com/hook",
            webhook_secret="mysecret",
        )
        dispatch_alert(rule, "inc-1", "fiber-1", 100, "test")
        call_args = mock_post.call_args
        assert "X-Sequoia-Signature" in call_args.kwargs.get("headers", {})
        assert call_args.kwargs["headers"]["X-Sequoia-Signature"].startswith("sha256=")

    @patch("apps.alerting.dispatch.http_requests.post")
    @patch("apps.alerting.dispatch.time.sleep")
    def test_webhook_no_signature_without_secret(self, mock_sleep, mock_post, *_):
        """When webhook_secret is empty, no signature header should be sent."""
        mock_post.return_value = MagicMock(status_code=200)
        rule = AlertRule.objects.create(
            organization=self.org,
            name="No secret",
            rule_type="speed_below",
            threshold=20.0,
            dispatch_channel="webhook",
            webhook_url="https://example.com/hook",
            webhook_secret="",
        )
        dispatch_alert(rule, "inc-1", "fiber-1", 100, "test")
        headers = mock_post.call_args.kwargs.get("headers", {})
        assert "X-Sequoia-Signature" not in headers

    @patch("apps.alerting.dispatch.http_requests.post")
    @patch("apps.alerting.dispatch.time.sleep")
    def test_hmac_signature_is_verifiable(self, mock_sleep, mock_post, *_):
        """The HMAC signature should be verifiable by the receiver."""
        mock_post.return_value = MagicMock(status_code=200)
        secret = "test-secret-key"
        rule = AlertRule.objects.create(
            organization=self.org,
            name="Verify HMAC",
            rule_type="speed_below",
            threshold=20.0,
            dispatch_channel="webhook",
            webhook_url="https://example.com/hook",
            webhook_secret=secret,
        )
        dispatch_alert(rule, "inc-1", "fiber-1", 100, "test")
        sent_body = mock_post.call_args.kwargs["data"]
        sent_sig = mock_post.call_args.kwargs["headers"]["X-Sequoia-Signature"]
        expected = (
            "sha256=" + hmac_module.new(secret.encode(), sent_body, hashlib.sha256).hexdigest()
        )
        assert sent_sig == expected


@pytest.mark.django_db
@patch("apps.alerting.dispatch._SYNC_MODE", True)
@patch("apps.alerting.dispatch.validate_webhook_url", return_value=None)
class TestWebhookRetry(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = OrganizationFactory()

    @patch("apps.alerting.dispatch.http_requests.post")
    @patch("apps.alerting.dispatch.time.sleep")
    def test_webhook_retries_on_failure(self, mock_sleep, mock_post, *_):
        """Webhook should retry 3 times on HTTP error before giving up."""
        mock_post.return_value = MagicMock(status_code=500)
        rule = AlertRule.objects.create(
            organization=self.org,
            name="Retry test",
            rule_type="speed_below",
            threshold=20.0,
            dispatch_channel="webhook",
            webhook_url="https://example.com/hook",
        )
        dispatch_alert(rule, "inc-1", "fiber-1", 100, "test")
        assert mock_post.call_count == 4  # 1 original + 3 retries

    @patch("apps.alerting.dispatch.http_requests.post")
    @patch("apps.alerting.dispatch.time.sleep")
    def test_webhook_stops_retrying_on_success(self, mock_sleep, mock_post, *_):
        """If a retry succeeds, stop retrying."""
        mock_post.side_effect = [
            MagicMock(status_code=500),
            MagicMock(status_code=200),
        ]
        rule = AlertRule.objects.create(
            organization=self.org,
            name="Retry stop",
            rule_type="speed_below",
            threshold=20.0,
            dispatch_channel="webhook",
            webhook_url="https://example.com/hook",
        )
        dispatch_alert(rule, "inc-1", "fiber-1", 100, "test")
        assert mock_post.call_count == 2


@pytest.mark.django_db
@patch("apps.alerting.dispatch._SYNC_MODE", True)
@patch("apps.alerting.dispatch.validate_webhook_url", return_value=None)
class TestWebhookDeliveryStatus(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = OrganizationFactory()

    @patch("apps.alerting.dispatch.http_requests.post")
    @patch("apps.alerting.dispatch.time.sleep")
    def test_successful_webhook_logged_as_success(self, mock_sleep, mock_post, *_):
        """AlertLog should have delivery_status='success' on successful dispatch."""
        mock_post.return_value = MagicMock(status_code=200)
        rule = AlertRule.objects.create(
            organization=self.org,
            name="Success status",
            rule_type="speed_below",
            threshold=20.0,
            dispatch_channel="webhook",
            webhook_url="https://example.com/hook",
        )
        dispatch_alert(rule, "inc-1", "fiber-1", 100, "test")
        log = AlertLog.objects.latest("dispatched_at")
        assert log.delivery_status == "success"

    @patch("apps.alerting.dispatch.http_requests.post")
    @patch("apps.alerting.dispatch.time.sleep")
    def test_failed_webhook_logged_with_error(self, mock_sleep, mock_post, *_):
        """AlertLog should have delivery_status='failed' and error_message on failure."""
        mock_post.return_value = MagicMock(status_code=500)
        rule = AlertRule.objects.create(
            organization=self.org,
            name="Fail status",
            rule_type="speed_below",
            threshold=20.0,
            dispatch_channel="webhook",
            webhook_url="https://example.com/hook",
        )
        dispatch_alert(rule, "inc-1", "fiber-1", 100, "test")
        log = AlertLog.objects.latest("dispatched_at")
        assert log.delivery_status == "failed"
        assert "HTTP 500" in log.error_message


@pytest.mark.django_db
class TestWebhookTestEndpoint(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = OrganizationFactory()
        cls.admin = OrganizationFactory.__class__  # placeholder

    def setUp(self):
        from tests.factories import UserFactory

        self.admin_user = UserFactory(organization=self.org, role="admin")
        from rest_framework.test import APIClient

        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=self.admin_user)

    @patch("apps.alerting.dispatch._dispatch_webhook")
    def test_webhook_test_endpoint(self, mock_dispatch):
        """POST /api/admin/alert-rules/<id>/test should send a test payload."""
        rule = AlertRule.objects.create(
            organization=self.org,
            name="Test endpoint",
            rule_type="speed_below",
            threshold=20.0,
            dispatch_channel="webhook",
            webhook_url="https://example.com/hook",
        )
        response = self.admin_client.post(f"/api/admin/alert-rules/{rule.pk}/test")
        assert response.status_code == 200
        mock_dispatch.assert_called_once()
