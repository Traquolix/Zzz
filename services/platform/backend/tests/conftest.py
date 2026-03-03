"""
Pytest fixtures for SequoIA backend tests.
"""

from unittest.mock import MagicMock, patch

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


@pytest.fixture(autouse=True)
def _reset_circuit_breaker():
    """Reset ClickHouse circuit breaker state between tests.

    Module-level globals (_consecutive_failures, _last_failure_time) and
    thread-local client cache must be pristine for each test.
    """
    import apps.shared.clickhouse as ch
    ch._consecutive_failures = 0
    ch._last_failure_time = 0.0
    ch._local.__dict__.clear()
    yield
    ch._consecutive_failures = 0
    ch._last_failure_time = 0.0
    ch._local.__dict__.clear()


@pytest.fixture(autouse=True)
def _reset_prometheus_metrics():
    """Reset Prometheus metric counters between tests.

    Without this, metrics leak across tests causing assertion failures.
    """
    try:
        from apps.shared import metrics as m
        from prometheus_client import REGISTRY

        for collector_name in list(REGISTRY._names_to_collectors.keys()):
            if collector_name.startswith('sequoia_'):
                try:
                    collector = REGISTRY._names_to_collectors[collector_name]
                    if hasattr(collector, '_metrics'):
                        collector._metrics.clear()
                except Exception:
                    pass
    except ImportError:
        pass
    yield


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


@pytest.fixture
def superuser(org):
    """Superuser with is_superuser=True for cross-org access tests."""
    return UserFactory(
        organization=org,
        username='superuser_test',
        is_superuser=True,
    )


@pytest.fixture
def superuser_client(superuser):
    """API client authenticated as superuser."""
    client = APIClient()
    client.force_authenticate(user=superuser)
    return client


@pytest.fixture
def mock_clickhouse_query():
    """Configurable ClickHouse mock.

    Returns a function set_results(rows, column_names) that configures
    what the next query() call will return.

    Usage:
        mock_ch = mock_clickhouse_query()
        mock_ch.set_results([{'id': '1', 'status': 'active'}])
        result = query("SELECT ...")  # returns configured rows
        assert mock_ch.last_sql contains expected SQL
    """
    class _MockCH:
        def __init__(self):
            self._results = []
            self._column_names = []
            self.last_sql = None
            self.last_params = None
            self.call_count = 0
            self._side_effects = []

        def set_results(self, rows, column_names=None):
            """Set rows as list of dicts. column_names inferred if not given."""
            self._results = rows
            if column_names:
                self._column_names = column_names
            elif rows:
                self._column_names = list(rows[0].keys())
            else:
                self._column_names = []

        def set_side_effects(self, effects):
            """Set a list of (rows, column_names) tuples for sequential calls."""
            self._side_effects = list(effects)

        def _make_mock_result(self, rows, column_names):
            result = MagicMock()
            result.column_names = column_names
            result.result_rows = [
                tuple(row.get(c) for c in column_names) for row in rows
            ]
            return result

    mock_ch = _MockCH()

    def _query_side_effect(sql, parameters=None, **kwargs):
        mock_ch.last_sql = sql
        mock_ch.last_params = parameters
        mock_ch.call_count += 1

        if mock_ch._side_effects:
            rows, cols = mock_ch._side_effects.pop(0)
            return mock_ch._make_mock_result(rows, cols or list(rows[0].keys()) if rows else [])
        return mock_ch._make_mock_result(mock_ch._results, mock_ch._column_names)

    mock_client = MagicMock()
    mock_client.query.side_effect = _query_side_effect

    with patch('apps.shared.clickhouse.get_client', return_value=mock_client):
        yield mock_ch


# ============================================================================
# Embedded ClickHouse (chdb) — real SQL engine for integration tests
# ============================================================================

@pytest.fixture(scope='session')
def _clickhouse_engine():
    """Session-scoped embedded ClickHouse engine.

    Creates the schema once per test session. Individual tests truncate
    and re-seed as needed via the ``clickhouse`` fixture.
    """
    from tests.clickhouse_embedded import EmbeddedClickHouse
    engine = EmbeddedClickHouse()
    engine.setup()
    yield engine
    engine.teardown()


@pytest.fixture
def clickhouse(_clickhouse_engine):
    """Per-test embedded ClickHouse with clean data.

    Patches ``apps.shared.clickhouse.get_client`` to return the chdb
    adapter client so all app-level query()/query_scalar() calls execute
    real SQL against the embedded engine.

    Usage in tests:
        def test_something(self, clickhouse, authenticated_client, fiber_assignments):
            clickhouse.seed_incidents([...])
            response = authenticated_client.get('/api/incidents/')
            assert response.status_code == 200
    """
    _clickhouse_engine.truncate_all()
    client = _clickhouse_engine.get_client()

    with patch('apps.shared.clickhouse.get_client', return_value=client):
        yield _clickhouse_engine
