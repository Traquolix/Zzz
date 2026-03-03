"""
TDD tests for incident workflow state machine.

The workflow is: detected → acknowledged → investigating → resolved
Each transition is an IncidentAction record in PostgreSQL, keyed by
the ClickHouse incident_id. The API should:

1. Accept state transitions with validation
2. Reject invalid transitions (e.g., resolved → acknowledged)
3. Record operator identity and timestamps
4. Support notes on any action
5. Return the full action history for an incident
6. Org-scope: only allow actions on incidents from the user's fibers
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.monitoring.models import IncidentAction
from apps.monitoring.workflow import (
    VALID_TRANSITIONS,
    validate_transition,
    get_current_status,
    InvalidTransitionError,
)


# ---------------------------------------------------------------------------
# Unit tests — workflow state machine (pure logic, no DB)
# ---------------------------------------------------------------------------


class TestValidTransitions:
    """The state machine defines which transitions are legal."""

    def test_detected_can_be_acknowledged(self):
        assert 'acknowledged' in VALID_TRANSITIONS['active']

    def test_detected_can_be_resolved(self):
        assert 'resolved' in VALID_TRANSITIONS['active']

    def test_acknowledged_can_move_to_investigating(self):
        assert 'investigating' in VALID_TRANSITIONS['acknowledged']

    def test_acknowledged_can_be_resolved(self):
        assert 'resolved' in VALID_TRANSITIONS['acknowledged']

    def test_investigating_can_be_resolved(self):
        assert 'resolved' in VALID_TRANSITIONS['investigating']

    def test_resolved_cannot_transition(self):
        assert VALID_TRANSITIONS.get('resolved', set()) == set()

    def test_resolved_to_acknowledged_is_invalid(self):
        with pytest.raises(InvalidTransitionError):
            validate_transition('resolved', 'acknowledged')

    def test_active_to_investigating_is_invalid(self):
        # Must acknowledge first
        with pytest.raises(InvalidTransitionError):
            validate_transition('active', 'investigating')

    def test_same_state_transition_is_invalid(self):
        with pytest.raises(InvalidTransitionError):
            validate_transition('acknowledged', 'acknowledged')


# ---------------------------------------------------------------------------
# Model tests — IncidentAction in PostgreSQL
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestIncidentActionModel(TestCase):
    """IncidentAction stores workflow transitions in PostgreSQL."""

    @classmethod
    def setUpTestData(cls):
        from apps.organizations.models import Organization
        from apps.accounts.models import User

        cls.org = Organization.objects.create(name='Test Org', slug='test-org')
        cls.user = User.objects.create_user(
            username='operator1',
            password='testpass123',
            organization=cls.org,
            role='operator',
        )

    def test_create_action(self):
        action = IncidentAction.objects.create(
            incident_id='inc-001',
            from_status='active',
            to_status='acknowledged',
            performed_by=self.user,
            note='Taking ownership',
        )
        assert action.pk is not None
        assert action.incident_id == 'inc-001'
        assert action.to_status == 'acknowledged'
        assert action.performed_by == self.user
        assert action.note == 'Taking ownership'
        assert action.performed_at is not None

    def test_action_ordering_is_newest_first(self):
        IncidentAction.objects.create(
            incident_id='inc-002',
            from_status='active',
            to_status='acknowledged',
            performed_by=self.user,
        )
        IncidentAction.objects.create(
            incident_id='inc-002',
            from_status='acknowledged',
            to_status='investigating',
            performed_by=self.user,
        )
        actions = list(IncidentAction.objects.filter(incident_id='inc-002'))
        assert actions[0].to_status == 'investigating'
        assert actions[1].to_status == 'acknowledged'

    def test_get_current_status_with_no_actions(self):
        """No actions recorded → status is whatever ClickHouse says (active)."""
        status = get_current_status('inc-nonexistent')
        assert status == 'active'

    def test_get_current_status_with_actions(self):
        IncidentAction.objects.create(
            incident_id='inc-003',
            from_status='active',
            to_status='acknowledged',
            performed_by=self.user,
        )
        IncidentAction.objects.create(
            incident_id='inc-003',
            from_status='acknowledged',
            to_status='investigating',
            performed_by=self.user,
        )
        status = get_current_status('inc-003')
        assert status == 'investigating'


# ---------------------------------------------------------------------------
# API tests — POST /api/incidents/<id>/actions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestIncidentActionAPI(TestCase):
    """API endpoint for recording incident workflow transitions."""

    @classmethod
    def setUpTestData(cls):
        from apps.organizations.models import Organization
        from apps.accounts.models import User
        from apps.fibers.models import FiberAssignment

        cls.org = Organization.objects.create(name='API Org', slug='api-org')
        cls.operator = User.objects.create_user(
            username='api_operator',
            password='testpass123',
            organization=cls.org,
            role='operator',
        )
        cls.other_org = Organization.objects.create(name='Other Org', slug='other-org')
        cls.other_user = User.objects.create_user(
            username='other_user',
            password='testpass123',
            organization=cls.other_org,
            role='operator',
        )
        # Assign fiber "carros" to API Org
        FiberAssignment.objects.create(
            organization=cls.org,
            fiber_id='carros',
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.operator)

    @patch('apps.monitoring.views.incident_query_by_id')
    def test_acknowledge_incident(self, mock_query):
        mock_query.return_value = {
            'incident_id': 'inc-100',
            'fiber_id': 'carros:0',
            'status': 'active',
        }
        resp = self.client.post('/api/incidents/inc-100/actions', {
            'action': 'acknowledged',
            'note': 'On it',
        }, format='json')
        assert resp.status_code == 201
        assert resp.data['toStatus'] == 'acknowledged'
        assert resp.data['performedBy'] == 'api_operator'
        assert resp.data['note'] == 'On it'

    @patch('apps.monitoring.views.incident_query_by_id')
    def test_invalid_transition_returns_409(self, mock_query):
        mock_query.return_value = {
            'incident_id': 'inc-101',
            'fiber_id': 'carros:0',
            'status': 'active',
        }
        # active → investigating is invalid (must acknowledge first)
        resp = self.client.post('/api/incidents/inc-101/actions', {
            'action': 'investigating',
        }, format='json')
        assert resp.status_code == 409
        assert resp.data['code'] == 'invalid_transition'

    @patch('apps.monitoring.views.incident_query_by_id')
    def test_org_scoping_denies_other_org(self, mock_query):
        mock_query.return_value = {
            'incident_id': 'inc-102',
            'fiber_id': 'carros:0',
            'status': 'active',
        }
        self.client.force_authenticate(user=self.other_user)
        resp = self.client.post('/api/incidents/inc-102/actions', {
            'action': 'acknowledged',
        }, format='json')
        assert resp.status_code == 404
        assert resp.data['code'] == 'incident_not_found'

    @patch('apps.monitoring.views.incident_query_by_id')
    def test_nonexistent_incident_returns_404(self, mock_query):
        mock_query.return_value = None
        resp = self.client.post('/api/incidents/inc-ghost/actions', {
            'action': 'acknowledged',
        }, format='json')
        assert resp.status_code == 404

    @patch('apps.monitoring.views.incident_query_by_id')
    def test_missing_action_field_returns_400(self, mock_query):
        mock_query.return_value = {
            'incident_id': 'inc-103',
            'fiber_id': 'carros:0',
            'status': 'active',
        }
        resp = self.client.post('/api/incidents/inc-103/actions', {}, format='json')
        assert resp.status_code == 400

    @patch('apps.monitoring.views.incident_query_by_id')
    def test_full_workflow_sequence(self, mock_query):
        """Walk through the entire lifecycle: active → acknowledged → investigating → resolved."""
        mock_query.return_value = {
            'incident_id': 'inc-200',
            'fiber_id': 'carros:0',
            'status': 'active',
        }

        # 1. Acknowledge
        resp = self.client.post('/api/incidents/inc-200/actions', {
            'action': 'acknowledged',
        }, format='json')
        assert resp.status_code == 201

        # 2. Investigate
        resp = self.client.post('/api/incidents/inc-200/actions', {
            'action': 'investigating',
            'note': 'Checking cameras',
        }, format='json')
        assert resp.status_code == 201

        # 3. Resolve
        resp = self.client.post('/api/incidents/inc-200/actions', {
            'action': 'resolved',
            'note': 'False alarm - construction crew',
        }, format='json')
        assert resp.status_code == 201

        # Verify final status
        assert get_current_status('inc-200') == 'resolved'

    @patch('apps.monitoring.views.incident_query_by_id')
    def test_resolve_already_resolved_returns_409(self, mock_query):
        mock_query.return_value = {
            'incident_id': 'inc-201',
            'fiber_id': 'carros:0',
            'status': 'active',
        }
        # Resolve directly
        self.client.post('/api/incidents/inc-201/actions', {
            'action': 'resolved',
        }, format='json')
        # Try again
        resp = self.client.post('/api/incidents/inc-201/actions', {
            'action': 'resolved',
        }, format='json')
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# API tests — GET /api/incidents/<id>/actions (action history)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestIncidentActionHistoryAPI(TestCase):
    """GET endpoint returns the full action log for an incident."""

    @classmethod
    def setUpTestData(cls):
        from apps.organizations.models import Organization
        from apps.accounts.models import User
        from apps.fibers.models import FiberAssignment

        cls.org = Organization.objects.create(name='History Org', slug='history-org')
        cls.user = User.objects.create_user(
            username='hist_operator',
            password='testpass123',
            organization=cls.org,
            role='operator',
        )
        FiberAssignment.objects.create(organization=cls.org, fiber_id='carros')

        # Pre-create some actions
        IncidentAction.objects.create(
            incident_id='inc-300',
            from_status='active',
            to_status='acknowledged',
            performed_by=cls.user,
            note='Got it',
        )
        IncidentAction.objects.create(
            incident_id='inc-300',
            from_status='acknowledged',
            to_status='investigating',
            performed_by=cls.user,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch('apps.monitoring.views.incident_query_by_id')
    def test_returns_action_history(self, mock_query):
        mock_query.return_value = {
            'incident_id': 'inc-300',
            'fiber_id': 'carros:0',
            'status': 'active',
        }
        resp = self.client.get('/api/incidents/inc-300/actions')
        assert resp.status_code == 200
        assert resp.data['currentStatus'] == 'investigating'
        assert len(resp.data['actions']) == 2
        # Newest first
        assert resp.data['actions'][0]['toStatus'] == 'investigating'
        assert resp.data['actions'][1]['toStatus'] == 'acknowledged'
        assert resp.data['actions'][1]['note'] == 'Got it'

    @patch('apps.monitoring.views.incident_query_by_id')
    def test_empty_history_returns_active(self, mock_query):
        mock_query.return_value = {
            'incident_id': 'inc-301',
            'fiber_id': 'carros:0',
            'status': 'active',
        }
        resp = self.client.get('/api/incidents/inc-301/actions')
        assert resp.status_code == 200
        assert resp.data['currentStatus'] == 'active'
        assert resp.data['actions'] == []
