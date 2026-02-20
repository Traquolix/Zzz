"""
Tests for signal-based audit logging.

Verifies that post_save signals on tracked models (User, Infrastructure,
Organization, OrganizationSettings) correctly create AuditLog entries,
and that untracked models do NOT trigger audit logging.
"""

import pytest

from apps.shared.models import AuditLog
from tests.factories import (
    OrganizationFactory,
    OrganizationSettingsFactory,
    UserFactory,
    InfrastructureFactory,
    UserPreferencesFactory,
)


pytestmark = pytest.mark.django_db


class TestUserAuditSignals:
    """Audit signals for the User model."""

    def test_creating_user_creates_audit_log(self):
        """Creating a new User should produce a USER_CREATED audit entry."""
        initial_count = AuditLog.objects.count()
        user = UserFactory(username='audit_new_user')
        logs = AuditLog.objects.filter(
            action=AuditLog.Action.USER_CREATED,
            object_type='User',
            object_id=str(user.pk),
        )
        assert logs.exists(), 'Expected USER_CREATED audit log after user creation'
        assert AuditLog.objects.count() > initial_count

    def test_creating_user_audit_has_correct_fields(self):
        """The audit entry for user creation should contain relevant fields."""
        user = UserFactory(username='audit_fields_user')
        log = AuditLog.objects.filter(
            action=AuditLog.Action.USER_CREATED,
            object_id=str(user.pk),
        ).first()
        assert log is not None
        assert log.object_type == 'User'
        assert log.organization == user.organization
        # Changes dict should include username
        assert 'username' in log.changes
        assert log.changes['username'] == 'audit_fields_user'

    def test_updating_user_creates_audit_log(self):
        """Updating an existing User should produce a USER_UPDATED audit entry."""
        user = UserFactory(username='audit_update_user')
        # Clear the creation log check
        create_count = AuditLog.objects.filter(
            action=AuditLog.Action.USER_CREATED,
            object_id=str(user.pk),
        ).count()
        assert create_count == 1

        # Update the user
        user.role = 'operator'
        user.save()

        update_logs = AuditLog.objects.filter(
            action=AuditLog.Action.USER_UPDATED,
            object_type='User',
            object_id=str(user.pk),
        )
        assert update_logs.exists(), 'Expected USER_UPDATED audit log after user update'

    def test_updating_user_audit_reflects_new_values(self):
        """The changes dict on update should reflect the new field values."""
        user = UserFactory(username='audit_reflect_user', role='viewer')
        user.role = 'operator'
        user.save()

        log = AuditLog.objects.filter(
            action=AuditLog.Action.USER_UPDATED,
            object_id=str(user.pk),
        ).first()
        assert log is not None
        assert log.changes['role'] == 'operator'


class TestInfrastructureAuditSignals:
    """Audit signals for the Infrastructure model."""

    def test_creating_infrastructure_creates_audit_log(self):
        """Creating Infrastructure should produce an INFRASTRUCTURE_UPDATED audit entry."""
        org = OrganizationFactory()
        infra = InfrastructureFactory(
            organization=org,
            id='bridge-audit-test',
            name='Audit Bridge',
        )
        logs = AuditLog.objects.filter(
            action=AuditLog.Action.INFRASTRUCTURE_UPDATED,
            object_type='Infrastructure',
            object_id=str(infra.pk),
        )
        assert logs.exists(), (
            'Expected INFRASTRUCTURE_UPDATED audit log after infrastructure creation'
        )

    def test_creating_infrastructure_audit_has_org(self):
        """The audit entry should reference the infrastructure's organization."""
        org = OrganizationFactory()
        infra = InfrastructureFactory(organization=org, id='bridge-audit-org')
        log = AuditLog.objects.filter(
            action=AuditLog.Action.INFRASTRUCTURE_UPDATED,
            object_id=str(infra.pk),
        ).first()
        assert log is not None
        assert log.organization == org

    def test_updating_infrastructure_creates_audit_log(self):
        """Updating Infrastructure should produce an INFRASTRUCTURE_UPDATED entry."""
        org = OrganizationFactory()
        infra = InfrastructureFactory(organization=org, id='bridge-audit-upd')
        initial_count = AuditLog.objects.filter(
            action=AuditLog.Action.INFRASTRUCTURE_UPDATED,
            object_id=str(infra.pk),
        ).count()

        infra.name = 'Updated Bridge Name'
        infra.save()

        new_count = AuditLog.objects.filter(
            action=AuditLog.Action.INFRASTRUCTURE_UPDATED,
            object_id=str(infra.pk),
        ).count()
        assert new_count == initial_count + 1

    def test_updating_infrastructure_audit_reflects_new_values(self):
        """Changes dict should contain the new name after update."""
        org = OrganizationFactory()
        infra = InfrastructureFactory(
            organization=org, id='bridge-audit-val', name='Old Name'
        )
        infra.name = 'New Name'
        infra.save()

        log = AuditLog.objects.filter(
            action=AuditLog.Action.INFRASTRUCTURE_UPDATED,
            object_id=str(infra.pk),
        ).order_by('-created_at').first()
        assert log is not None
        assert log.changes['name'] == 'New Name'


