"""
TDD tests for admin API pagination and search.

Tests verify that:
1. Search filters work correctly on all list endpoints
2. Pagination (offset/limit) works correctly
3. Response shape includes total, offset, hasMore
4. Search is case-insensitive
5. hasMore flag is accurate
"""

import pytest
from django.test import TestCase
from rest_framework.test import APIClient

from apps.organizations.models import Organization, OrganizationSettings
from apps.accounts.models import User
from apps.monitoring.models import Infrastructure
from apps.alerting.models import AlertRule, AlertLog
from apps.fibers.models import FiberAssignment


@pytest.mark.django_db
class TestUserAdminPagination(TestCase):
    """Test pagination and search on user list endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name='Test Org', slug='test-org')
        OrganizationSettings.objects.create(organization=cls.org)
        cls.superuser = User.objects.create_superuser(
            username='super', password='pass123', email='super@test.com',
        )
        # Create test users
        User.objects.create_user(
            username='alice', password='pass123', email='alice@test.com',
            organization=cls.org, role='viewer',
        )
        User.objects.create_user(
            username='bob', password='pass123', email='bob@test.com',
            organization=cls.org, role='admin',
        )
        User.objects.create_user(
            username='charlie', password='pass123', email='charlie@test.com',
            organization=cls.org, role='operator',
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.superuser)

    def test_list_includes_pagination_fields(self):
        """Response includes offset, limit, total, hasMore."""
        resp = self.client.get('/api/admin/users')
        assert resp.status_code == 200
        assert 'results' in resp.data
        assert 'offset' in resp.data
        assert 'limit' in resp.data
        assert 'total' in resp.data
        assert 'hasMore' in resp.data
        assert isinstance(resp.data['offset'], int)
        assert isinstance(resp.data['limit'], int)
        assert isinstance(resp.data['total'], int)
        assert isinstance(resp.data['hasMore'], bool)

    def test_search_filters_by_username(self):
        """?search=alice filters on username (case-insensitive)."""
        resp = self.client.get('/api/admin/users?search=alice')
        assert resp.status_code == 200
        assert len(resp.data['results']) == 1
        assert resp.data['results'][0]['username'] == 'alice'

    def test_search_filters_by_email(self):
        """?search=bob@test filters on email."""
        resp = self.client.get('/api/admin/users?search=bob@test')
        assert resp.status_code == 200
        assert len(resp.data['results']) == 1
        assert resp.data['results'][0]['email'] == 'bob@test.com'

    def test_search_case_insensitive(self):
        """Search is case-insensitive."""
        resp = self.client.get('/api/admin/users?search=ALICE')
        assert resp.status_code == 200
        assert len(resp.data['results']) == 1
        assert resp.data['results'][0]['username'] == 'alice'

    def test_search_no_matches_returns_empty(self):
        """Search with no matches returns empty results."""
        resp = self.client.get('/api/admin/users?search=nonexistent')
        assert resp.status_code == 200
        assert len(resp.data['results']) == 0
        assert resp.data['total'] == 0
        assert resp.data['hasMore'] is False

    def test_offset_and_limit(self):
        """?offset=1&limit=2 returns correct page."""
        resp = self.client.get('/api/admin/users?offset=1&limit=2')
        assert resp.status_code == 200
        assert resp.data['offset'] == 1
        assert resp.data['limit'] == 2
        assert len(resp.data['results']) <= 2

    def test_has_more_flag_true(self):
        """hasMore=true when more results exist beyond this page."""
        resp = self.client.get('/api/admin/users?limit=1')
        assert resp.status_code == 200
        # Should have more than 1 user (alice, bob, charlie, super)
        if resp.data['total'] > 1:
            assert resp.data['hasMore'] is True

    def test_has_more_flag_false(self):
        """hasMore=false when no more results."""
        resp = self.client.get('/api/admin/users?offset=100')
        assert resp.status_code == 200
        assert resp.data['hasMore'] is False

    def test_total_count_correct(self):
        """total reflects actual count of all matching items."""
        resp = self.client.get('/api/admin/users')
        assert resp.status_code == 200
        # Should be at least superuser + 3 test users
        assert resp.data['total'] >= 4


@pytest.mark.django_db
class TestOrganizationAdminPagination(TestCase):
    """Test pagination and search on organization list endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username='super', password='pass123', email='su@test.com',
        )
        # Create test orgs
        org1 = Organization.objects.create(name='Acme Corp', slug='acme-corp')
        org2 = Organization.objects.create(name='Beta Industries', slug='beta-ind')
        org3 = Organization.objects.create(name='Gamma Systems', slug='gamma-sys')
        OrganizationSettings.objects.create(organization=org1)
        OrganizationSettings.objects.create(organization=org2)
        OrganizationSettings.objects.create(organization=org3)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.superuser)

    def test_search_filters_by_name(self):
        """?search=acme filters on organization name."""
        resp = self.client.get('/api/admin/organizations?search=acme')
        assert resp.status_code == 200
        assert len(resp.data['results']) == 1
        assert resp.data['results'][0]['name'] == 'Acme Corp'

    def test_search_filters_by_slug(self):
        """?search=beta-ind filters on slug."""
        resp = self.client.get('/api/admin/organizations?search=beta-ind')
        assert resp.status_code == 200
        assert len(resp.data['results']) == 1
        assert resp.data['results'][0]['slug'] == 'beta-ind'

    def test_pagination_response_shape(self):
        """Response includes all pagination fields."""
        resp = self.client.get('/api/admin/organizations')
        assert resp.status_code == 200
        assert 'offset' in resp.data
        assert 'limit' in resp.data
        assert 'total' in resp.data
        assert 'hasMore' in resp.data


