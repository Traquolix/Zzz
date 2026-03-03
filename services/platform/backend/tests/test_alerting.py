"""
TDD tests for alerting rules engine.

The alerting system should:
1. Define rules per-org (speed threshold, incident type filter, channel range)
2. Evaluate incoming detection data against rules
3. Dispatch alerts via configured channels (log, webhook, email)
4. Auto-resolve incidents older than org's auto_resolve_minutes setting
5. Debounce: don't fire the same rule for the same fiber+channel within cooldown
"""

import uuid
from datetime import timedelta
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from django.test import TestCase
from django.utils import timezone

from apps.alerting.models import AlertRule, AlertLog
from apps.alerting.evaluator import evaluate_detection, evaluate_incident
from apps.alerting.dispatch import dispatch_alert


# ---------------------------------------------------------------------------
# Model tests — AlertRule + AlertLog
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAlertRuleModel(TestCase):

    @classmethod
    def setUpTestData(cls):
        from apps.organizations.models import Organization
        cls.org = Organization.objects.create(name='Alert Org', slug='alert-org')

    def test_create_speed_threshold_rule(self):
        rule = AlertRule.objects.create(
            organization=self.org,
            name='Slowdown alert',
            rule_type='speed_below',
            threshold=20.0,
            severity_filter=['medium', 'high', 'critical'],
            is_active=True,
        )
        assert rule.pk is not None
        assert rule.rule_type == 'speed_below'
        assert rule.threshold == 20.0
        assert rule.cooldown_seconds == 300  # default

    def test_create_incident_type_rule(self):
        rule = AlertRule.objects.create(
            organization=self.org,
            name='Accident alert',
            rule_type='incident_type',
            incident_type_filter=['accident'],
            severity_filter=['high', 'critical'],
            dispatch_channel='webhook',
        )
        assert rule.dispatch_channel == 'webhook'
        assert rule.incident_type_filter == ['accident']

    def test_scoped_to_org(self):
        from apps.organizations.models import Organization
        other_org = Organization.objects.create(name='Other Org 2', slug='other-org-2')

        AlertRule.objects.create(organization=self.org, name='Rule A', rule_type='speed_below', threshold=15.0)
        AlertRule.objects.create(organization=other_org, name='Rule B', rule_type='speed_below', threshold=25.0)

        org_rules = AlertRule.objects.filter(organization=self.org)
        assert org_rules.count() == 1
        assert org_rules.first().name == 'Rule A'

    def test_alert_log_created(self):
        rule = AlertRule.objects.create(
            organization=self.org,
            name='Test rule',
            rule_type='speed_below',
            threshold=20.0,
        )
        log = AlertLog.objects.create(
            rule=rule,
            incident_id='inc-500',
            fiber_id='carros:0',
            channel=42,
            detail='Speed 12 km/h below threshold 20 km/h',
        )
        assert log.pk is not None
        assert log.rule == rule
        assert log.dispatched_at is not None


# ---------------------------------------------------------------------------
# Evaluator tests — pure logic
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAlertEvaluator(TestCase):

    @classmethod
    def setUpTestData(cls):
        from apps.organizations.models import Organization
        cls.org = Organization.objects.create(name='Eval Org', slug='eval-org')

    def test_speed_below_triggers_alert(self):
        rule = AlertRule.objects.create(
            organization=self.org,
            name='Slow traffic',
            rule_type='speed_below',
            threshold=20.0,
            is_active=True,
        )
        detection = {
            'fiberLine': 'carros:0',
            'channel': 10,
            'speed': 12.0,
        }
        triggered = evaluate_detection(detection, [rule])
        assert len(triggered) == 1
        assert triggered[0][0] == rule
        assert 'below' in triggered[0][1].lower()

    def test_speed_above_threshold_does_not_trigger(self):
        rule = AlertRule.objects.create(
            organization=self.org,
            name='Slow traffic',
            rule_type='speed_below',
            threshold=20.0,
            is_active=True,
        )
        detection = {'fiberLine': 'carros:0', 'channel': 10, 'speed': 55.0}
        triggered = evaluate_detection(detection, [rule])
        assert len(triggered) == 0

    def test_inactive_rule_not_evaluated(self):
        rule = AlertRule.objects.create(
            organization=self.org,
            name='Disabled',
            rule_type='speed_below',
            threshold=20.0,
            is_active=False,
        )
        detection = {'fiberLine': 'carros:0', 'channel': 10, 'speed': 5.0}
        triggered = evaluate_detection(detection, [rule])
        assert len(triggered) == 0

    def test_fiber_filter_restricts_evaluation(self):
        rule = AlertRule.objects.create(
            organization=self.org,
            name='Carros only',
            rule_type='speed_below',
            threshold=20.0,
            fiber_id_filter=['carros'],
            is_active=True,
        )
        # Different fiber — should not trigger
        detection = {'fiberLine': 'nice:0', 'channel': 10, 'speed': 5.0}
        triggered = evaluate_detection(detection, [rule])
        assert len(triggered) == 0

        # Matching fiber — should trigger
        detection2 = {'fiberLine': 'carros:0', 'channel': 10, 'speed': 5.0}
        triggered2 = evaluate_detection(detection2, [rule])
        assert len(triggered2) == 1

    def test_channel_range_filter(self):
        rule = AlertRule.objects.create(
            organization=self.org,
            name='Bridge zone only',
            rule_type='speed_below',
            threshold=20.0,
            channel_start=100,
            channel_end=200,
            is_active=True,
        )
        # Outside range
        detection = {'fiberLine': 'carros:0', 'channel': 50, 'speed': 5.0}
        assert len(evaluate_detection(detection, [rule])) == 0

        # Inside range
        detection2 = {'fiberLine': 'carros:0', 'channel': 150, 'speed': 5.0}
        assert len(evaluate_detection(detection2, [rule])) == 1

    def test_incident_type_rule_triggers_on_match(self):
        rule = AlertRule.objects.create(
            organization=self.org,
            name='Accident alert',
            rule_type='incident_type',
            incident_type_filter=['accident'],
            is_active=True,
        )
        incident = {
            'id': 'inc-600',
            'type': 'accident',
            'severity': 'high',
            'fiberLine': 'carros:0',
            'channel': 50,
        }
        triggered = evaluate_incident(incident, [rule])
        assert len(triggered) == 1

    def test_incident_type_rule_ignores_non_match(self):
        rule = AlertRule.objects.create(
            organization=self.org,
            name='Accident only',
            rule_type='incident_type',
            incident_type_filter=['accident'],
            is_active=True,
        )
        incident = {
            'id': 'inc-601',
            'type': 'slowdown',
            'severity': 'low',
            'fiberLine': 'carros:0',
            'channel': 50,
        }
        triggered = evaluate_incident(incident, [rule])
        assert len(triggered) == 0

    def test_severity_filter_excludes_low(self):
        rule = AlertRule.objects.create(
            organization=self.org,
            name='High severity only',
            rule_type='incident_type',
            incident_type_filter=['accident', 'congestion'],
            severity_filter=['high', 'critical'],
            is_active=True,
        )
        incident = {
            'id': 'inc-602',
            'type': 'accident',
            'severity': 'low',
            'fiberLine': 'carros:0',
            'channel': 50,
        }
        triggered = evaluate_incident(incident, [rule])
        assert len(triggered) == 0


