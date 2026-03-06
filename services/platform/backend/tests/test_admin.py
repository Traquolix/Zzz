"""
Tests for Django admin site.

Smoke tests ensuring all registered model admin pages load correctly
for a superuser. Covers changelist and add views for each registered model.
"""

import pytest
from django.contrib.admin.sites import site as admin_site
from django.test import Client
from django.urls import reverse

from tests.factories import (
    InfrastructureFactory,
    OrganizationFactory,
    UserFactory,
    UserPreferencesFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def superuser():
    """Create a Django superuser for admin access."""
    org = OrganizationFactory()
    user = UserFactory(
        organization=org,
        username="superadmin",
        is_staff=True,
        is_superuser=True,
    )
    return user


@pytest.fixture
def admin_client(superuser):
    """Return a Django test client logged in as superuser."""
    client = Client()
    client.force_login(superuser)
    return client


class TestAdminIndex:
    """Test the admin index page loads."""

    def test_admin_index_loads(self, admin_client):
        url = reverse("admin:index")
        response = admin_client.get(url)
        assert response.status_code == 200

    def test_admin_index_unauthenticated_redirects(self):
        client = Client()
        url = reverse("admin:index")
        response = client.get(url)
        # Should redirect to admin login
        assert response.status_code == 302


class TestAdminChangelists:
    """Test that changelist (list) pages load for all registered models."""

    def _changelist_url(self, model):
        """Build the admin changelist URL for a model."""
        meta = model._meta
        return reverse(f"admin:{meta.app_label}_{meta.model_name}_changelist")

    def test_all_registered_changelists_load(self, admin_client):
        """Every model registered with admin should have a working changelist."""
        for model, model_admin in admin_site._registry.items():
            url = self._changelist_url(model)
            response = admin_client.get(url)
            model_name = f"{model._meta.app_label}.{model._meta.model_name}"
            assert response.status_code == 200, (
                f"Changelist for {model_name} returned {response.status_code}"
            )

    def test_user_changelist(self, admin_client):
        url = reverse("admin:accounts_user_changelist")
        response = admin_client.get(url)
        assert response.status_code == 200

    def test_organization_changelist(self, admin_client):
        url = reverse("admin:organizations_organization_changelist")
        response = admin_client.get(url)
        assert response.status_code == 200

    def test_infrastructure_changelist(self, admin_client):
        url = reverse("admin:monitoring_infrastructure_changelist")
        response = admin_client.get(url)
        assert response.status_code == 200

    def test_auditlog_changelist(self, admin_client):
        url = reverse("admin:shared_auditlog_changelist")
        response = admin_client.get(url)
        assert response.status_code == 200

    def test_preferences_changelist(self, admin_client):
        url = reverse("admin:preferences_userpreferences_changelist")
        response = admin_client.get(url)
        assert response.status_code == 200


class TestAdminAddPages:
    """Test that add (create) pages load for models that support it."""

    def _add_url(self, model):
        """Build the admin add URL for a model."""
        meta = model._meta
        return reverse(f"admin:{meta.app_label}_{meta.model_name}_add")

    def test_all_add_pages_load_or_forbidden(self, admin_client):
        """
        Every registered model's add page should load (200) or return 403
        if the model admin disallows adding (e.g. AuditLog).
        """
        for model, model_admin in admin_site._registry.items():
            url = self._add_url(model)
            response = admin_client.get(url)
            model_name = f"{model._meta.app_label}.{model._meta.model_name}"
            assert response.status_code in (200, 403), (
                f"Add page for {model_name} returned {response.status_code}"
            )

    def test_user_add_page(self, admin_client):
        url = reverse("admin:accounts_user_add")
        response = admin_client.get(url)
        assert response.status_code == 200

    def test_organization_add_page(self, admin_client):
        url = reverse("admin:organizations_organization_add")
        response = admin_client.get(url)
        assert response.status_code == 200

    def test_infrastructure_add_page(self, admin_client):
        url = reverse("admin:monitoring_infrastructure_add")
        response = admin_client.get(url)
        assert response.status_code == 200

    def test_auditlog_add_page_forbidden(self, admin_client):
        """AuditLog has has_add_permission=False, so add page should be 403."""
        url = reverse("admin:shared_auditlog_add")
        response = admin_client.get(url)
        assert response.status_code == 403


class TestAdminChangePages:
    """Test that change (edit) pages load for existing objects."""

    def test_user_change_page(self, admin_client, superuser):
        url = reverse("admin:accounts_user_change", args=[superuser.pk])
        response = admin_client.get(url)
        assert response.status_code == 200

    def test_organization_change_page(self, admin_client):
        org = OrganizationFactory(name="Test Org for Change")
        url = reverse("admin:organizations_organization_change", args=[org.pk])
        response = admin_client.get(url)
        assert response.status_code == 200

    def test_infrastructure_change_page(self, admin_client):
        org = OrganizationFactory()
        infra = InfrastructureFactory(organization=org)
        url = reverse("admin:monitoring_infrastructure_change", args=[infra.pk])
        response = admin_client.get(url)
        assert response.status_code == 200

    def test_preferences_change_page(self, admin_client):
        prefs = UserPreferencesFactory()
        url = reverse("admin:preferences_userpreferences_change", args=[prefs.pk])
        response = admin_client.get(url)
        assert response.status_code == 200


class TestAdminNonStaffAccess:
    """Test that non-staff users cannot access admin."""

    def test_non_staff_user_redirected(self):
        org = OrganizationFactory()
        user = UserFactory(
            organization=org,
            username="regularuser",
            is_staff=False,
            is_superuser=False,
        )
        client = Client()
        client.force_login(user)
        url = reverse("admin:index")
        response = client.get(url)
        assert response.status_code == 302