@pytest.mark.django_db
class TestAlertRuleAdminPagination(TestCase):
    """Test pagination and search on alert rules endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name='Rule Org', slug='rule-org')
        OrganizationSettings.objects.create(organization=cls.org)
        cls.admin = User.objects.create_user(
            username='admin', password='pass123',
            organization=cls.org, role='admin',
        )
        # Create test rules
        AlertRule.objects.create(
            organization=cls.org, name='Speed Alert',
            rule_type='speed_below', threshold=20.0,
        )
        AlertRule.objects.create(
            organization=cls.org, name='Fiber Break',
            rule_type='fiber_cut', threshold=None,
        )
        AlertRule.objects.create(
            organization=cls.org, name='High Temperature',
            rule_type='temperature', threshold=85.0,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_search_filters_by_name(self):
        """?search=speed filters on rule name."""
        resp = self.client.get('/api/admin/alert-rules?search=speed')
        assert resp.status_code == 200
        assert len(resp.data['results']) == 1
        assert resp.data['results'][0]['name'] == 'Speed Alert'

    def test_search_filters_by_rule_type(self):
        """?search=fiber_cut filters on rule_type."""
        resp = self.client.get('/api/admin/alert-rules?search=fiber_cut')
        assert resp.status_code == 200
        assert len(resp.data['results']) == 1
        assert resp.data['results'][0]['ruleType'] == 'fiber_cut'

    def test_pagination_response_shape(self):
        """Response includes all pagination fields."""
        resp = self.client.get('/api/admin/alert-rules')
        assert resp.status_code == 200
        assert 'offset' in resp.data
        assert 'limit' in resp.data
        assert 'total' in resp.data
        assert 'hasMore' in resp.data
        assert resp.data['total'] == 3


@pytest.mark.django_db
class TestInfrastructureAdminPagination(TestCase):
    """Test pagination and search on infrastructure endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name='Infra Org', slug='infra-org')
        OrganizationSettings.objects.create(organization=cls.org)
        cls.admin = User.objects.create_user(
            username='admin', password='pass123',
            organization=cls.org, role='admin',
        )
        FiberAssignment.objects.create(organization=cls.org, fiber_id='carros')
        # Create test infrastructure
        Infrastructure.objects.create(
            id='bridge-1', name='Golden Bridge', type='bridge',
            organization=cls.org, fiber_id='carros',
            start_channel=0, end_channel=50,
        )
        Infrastructure.objects.create(
            id='tunnel-1', name='Mountain Tunnel', type='tunnel',
            organization=cls.org, fiber_id='carros',
            start_channel=100, end_channel=150,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_search_filters_by_name(self):
        """?search=golden filters on name."""
        resp = self.client.get('/api/admin/infrastructure?search=golden')
        assert resp.status_code == 200
        assert len(resp.data['results']) == 1
        assert resp.data['results'][0]['name'] == 'Golden Bridge'

    def test_search_filters_by_type(self):
        """?search=tunnel filters on type."""
        resp = self.client.get('/api/admin/infrastructure?search=tunnel')
        assert resp.status_code == 200
        assert len(resp.data['results']) == 1
        assert resp.data['results'][0]['type'] == 'tunnel'

    def test_pagination_response_shape(self):
        """Response includes all pagination fields."""
        resp = self.client.get('/api/admin/infrastructure')
        assert resp.status_code == 200
        assert 'offset' in resp.data
        assert 'limit' in resp.data
        assert 'total' in resp.data
        assert 'hasMore' in resp.data
        assert resp.data['total'] == 2


@pytest.mark.django_db
class TestAlertLogAdminPagination(TestCase):
    """Test pagination and search on alert logs endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name='Log Org', slug='log-org')
        OrganizationSettings.objects.create(organization=cls.org)
        cls.admin = User.objects.create_user(
            username='admin', password='pass123',
            organization=cls.org, role='admin',
        )
        rule1 = AlertRule.objects.create(
            organization=cls.org, name='Alert 1',
            rule_type='speed_below', threshold=20.0,
        )
        rule2 = AlertRule.objects.create(
            organization=cls.org, name='Alert 2',
            rule_type='fiber_cut',
        )
        # Create test logs
        AlertLog.objects.create(
            rule=rule1, fiber_id='fiber-a', channel=10,
            detail='Speed dropped below threshold',
        )
        AlertLog.objects.create(
            rule=rule2, fiber_id='fiber-b', channel=20,
            detail='Fiber break detected',
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_search_filters_by_rule_name(self):
        """?search=alert filters on rule name (case-insensitive)."""
        resp = self.client.get('/api/admin/alert-logs?search=alert')
        assert resp.status_code == 200
        assert len(resp.data['results']) >= 1
        # Should match "Alert 1" and "Alert 2"
        found_names = {r['ruleName'] for r in resp.data['results']}
        assert any('Alert' in name for name in found_names)

    def test_search_filters_by_detail(self):
        """?search=fiber filters on detail."""
        resp = self.client.get('/api/admin/alert-logs?search=fiber')
        assert resp.status_code == 200
        assert len(resp.data['results']) >= 1

    def test_pagination_response_shape(self):
        """Response includes all pagination fields."""
        resp = self.client.get('/api/admin/alert-logs')
        assert resp.status_code == 200
        assert 'offset' in resp.data
        assert 'limit' in resp.data
        assert 'total' in resp.data
        assert 'hasMore' in resp.data


@pytest.mark.django_db
class TestPaginationLimit(TestCase):
    """Test that limit is capped at 200."""

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name='Org', slug='org')
        OrganizationSettings.objects.create(organization=cls.org)
        cls.superuser = User.objects.create_superuser(
            username='super', password='pass123', email='su@test.com',
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.superuser)

    def test_limit_capped_at_200(self):
        """Request with limit > 200 is capped to 200."""
        resp = self.client.get('/api/admin/users?limit=500')
        assert resp.status_code == 200
        assert resp.data['limit'] == 200


@pytest.mark.django_db
class TestSearchEmptyQuery(TestCase):
    """Test search behavior with empty or whitespace queries."""

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name='Org', slug='org')
        OrganizationSettings.objects.create(organization=cls.org)
        cls.admin = User.objects.create_user(
            username='admin', password='pass123',
            organization=cls.org, role='admin',
        )
        User.objects.create_user(
            username='test', password='pass123',
            organization=cls.org, role='viewer',
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_empty_search_returns_all(self):
        """?search= (empty) returns all results."""
        resp = self.client.get('/api/admin/users?search=')
        assert resp.status_code == 200
        # Should return all users in org
        assert len(resp.data['results']) >= 2

    def test_whitespace_search_returns_all(self):
        """?search=   (whitespace) returns all results."""
        resp = self.client.get('/api/admin/users?search=%20%20%20')
        assert resp.status_code == 200
        assert len(resp.data['results']) >= 2