class TestOrganizationAuditSignals:
    """Audit signals for the Organization model."""

    def test_creating_organization_creates_audit_log(self):
        """Creating an Organization should produce an ORG_SETTINGS_UPDATED audit entry."""
        org = OrganizationFactory(name='Audit Test Org')
        logs = AuditLog.objects.filter(
            action=AuditLog.Action.ORG_SETTINGS_UPDATED,
            object_type='Organization',
            object_id=str(org.pk),
        )
        assert logs.exists(), (
            'Expected ORG_SETTINGS_UPDATED audit log after organization creation'
        )

    def test_creating_organization_audit_references_self(self):
        """The audit entry org field should reference the created org itself."""
        org = OrganizationFactory(name='Self Ref Org')
        log = AuditLog.objects.filter(
            action=AuditLog.Action.ORG_SETTINGS_UPDATED,
            object_type='Organization',
            object_id=str(org.pk),
        ).first()
        assert log is not None
        assert log.organization == org

    def test_updating_organization_creates_audit_log(self):
        """Updating an Organization should produce another audit entry."""
        org = OrganizationFactory(name='Org Before Update')
        initial_count = AuditLog.objects.filter(
            action=AuditLog.Action.ORG_SETTINGS_UPDATED,
            object_type='Organization',
            object_id=str(org.pk),
        ).count()

        org.name = 'Org After Update'
        org.save()

        new_count = AuditLog.objects.filter(
            action=AuditLog.Action.ORG_SETTINGS_UPDATED,
            object_type='Organization',
            object_id=str(org.pk),
        ).count()
        assert new_count == initial_count + 1

    def test_organization_settings_creates_audit_log(self):
        """Creating OrganizationSettings should also produce an audit entry."""
        org = OrganizationFactory(name='Settings Audit Org')
        settings = OrganizationSettingsFactory(organization=org)
        logs = AuditLog.objects.filter(
            action=AuditLog.Action.ORG_SETTINGS_UPDATED,
            object_type='OrganizationSettings',
            object_id=str(settings.pk),
        )
        assert logs.exists(), (
            'Expected ORG_SETTINGS_UPDATED audit log after OrganizationSettings creation'
        )

    def test_updating_organization_settings_creates_audit_log(self):
        """Updating OrganizationSettings should produce another audit entry."""
        org = OrganizationFactory()
        settings = OrganizationSettingsFactory(organization=org)
        initial_count = AuditLog.objects.filter(
            action=AuditLog.Action.ORG_SETTINGS_UPDATED,
            object_type='OrganizationSettings',
            object_id=str(settings.pk),
        ).count()

        settings.timezone = 'America/New_York'
        settings.save()

        new_count = AuditLog.objects.filter(
            action=AuditLog.Action.ORG_SETTINGS_UPDATED,
            object_type='OrganizationSettings',
            object_id=str(settings.pk),
        ).count()
        assert new_count == initial_count + 1


class TestUntrackedModelDoesNotAudit:
    """Verify that saving an untracked model does NOT create an AuditLog entry."""

    def test_saving_preferences_does_not_create_audit_log(self):
        """
        UserPreferences is not in the tracked models list
        (connect_audit_signals only tracks User, Infrastructure,
        Organization, OrganizationSettings). Saving it should not
        produce any audit log entries with object_type='UserPreferences'.
        """
        initial_count = AuditLog.objects.filter(
            object_type='UserPreferences'
        ).count()

        prefs = UserPreferencesFactory()
        prefs.dashboard = {'layout': 'compact'}
        prefs.save()

        final_count = AuditLog.objects.filter(
            object_type='UserPreferences'
        ).count()
        assert final_count == initial_count, (
            'UserPreferences is not tracked -- no audit log should be created'
        )


class TestAuditLogChangesExcludesSensitive:
    """Verify that sensitive fields are excluded from the changes dict."""

    def test_password_not_in_changes(self):
        """The password field should never appear in audit log changes."""
        user = UserFactory(username='audit_pw_user')
        log = AuditLog.objects.filter(
            action=AuditLog.Action.USER_CREATED,
            object_id=str(user.pk),
        ).first()
        assert log is not None
        assert 'password' not in log.changes, (
            'Password should be excluded from audit log changes'
        )
