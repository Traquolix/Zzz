"""
Pytest fixtures for SequoIA backend tests.
"""

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from tests.factories import (
    OrganizationFactory,
    UserFactory,
    FiberAssignmentFactory,
    InfrastructureFactory,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear Django cache before each test to avoid stale data."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def org():
    """Create an organization."""
    return OrganizationFactory()


@pytest.fixture
def other_org():
    """Create another organization for tenant isolation tests."""
    return OrganizationFactory(name='Other Organization')


@pytest.fixture
def admin_user(org):
    """Create an admin user with all permissions."""
    return UserFactory(
        organization=org,
        username='admin_test',
        role='admin',
    )


@pytest.fixture
def viewer_user(org):
    """Create a viewer user with limited permissions."""
    return UserFactory(
        organization=org,
        username='viewer_test',
        role='viewer',
    )


@pytest.fixture
def other_org_user(other_org):
    """Create a user in a different organization."""
    return UserFactory(
        organization=other_org,
        username='other_org_user',
    )


@pytest.fixture
def infrastructure(org):
    """Create infrastructure items in the organization."""
    return [
        InfrastructureFactory(
            organization=org,
            id='bridge-magnan',
            type='bridge',
            name='Pont Magnan',
            fiber_id='fiber-promenade',
            start_channel=50,
            end_channel=60,
        ),
        InfrastructureFactory(
            organization=org,
            id='tunnel-paillon',
            type='tunnel',
            name='Tunnel du Paillon',
            fiber_id='fiber-promenade',
            start_channel=120,
            end_channel=180,
        ),
    ]


@pytest.fixture
def fiber_assignments(org):
    """Assign fibers to the org for tenant-scoped tests."""
    return [
        FiberAssignmentFactory(organization=org, fiber_id='carros'),
        FiberAssignmentFactory(organization=org, fiber_id='mathis'),
        FiberAssignmentFactory(organization=org, fiber_id='promenade'),
    ]


@pytest.fixture
def other_org_fiber_assignments(other_org):
    """Assign a single fiber to the other org."""
    return [
        FiberAssignmentFactory(organization=other_org, fiber_id='carros'),
    ]


@pytest.fixture
def api_client():
    """Create an unauthenticated DRF API client."""
    return APIClient()


@pytest.fixture
def authenticated_client(api_client, admin_user):
    """Create an API client authenticated as admin."""
    api_client.force_authenticate(user=admin_user)
    return api_client


@pytest.fixture
def viewer_client(api_client, viewer_user):
    """Create an API client authenticated as viewer."""
    api_client.force_authenticate(user=viewer_user)
    return api_client


@pytest.fixture
def other_org_client(other_org_user):
    """Create an API client authenticated as a user from another org."""
    client = APIClient()
    client.force_authenticate(user=other_org_user)
    return client
