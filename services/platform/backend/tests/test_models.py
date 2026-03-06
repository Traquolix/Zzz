"""
Tests for Django models.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.accounts.models import User
from apps.organizations.models import OrganizationSettings
from apps.preferences.models import UserPreferences
from apps.shared.constants import ALL_LAYERS, ALL_WIDGETS, VIEWER_LAYERS, VIEWER_WIDGETS
from tests.factories import InfrastructureFactory, OrganizationFactory, UserFactory

pytestmark = pytest.mark.django_db


class TestOrganization:
    def test_create_organization(self):
        org = OrganizationFactory(name="Test Corp")
        assert org.name == "Test Corp"
        assert org.slug == "test-corp"
        assert org.is_active is True

    def test_auto_slug_generation(self):
        org = OrganizationFactory(name="SequoIA Nice")
        assert org.slug == "sequoia-nice"

    def test_slug_uniqueness(self):
        OrganizationFactory(name="Duplicate")
        org2 = OrganizationFactory(name="Duplicate")
        assert org2.slug == "duplicate-1"

    def test_organization_str(self):
        org = OrganizationFactory(name="My Org")
        assert str(org) == "My Org"


class TestOrganizationSettings:
    def test_create_settings(self):
        org = OrganizationFactory()
        settings = OrganizationSettings.objects.create(organization=org)
        assert settings.timezone == "Europe/Paris"
        assert settings.speed_alert_threshold == 20.0
        assert settings.incident_auto_resolve_minutes == 30
        assert settings.shm_enabled is True


class TestUser:
    def test_create_admin_user(self):
        org = OrganizationFactory()
        user = UserFactory(organization=org, role="admin")
        assert user.role == "admin"
        assert user.allowed_widgets == list(ALL_WIDGETS)
        assert user.allowed_layers == list(ALL_LAYERS)

    def test_create_viewer_user(self):
        org = OrganizationFactory()
        user = UserFactory(organization=org, role="viewer")
        assert user.role == "viewer"
        assert user.allowed_widgets == list(VIEWER_WIDGETS)
        assert user.allowed_layers == list(VIEWER_LAYERS)

    def test_create_operator_user(self):
        org = OrganizationFactory()
        user = UserFactory(organization=org, role="operator")
        assert user.allowed_widgets == list(ALL_WIDGETS)
        assert user.allowed_layers == list(ALL_LAYERS)

    def test_custom_widgets_preserved(self):
        org = OrganizationFactory()
        user = UserFactory(
            organization=org,
            role="viewer",
            allowed_widgets=["map"],
            allowed_layers=["fibers"],
        )
        assert user.allowed_widgets == ["map"]
        assert user.allowed_layers == ["fibers"]

    def test_user_str(self):
        user = UserFactory(username="testuser")
        assert str(user) == "testuser"

    def test_non_superuser_requires_organization(self):
        user = User(username="noorg", is_superuser=False, organization=None)
        with pytest.raises(ValidationError) as exc_info:
            user.clean()
        assert "organization" in exc_info.value.message_dict

    def test_superuser_no_org_required(self):
        user = User(username="superadmin", is_superuser=True, organization=None)
        user.clean()  # Should not raise

    def test_password_is_hashed(self):
        user = UserFactory(password="mysecret")
        assert user.check_password("mysecret")
        assert not user.check_password("wrongpassword")


class TestInfrastructure:
    def test_create_infrastructure(self):
        org = OrganizationFactory()
        infra = InfrastructureFactory(
            organization=org,
            type="bridge",
            name="Pont Magnan",
            start_channel=50,
            end_channel=60,
        )
        assert infra.type == "bridge"
        assert infra.name == "Pont Magnan"
        assert infra.start_channel == 50
        assert infra.end_channel == 60

    def test_infrastructure_str(self):
        infra = InfrastructureFactory(name="Test Bridge", type="bridge")
        assert str(infra) == "Test Bridge (bridge)"


class TestUserPreferences:
    def test_create_empty_preferences(self):
        user = UserFactory()
        prefs = UserPreferences.objects.create(user=user)
        assert prefs.dashboard == {}
        assert prefs.map_config == {}

    def test_preferences_str(self):
        user = UserFactory(username="prefuser")
        prefs = UserPreferences.objects.create(user=user)
        assert "prefuser" in str(prefs)

    def test_preferences_json_storage(self):
        user = UserFactory()
        prefs = UserPreferences.objects.create(
            user=user,
            dashboard={"layouts": {"lg": [{"i": "map"}]}},
            map_config={"center": [7.26, 43.7], "zoom": 13},
        )
        prefs.refresh_from_db()
        assert prefs.dashboard["layouts"]["lg"][0]["i"] == "map"
        assert prefs.map_config["center"] == [7.26, 43.7]
