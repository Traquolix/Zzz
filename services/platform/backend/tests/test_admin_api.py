"""
TDD tests for admin REST API.

The admin API provides CRUD for:
- Organizations (superuser only)
- Users (admin role within org, or superuser)
- Infrastructure (admin role within org, or superuser)
- FiberAssignments (superuser only)
- AlertRules (admin role within org, or superuser)

Permission model:
- Superusers: full access to all resources
- Org admins: can manage users, infrastructure, and alert rules within their org
- Operators/viewers: no admin access (403)
"""

import uuid

import pytest
from django.test import TestCase
from rest_framework.test import APIClient

from apps.organizations.models import Organization, OrganizationSettings
from apps.accounts.models import User
from apps.fibers.models import FiberAssignment
from apps.monitoring.models import Infrastructure
from apps.alerting.models import AlertRule


# ---------------------------------------------------------------------------
# Permission tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAdminPermissions(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name='Perm Org', slug='perm-org')
        OrganizationSettings.objects.create(organization=cls.org)
        cls.superuser = User.objects.create_superuser(
            username='super', password='pass123', email='su@test.com',
        )
        cls.admin_user = User.objects.create_user(
            username='org_admin', password='pass123',
            organization=cls.org, role='admin',
        )
        cls.viewer = User.objects.create_user(
            username='viewer', password='pass123',
            organization=cls.org, role='viewer',
        )

    def setUp(self):
        self.client = APIClient()

    def test_superuser_can_list_organizations(self):
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.get('/api/admin/organizations')
        assert resp.status_code == 200

    def test_viewer_cannot_access_admin(self):
        self.client.force_authenticate(user=self.viewer)
        resp = self.client.get('/api/admin/organizations')
        assert resp.status_code == 403

    def test_org_admin_can_list_own_users(self):
        self.client.force_authenticate(user=self.admin_user)
        resp = self.client.get('/api/admin/users')
        assert resp.status_code == 200
        # Should only see own org's users
        usernames = [u['username'] for u in resp.data['results']]
        assert 'org_admin' in usernames
        assert 'super' not in usernames

    def test_unauthenticated_gets_401(self):
        resp = self.client.get('/api/admin/organizations')
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Organization CRUD (superuser only)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestOrganizationAdmin(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name='Existing Org', slug='existing-org')
        OrganizationSettings.objects.create(organization=cls.org)
        cls.superuser = User.objects.create_superuser(
            username='su_org', password='pass123', email='su@test.com',
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.superuser)

    def test_list_organizations(self):
        resp = self.client.get('/api/admin/organizations')
        assert resp.status_code == 200
        assert len(resp.data['results']) >= 1

    def test_create_organization(self):
        resp = self.client.post('/api/admin/organizations', {
            'name': 'New Corp',
        }, format='json')
        assert resp.status_code == 201
        assert resp.data['name'] == 'New Corp'
        assert resp.data['slug'] == 'new-corp'
        # Settings should be auto-created
        assert Organization.objects.get(slug='new-corp').settings is not None

    def test_update_organization(self):
        resp = self.client.patch(f'/api/admin/organizations/{self.org.pk}', {
            'name': 'Renamed Org',
        }, format='json')
        assert resp.status_code == 200
        self.org.refresh_from_db()
        assert self.org.name == 'Renamed Org'


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestUserAdmin(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name='User Org', slug='user-org')
        OrganizationSettings.objects.create(organization=cls.org)
        cls.admin_user = User.objects.create_user(
            username='usr_admin', password='pass123',
            organization=cls.org, role='admin',
        )
        cls.superuser = User.objects.create_superuser(
            username='su_usr', password='pass123', email='su@test.com',
        )

    def setUp(self):
        self.client = APIClient()

    def test_admin_lists_own_org_users(self):
        self.client.force_authenticate(user=self.admin_user)
        resp = self.client.get('/api/admin/users')
        assert resp.status_code == 200
        for u in resp.data['results']:
            assert u.get('organizationId') == str(self.org.pk)

    def test_superuser_lists_all_users(self):
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.get('/api/admin/users')
        assert resp.status_code == 200
        assert len(resp.data['results']) >= 2  # admin + superuser at minimum

    def test_create_user_in_org(self):
        self.client.force_authenticate(user=self.admin_user)
        resp = self.client.post('/api/admin/users', {
            'username': 'new_operator',
            'password': 'securepass123',
            'role': 'operator',
        }, format='json')
        assert resp.status_code == 201
        assert resp.data['username'] == 'new_operator'
        assert resp.data['role'] == 'operator'
        # Auto-assigned to admin's org
        new_user = User.objects.get(username='new_operator')
        assert new_user.organization == self.org

    def test_create_user_requires_password(self):
        self.client.force_authenticate(user=self.admin_user)
        resp = self.client.post('/api/admin/users', {
            'username': 'no_pass',
            'role': 'viewer',
        }, format='json')
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Infrastructure management
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestInfrastructureAdmin(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name='Infra Org', slug='infra-org')
        OrganizationSettings.objects.create(organization=cls.org)
        cls.admin_user = User.objects.create_user(
            username='infra_admin', password='pass123',
            organization=cls.org, role='admin',
        )
        FiberAssignment.objects.create(organization=cls.org, fiber_id='carros')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin_user)

    def test_create_infrastructure(self):
        resp = self.client.post('/api/admin/infrastructure', {
            'id': 'pont-napoleon',
            'name': 'Pont Napoleon III',
            'type': 'bridge',
            'fiberId': 'carros',
            'startChannel': 100,
            'endChannel': 200,
        }, format='json')
        assert resp.status_code == 201
        assert Infrastructure.objects.filter(id='pont-napoleon').exists()

    def test_list_infrastructure(self):
        Infrastructure.objects.create(
            id='tunnel-1', name='Tunnel Test', type='tunnel',
            organization=self.org, fiber_id='carros',
            start_channel=0, end_channel=50,
        )
        resp = self.client.get('/api/admin/infrastructure')
        assert resp.status_code == 200
        assert len(resp.data['results']) >= 1

    def test_delete_infrastructure(self):
        Infrastructure.objects.create(
            id='to-delete', name='Delete Me', type='bridge',
            organization=self.org, fiber_id='carros',
            start_channel=0, end_channel=50,
        )
        resp = self.client.delete('/api/admin/infrastructure/to-delete')
        assert resp.status_code == 204
        assert not Infrastructure.objects.filter(id='to-delete').exists()