# ---------------------------------------------------------------------------
# Dispatch tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAlertDispatch(TestCase):

    @classmethod
    def setUpTestData(cls):
        from apps.organizations.models import Organization
        cls.org = Organization.objects.create(name='Dispatch Org', slug='dispatch-org')

    def test_log_dispatch_creates_alert_log(self):
        rule = AlertRule.objects.create(
            organization=self.org,
            name='Log rule',
            rule_type='speed_below',
            threshold=20.0,
            dispatch_channel='log',
        )
        dispatch_alert(rule, 'inc-700', 'carros:0', 42, 'Speed 10 < 20')
        assert AlertLog.objects.filter(rule=rule, incident_id='inc-700').exists()

    @patch('apps.alerting.dispatch.validate_webhook_url', return_value=None)
    @patch('apps.alerting.dispatch._SYNC_MODE', True)
    @patch('apps.alerting.dispatch.time.sleep')
    @patch('apps.alerting.dispatch.http_requests.post')
    def test_webhook_dispatch_calls_url(self, mock_post, mock_sleep, *_):
        mock_post.return_value = MagicMock(status_code=200)
        rule = AlertRule.objects.create(
            organization=self.org,
            name='Webhook rule',
            rule_type='speed_below',
            threshold=20.0,
            dispatch_channel='webhook',
            webhook_url='https://hooks.example.com/alert',
        )
        dispatch_alert(rule, 'inc-701', 'carros:0', 42, 'Speed 10 < 20')
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert 'https://hooks.example.com/alert' in call_kwargs[0]

    def test_cooldown_prevents_duplicate_alerts(self):
        rule = AlertRule.objects.create(
            organization=self.org,
            name='Cooldown rule',
            rule_type='speed_below',
            threshold=20.0,
            dispatch_channel='log',
            cooldown_seconds=300,
        )
        # First dispatch — should create log
        dispatch_alert(rule, 'inc-702', 'carros:0', 42, 'Speed 10 < 20')
        assert AlertLog.objects.filter(rule=rule).count() == 1

        # Second dispatch within cooldown — should be skipped
        dispatch_alert(rule, 'inc-702', 'carros:0', 42, 'Speed 10 < 20')
        assert AlertLog.objects.filter(rule=rule).count() == 1

    def test_cooldown_allows_after_expiry(self):
        rule = AlertRule.objects.create(
            organization=self.org,
            name='Expired cooldown',
            rule_type='speed_below',
            threshold=20.0,
            dispatch_channel='log',
            cooldown_seconds=300,
        )
        # Create an old log entry
        old_log = AlertLog.objects.create(
            rule=rule,
            incident_id='inc-703',
            fiber_id='carros:0',
            channel=42,
            detail='Old alert',
        )
        # Backdate it
        AlertLog.objects.filter(pk=old_log.pk).update(
            dispatched_at=timezone.now() - timedelta(seconds=600)
        )

        # New dispatch should succeed (cooldown expired)
        dispatch_alert(rule, 'inc-703', 'carros:0', 42, 'Speed 10 < 20')
        assert AlertLog.objects.filter(rule=rule).count() == 2
