"""
Tests for OrgSettingsView — organization-level settings management.
"""

import pytest
from django.test import TestCase
from rest_framework.test import APIClient

from apps.organizations.models import Organization, OrganizationSettings
from apps.accounts.models import User


@pytest.mark.django_db
class TestOrgSettingsView(TestCase):
    """Test organization settings endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name='Settings Test Org', slug='settings-test-org')
        cls.settings = OrganizationSettings.objects.create(
            organization=cls.org,
            timezone='Europe/Paris',
            speed_alert_threshold=20.0,
            incident_auto_resolve_minutes=30,
            shm_enabled=True,
            allowed_widgets=[],
            allowed_layers=[],
        )
        cls.other_org = Organization.objects.create(name='Other Org', slug='other-org')
        cls.other_settings = OrganizationSettings.objects.create(organization=cls.other_org)

        cls.superuser = User.objects.create_superuser(
            username='su_settings', password='pass123', email='su@test.com'
        )
        cls.admin_user = User.objects.create_user(
            username='admin_settings',
            password='pass123',
            organization=cls.org,
            role='admin',
        )
        cls.other_admin = User.objects.create_user(
            username='admin_other',
            password='pass123',
            organization=cls.other_org,
            role='admin',
        )

    def setUp(self):
        self.client = APIClient()

    def test_get_settings_returns_correct_shape_superuser(self):
        """Superuser can GET settings and gets correct response shape."""
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.get(f'/api/admin/organizations/{self.org.pk}/settings')
        assert resp.status_code == 200
        assert 'timezone' in resp.data
        assert 'speedAlertThreshold' in resp.data
        assert 'incidentAutoResolveMinutes' in resp.data
        assert 'shmEnabled' in resp.data
        assert 'allowedWidgets' in resp.data
        assert 'allowedLayers' in resp.data

    def test_patch_timezone_updates(self):
        """Superuser can update timezone."""
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.patch(
            f'/api/admin/organizations/{self.org.pk}/settings',
            {'timezone': 'America/New_York'},
            format='json'
        )
        assert resp.status_code == 200
        self.settings.refresh_from_db()
        assert self.settings.timezone == 'America/New_York'

    def test_patch_widgets_validates_invalid_keys(self):
        """Superuser patch with invalid widget keys returns 400."""
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.patch(
            f'/api/admin/organizations/{self.org.pk}/settings',
            {'allowedWidgets': ['map', 'invalid_widget']},
            format='json'
        )
        assert resp.status_code == 400
        assert 'Invalid widget keys' in resp.data['detail']

    def test_patch_widgets_succeeds_valid_keys(self):
        """Superuser patch with valid widget keys succeeds."""
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.patch(
            f'/api/admin/organizations/{self.org.pk}/settings',
            {'allowedWidgets': ['map', 'incidents']},
            format='json'
        )
        assert resp.status_code == 200
        self.settings.refresh_from_db()
        assert self.settings.allowed_widgets == ['map', 'incidents']

    def test_org_admin_can_edit_own_org_timezone(self):
        """Org admin can edit timezone for their own org."""
        self.client.force_authenticate(user=self.admin_user)
        resp = self.client.patch(
            f'/api/admin/organizations/{self.org.pk}/settings',
            {'timezone': 'Europe/London'},
            format='json'
        )
        assert resp.status_code == 200
        self.settings.refresh_from_db()
        assert self.settings.timezone == 'Europe/London'

    def test_org_admin_cannot_edit_widgets(self):
        """Org admin cannot edit allowed_widgets (403)."""
        self.client.force_authenticate(user=self.admin_user)
        resp = self.client.patch(
            f'/api/admin/organizations/{self.org.pk}/settings',
            {'allowedWidgets': ['map']},
            format='json'
        )
        assert resp.status_code == 403
        assert 'Only superusers can edit widget restrictions' in resp.data['detail']

    def test_org_admin_cannot_edit_layers(self):
        """Org admin cannot edit allowed_layers (403)."""
        self.client.force_authenticate(user=self.admin_user)
        resp = self.client.patch(
            f'/api/admin/organizations/{self.org.pk}/settings',
            {'allowedLayers': ['cables']},
            format='json'
        )
        assert resp.status_code == 403
        assert 'Only superusers can edit layer restrictions' in resp.data['detail']

    def test_org_admin_cannot_access_other_org_settings(self):
        """Org admin cannot access settings for another org (403)."""
        self.client.force_authenticate(user=self.admin_user)
        resp = self.client.get(f'/api/admin/organizations/{self.other_org.pk}/settings')
        assert resp.status_code == 403

    def test_org_admin_cannot_patch_other_org_settings(self):
        """Org admin cannot patch settings for another org (403)."""
        self.client.force_authenticate(user=self.admin_user)
        resp = self.client.patch(
            f'/api/admin/organizations/{self.other_org.pk}/settings',
            {'timezone': 'UTC'},
            format='json'
        )
        assert resp.status_code == 403

    def test_superuser_can_access_any_org_settings(self):
        """Superuser can access settings for any org."""
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.get(f'/api/admin/organizations/{self.other_org.pk}/settings')
        assert resp.status_code == 200

    def test_nonexistent_org_settings_returns_404(self):
        """Requesting settings for nonexistent org returns 404."""
        self.client.force_authenticate(user=self.superuser)
        fake_org_id = '00000000-0000-0000-0000-000000000000'
        resp = self.client.get(f'/api/admin/organizations/{fake_org_id}/settings')
        assert resp.status_code == 404

    def test_patch_speed_alert_threshold(self):
        """Org admin can update speed_alert_threshold."""
        self.client.force_authenticate(user=self.admin_user)
        resp = self.client.patch(
            f'/api/admin/organizations/{self.org.pk}/settings',
            {'speedAlertThreshold': 25.5},
            format='json'
        )
        assert resp.status_code == 200
        self.settings.refresh_from_db()
        assert self.settings.speed_alert_threshold == 25.5

    def test_patch_incident_auto_resolve_minutes(self):
        """Org admin can update incident_auto_resolve_minutes."""
        self.client.force_authenticate(user=self.admin_user)
        resp = self.client.patch(
            f'/api/admin/organizations/{self.org.pk}/settings',
            {'incidentAutoResolveMinutes': 60},
            format='json'
        )
        assert resp.status_code == 200
        self.settings.refresh_from_db()
        assert self.settings.incident_auto_resolve_minutes == 60

    def test_patch_shm_enabled(self):
        """Org admin can update shm_enabled."""
        self.client.force_authenticate(user=self.admin_user)
        resp = self.client.patch(
            f'/api/admin/organizations/{self.org.pk}/settings',
            {'shmEnabled': False},
            format='json'
        )
        assert resp.status_code == 200
        self.settings.refresh_from_db()
        assert self.settings.shm_enabled is False