# ---------------------------------------------------------------------------
# Alert rule management
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAlertRuleAdmin(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name='Rule Org', slug='rule-org')
        OrganizationSettings.objects.create(organization=cls.org)
        cls.admin_user = User.objects.create_user(
            username='rule_admin', password='pass123',
            organization=cls.org, role='admin',
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin_user)

    def test_create_alert_rule(self):
        resp = self.client.post('/api/admin/alert-rules', {
            'name': 'Slow traffic alert',
            'ruleType': 'speed_below',
            'threshold': 15.0,
            'dispatchChannel': 'log',
        }, format='json')
        assert resp.status_code == 201
        assert resp.data['name'] == 'Slow traffic alert'

    def test_list_alert_rules(self):
        AlertRule.objects.create(
            organization=self.org, name='Existing Rule',
            rule_type='speed_below', threshold=20.0,
        )
        resp = self.client.get('/api/admin/alert-rules')
        assert resp.status_code == 200
        assert len(resp.data['results']) >= 1

    def test_update_alert_rule(self):
        rule = AlertRule.objects.create(
            organization=self.org, name='Old Name',
            rule_type='speed_below', threshold=20.0,
        )
        resp = self.client.patch(f'/api/admin/alert-rules/{rule.pk}', {
            'name': 'New Name',
            'threshold': 25.0,
        }, format='json')
        assert resp.status_code == 200
        rule.refresh_from_db()
        assert rule.name == 'New Name'
        assert rule.threshold == 25.0

    def test_delete_alert_rule(self):
        rule = AlertRule.objects.create(
            organization=self.org, name='To Delete',
            rule_type='speed_below', threshold=20.0,
        )
        resp = self.client.delete(f'/api/admin/alert-rules/{rule.pk}')
        assert resp.status_code == 204
        assert not AlertRule.objects.filter(pk=rule.pk).exists()
