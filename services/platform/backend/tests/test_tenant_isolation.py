"""
Tests for multi-tenant isolation.

Verifies that users in one organization cannot see data from another,
and that FiberAssignment correctly scopes data access across REST
endpoints, ClickHouse queries, and WebSocket channels.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache as django_cache
from rest_framework import status

from apps.fibers.models import FiberAssignment
from apps.fibers.utils import get_fiber_org_map, get_org_fiber_ids
from tests.factories import (
    InfrastructureFactory,
    OrganizationFactory,
    OrganizationSettingsFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db(transaction=True)


# ---------------------------------------------------------------------------
# Model + utility tests
# ---------------------------------------------------------------------------


class TestFiberAssignment:
    """Tests for the FiberAssignment model and utilities."""

    def test_create_fiber_assignment(self, org):
        fa = FiberAssignment.objects.create(
            organization=org,
            fiber_id="test-fiber",
        )
        assert fa.fiber_id == "test-fiber"
        assert fa.organization == org
        assert fa.assigned_at is not None

    def test_unique_together_constraint(self, org):
        FiberAssignment.objects.create(organization=org, fiber_id="fiber-a")
        with pytest.raises(Exception):
            FiberAssignment.objects.create(organization=org, fiber_id="fiber-a")

    def test_fiber_shared_across_orgs(self, org, other_org):
        FiberAssignment.objects.create(organization=org, fiber_id="shared-fiber")
        FiberAssignment.objects.create(organization=other_org, fiber_id="shared-fiber")
        assert FiberAssignment.objects.filter(fiber_id="shared-fiber").count() == 2

    def test_get_org_fiber_ids(self, org, fiber_assignments):
        ids = get_org_fiber_ids(org)
        assert set(ids) == {"carros", "mathis", "promenade"}

    def test_get_org_fiber_ids_empty(self, other_org):
        ids = get_org_fiber_ids(other_org)
        assert ids == []

    def test_get_fiber_org_map(
        self, org, other_org, fiber_assignments, other_org_fiber_assignments
    ):
        mapping = get_fiber_org_map()
        assert str(org.pk) in mapping["carros"]
        assert str(other_org.pk) in mapping["carros"]
        assert str(org.pk) in mapping["mathis"]
        assert str(other_org.pk) not in mapping.get("mathis", [])

    def test_cascade_delete_on_org_removal(self, org):
        FiberAssignment.objects.create(organization=org, fiber_id="doomed")
        assert FiberAssignment.objects.filter(organization=org).count() == 1
        org.delete()
        assert FiberAssignment.objects.filter(fiber_id="doomed").count() == 0


# ---------------------------------------------------------------------------
# Widget / layer inheritance chain
# ---------------------------------------------------------------------------


class TestUserWidgetInheritance:
    """Tests for the User.save() widget/layer inheritance chain."""

    def test_admin_gets_all_by_default(self):
        org = OrganizationFactory()
        user = UserFactory(organization=org, role="admin", allowed_widgets=[], allowed_layers=[])
        from apps.shared.constants import ALL_LAYERS, ALL_WIDGETS

        assert user.allowed_widgets == list(ALL_WIDGETS)
        assert user.allowed_layers == list(ALL_LAYERS)

    def test_viewer_gets_viewer_defaults(self):
        org = OrganizationFactory()
        user = UserFactory(organization=org, role="viewer", allowed_widgets=[], allowed_layers=[])
        from apps.shared.constants import VIEWER_LAYERS, VIEWER_WIDGETS

        assert user.allowed_widgets == list(VIEWER_WIDGETS)
        assert user.allowed_layers == list(VIEWER_LAYERS)

    def test_explicit_user_widgets_preserved(self):
        org = OrganizationFactory()
        user = UserFactory(
            organization=org,
            role="viewer",
            allowed_widgets=["map"],
            allowed_layers=["fibers"],
        )
        assert user.allowed_widgets == ["map"]
        assert user.allowed_layers == ["fibers"]

    def test_inherits_from_org_settings(self):
        org = OrganizationFactory()
        OrganizationSettingsFactory(
            organization=org,
            allowed_widgets=["map", "traffic_monitor"],
            allowed_layers=["fibers", "vehicles"],
        )
        user = UserFactory(organization=org, role="viewer", allowed_widgets=[], allowed_layers=[])
        assert user.allowed_widgets == ["map", "traffic_monitor"]
        assert user.allowed_layers == ["fibers", "vehicles"]

    def test_org_settings_empty_falls_through_to_role(self):
        org = OrganizationFactory()
        OrganizationSettingsFactory(
            organization=org,
            allowed_widgets=[],
            allowed_layers=[],
        )
        user = UserFactory(organization=org, role="admin", allowed_widgets=[], allowed_layers=[])
        from apps.shared.constants import ALL_LAYERS, ALL_WIDGETS

        assert user.allowed_widgets == list(ALL_WIDGETS)
        assert user.allowed_layers == list(ALL_LAYERS)


# ---------------------------------------------------------------------------
# PostgreSQL endpoint isolation (Infrastructure, Preferences)
# ---------------------------------------------------------------------------


class TestPostgresIsolation:
    """Cross-org isolation for PostgreSQL-backed endpoints."""

    def test_infrastructure_isolation(self, authenticated_client, other_org_client, org, other_org):
        InfrastructureFactory(organization=org, id="org-a-1", name="Org A Bridge")
        InfrastructureFactory(organization=other_org, id="org-b-1", name="Org B Tunnel")

        resp_a = authenticated_client.get("/api/infrastructure")
        names_a = [i["name"] for i in resp_a.json()["results"]]
        assert "Org A Bridge" in names_a
        assert "Org B Tunnel" not in names_a

        resp_b = other_org_client.get("/api/infrastructure")
        names_b = [i["name"] for i in resp_b.json()["results"]]
        assert "Org B Tunnel" in names_b
        assert "Org A Bridge" not in names_b

    def test_preferences_isolation(
        self, authenticated_client, other_org_client, admin_user, other_org_user
    ):
        authenticated_client.put(
            "/api/user/preferences",
            {"dashboard": {"org_a": True}},
            format="json",
        )

        response = other_org_client.get("/api/user/preferences")
        assert response.json()["dashboard"] == {}

        response = authenticated_client.get("/api/user/preferences")
        assert response.json()["dashboard"] == {"org_a": True}


# ---------------------------------------------------------------------------
# Auth responses include org identity
# ---------------------------------------------------------------------------


class TestAuthOrgInfo:
    """Verify auth endpoints return correct organization identity."""

    def test_verify_returns_org_info(self, authenticated_client, admin_user, org):
        resp = authenticated_client.get("/api/auth/verify")
        data = resp.json()
        assert data["organizationId"] == str(org.pk)
        assert data["organizationName"] == org.name

    def test_verify_returns_different_org_per_user(
        self, authenticated_client, other_org_client, org, other_org
    ):
        resp_a = authenticated_client.get("/api/auth/verify")
        resp_b = other_org_client.get("/api/auth/verify")
        assert resp_a.json()["organizationId"] == str(org.pk)
        assert resp_b.json()["organizationId"] == str(other_org.pk)
        assert resp_a.json()["organizationId"] != resp_b.json()["organizationId"]

    def test_login_returns_org_info(self, api_client, admin_user, org):
        response = api_client.post(
            "/api/auth/login",
            {
                "username": admin_user.username,
                "password": "testpass123",
            },
        )
        data = response.json()
        assert data["organizationId"] == str(org.pk)
        assert data["organizationName"] == org.name


# ---------------------------------------------------------------------------
# Cross-org ClickHouse endpoint isolation
# ---------------------------------------------------------------------------


class TestFiberEndpointIsolation:
    """Cross-org isolation for GET /api/fibers (ClickHouse)."""

    @patch("apps.fibers.views.get_client")
    def test_org_a_only_sees_own_fibers(self, mock_get_client, authenticated_client, org):
        """Verify the query is parameterized with org A's fiber IDs only."""
        FiberAssignment.objects.create(organization=org, fiber_id="carros")

        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.named_results.return_value = []
        mock_client.query.return_value = mock_result
        mock_get_client.return_value = mock_client

        authenticated_client.get("/api/fibers")

        # Verify ClickHouse was called with the correct fiber_ids
        mock_client.query.assert_called_once()
        _, kwargs = mock_client.query.call_args
        assert kwargs["parameters"]["fids"] == ["carros"]

    @patch("apps.fibers.views.get_client")
    def test_org_b_only_sees_own_fibers(self, mock_get_client, other_org_client, other_org):
        """Verify org B's query only includes org B's fibers."""
        FiberAssignment.objects.create(organization=other_org, fiber_id="promenade")

        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.named_results.return_value = []
        mock_client.query.return_value = mock_result
        mock_get_client.return_value = mock_client

        other_org_client.get("/api/fibers")

        mock_client.query.assert_called_once()
        _, kwargs = mock_client.query.call_args
        assert kwargs["parameters"]["fids"] == ["promenade"]

    @patch("apps.fibers.views.get_client")
    def test_no_assignments_skips_clickhouse_entirely(self, mock_get_client, authenticated_client):
        """If org has no fiber assignments, ClickHouse should never be called."""
        response = authenticated_client.get("/api/fibers")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["results"] == []
        assert response.json()["hasMore"] is False
        mock_get_client.assert_not_called()

    @patch("apps.fibers.views.get_client")
    def test_shared_fiber_visible_to_both_orgs(
        self, mock_get_client, authenticated_client, other_org_client, org, other_org
    ):
        """A fiber assigned to both orgs should appear in both queries."""
        FiberAssignment.objects.create(organization=org, fiber_id="shared")
        FiberAssignment.objects.create(organization=other_org, fiber_id="shared")
        FiberAssignment.objects.create(organization=org, fiber_id="org-a-only")

        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.named_results.return_value = []
        mock_client.query.return_value = mock_result
        mock_get_client.return_value = mock_client

        authenticated_client.get("/api/fibers")
        _, kwargs_a = mock_client.query.call_args
        fids_a = set(kwargs_a["parameters"]["fids"])
        assert fids_a == {"shared", "org-a-only"}

        mock_client.query.reset_mock()
        django_cache.clear()

        other_org_client.get("/api/fibers")
        _, kwargs_b = mock_client.query.call_args
        fids_b = set(kwargs_b["parameters"]["fids"])
        assert fids_b == {"shared"}
        assert "org-a-only" not in fids_b


class TestIncidentEndpointIsolation:
    """Cross-org isolation for incident endpoints (ClickHouse)."""

    @patch("apps.monitoring.incident_service.query")
    def test_incident_list_parameterized_with_org_fibers(
        self, mock_query, authenticated_client, org
    ):
        """Verify the incident query includes a fiber_id IN clause."""
        FiberAssignment.objects.create(organization=org, fiber_id="carros")
        FiberAssignment.objects.create(organization=org, fiber_id="mathis")
        mock_query.return_value = []

        authenticated_client.get("/api/incidents")

        mock_query.assert_called_once()
        sql = mock_query.call_args[0][0]
        assert "fiber_id IN {fids:Array(String)}" in sql
        params = (
            mock_query.call_args[1].get("parameters") or mock_query.call_args[0][1]
            if len(mock_query.call_args[0]) > 1
            else mock_query.call_args[1]["parameters"]
        )
        assert set(params["fids"]) == {"carros", "mathis"}

    @patch("apps.monitoring.incident_service.query")
    def test_incident_list_different_orgs_get_different_fibers(
        self, mock_query, authenticated_client, other_org_client, org, other_org
    ):
        """Two orgs with different fibers get different parameterized queries."""
        FiberAssignment.objects.create(organization=org, fiber_id="carros")
        FiberAssignment.objects.create(organization=other_org, fiber_id="promenade")
        mock_query.return_value = []

        authenticated_client.get("/api/incidents")
        call_a = mock_query.call_args
        params_a = call_a[1].get("parameters", {})
        assert params_a["fids"] == ["carros"]

        mock_query.reset_mock()
        django_cache.clear()

        other_org_client.get("/api/incidents")
        call_b = mock_query.call_args
        params_b = call_b[1].get("parameters", {})
        assert params_b["fids"] == ["promenade"]

    @patch("apps.monitoring.incident_service.query")
    def test_incident_list_no_assignments_returns_empty(self, mock_query, authenticated_client):
        """Org with no fibers gets empty result, ClickHouse is not queried."""
        response = authenticated_client.get("/api/incidents")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["results"] == []
        assert data["hasMore"] is False
        mock_query.assert_not_called()

    @patch("apps.monitoring.views.query")
    def test_snapshot_cross_org_rejected(self, mock_query, other_org_client, other_org):
        """
        Accessing a snapshot for an incident on a fiber NOT assigned to the
        requesting org should return 404.
        """
        # Other org only has promenade, but the incident is on carros
        FiberAssignment.objects.create(organization=other_org, fiber_id="promenade")
        mock_query.return_value = [
            {
                "fiber_id": "carros",
                "channel_start": 100,
                "channel_end": 110,
                "timestamp_ns": 1717200000000000000,
            }
        ]

        response = other_org_client.get("/api/incidents/inc-cross-org/snapshot")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch("apps.monitoring.views.query")
    def test_snapshot_same_org_allowed(self, mock_query, authenticated_client, org):
        """
        Accessing a snapshot for an incident on a fiber assigned to the
        requesting org should succeed.
        """
        FiberAssignment.objects.create(organization=org, fiber_id="carros")
        mock_query.side_effect = [
            # Incident lookup
            [
                {
                    "fiber_id": "carros",
                    "channel_start": 100,
                    "channel_end": 110,
                    "timestamp_ns": 1717200000000000000,
                }
            ],
            # Speed hires data
            [],
        ]

        response = authenticated_client.get("/api/incidents/inc-own-org/snapshot")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["incidentId"] == "inc-own-org"
        assert data["fiberLine"] == "carros:0"  # Normalized with directional suffix


class TestStatsEndpointIsolation:
    """Cross-org isolation for GET /api/stats (ClickHouse)."""

    @patch("apps.monitoring.views.query_scalar")
    def test_stats_parameterized_with_org_fibers(self, mock_scalar, authenticated_client, org):
        """Verify all 5 stats queries use the org's fiber IDs."""
        FiberAssignment.objects.create(organization=org, fiber_id="carros")
        mock_scalar.return_value = 0

        authenticated_client.get("/api/stats")

        # 5 ClickHouse scalars should be called
        assert mock_scalar.call_count == 5
        for c in mock_scalar.call_args_list:
            sql = c[0][0]
            assert "fiber_id IN {fids:Array(String)}" in sql
            params = c[1].get("parameters", {})
            assert params["fids"] == ["carros"]

    @patch("apps.monitoring.views.query_scalar")
    def test_stats_different_orgs_get_different_fibers(
        self, mock_scalar, authenticated_client, other_org_client, org, other_org
    ):
        """Two orgs with different fibers get different parameterized queries."""
        FiberAssignment.objects.create(organization=org, fiber_id="carros")
        FiberAssignment.objects.create(organization=org, fiber_id="mathis")
        FiberAssignment.objects.create(organization=other_org, fiber_id="promenade")
        mock_scalar.return_value = 0

        authenticated_client.get("/api/stats")
        for c in mock_scalar.call_args_list:
            params = c[1].get("parameters", {})
            assert set(params["fids"]) == {"carros", "mathis"}

        mock_scalar.reset_mock()
        django_cache.clear()

        other_org_client.get("/api/stats")
        for c in mock_scalar.call_args_list:
            params = c[1].get("parameters", {})
            assert params["fids"] == ["promenade"]

    @patch("apps.monitoring.views.query_scalar")
    def test_stats_no_assignments_returns_zeros_without_querying(
        self, mock_scalar, authenticated_client
    ):
        """Org with no fibers gets zeros, ClickHouse not queried."""
        response = authenticated_client.get("/api/stats")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["fiberCount"] == 0
        assert data["totalChannels"] == 0
        assert data["activeIncidents"] == 0
        assert data["detectionsPerSecond"] == 0.0
        assert data["activeVehicles"] == 0
        mock_scalar.assert_not_called()


# ---------------------------------------------------------------------------
# Superuser bypass — no fiber_id filter applied
# ---------------------------------------------------------------------------


class TestSuperuserBypass:
    """Superusers should see all data regardless of org fiber assignments."""

    @pytest.fixture
    def superuser_client(self, api_client, org):
        user = UserFactory(
            organization=org,
            username="superadmin",
            is_superuser=True,
            is_staff=True,
        )
        api_client.force_authenticate(user=user)
        return api_client

    @patch("apps.fibers.views.get_client")
    def test_superuser_fibers_no_filter(self, mock_get_client, superuser_client):
        """Superuser fiber query should have no WHERE fiber_id IN clause."""
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.named_results.return_value = []
        mock_client.query.return_value = mock_result
        mock_get_client.return_value = mock_client

        superuser_client.get("/api/fibers")

        mock_client.query.assert_called_once()
        sql = mock_client.query.call_args[0][0]
        assert "IN {fids:Array(String)}" not in sql

    @patch("apps.monitoring.incident_service.query")
    def test_superuser_incidents_no_filter(self, mock_query, superuser_client):
        """Superuser incident query should have no fiber_id IN clause."""
        mock_query.return_value = []

        superuser_client.get("/api/incidents")

        mock_query.assert_called_once()
        sql = mock_query.call_args[0][0]
        assert "IN {fids:Array(String)}" not in sql

    @patch("apps.monitoring.views.query_scalar")
    def test_superuser_stats_no_filter(self, mock_scalar, superuser_client):
        """Superuser stats queries should have no fiber_id IN clauses."""
        mock_scalar.return_value = 0

        superuser_client.get("/api/stats")

        assert mock_scalar.call_count == 5
        for c in mock_scalar.call_args_list:
            sql = c[0][0]
            assert "IN {fids:Array(String)}" not in sql

    @patch("apps.monitoring.views.query")
    def test_superuser_snapshot_any_fiber(self, mock_query, superuser_client):
        """Superuser can view snapshot for any incident regardless of fiber."""
        mock_query.side_effect = [
            [
                {
                    "fiber_id": "unassigned-fiber",
                    "channel_start": 50,
                    "channel_end": 60,
                    "timestamp_ns": 1717200000000000000,
                }
            ],
            [],  # speed data
        ]
        response = superuser_client.get("/api/incidents/inc-any/snapshot")
        assert response.status_code == status.HTTP_200_OK


# ---------------------------------------------------------------------------
# Cache isolation — cached data must not leak between orgs
# ---------------------------------------------------------------------------


class TestCacheIsolation:
    """Cached responses must be org-scoped."""

    @patch("apps.monitoring.incident_service.query")
    def test_incident_cache_per_org(
        self, mock_query, authenticated_client, other_org_client, org, other_org
    ):
        """
        Org A's cached incident list must not be served to org B.
        """
        FiberAssignment.objects.create(organization=org, fiber_id="carros")
        FiberAssignment.objects.create(organization=other_org, fiber_id="promenade")

        # Org A: incidents returns one incident on carros
        mock_query.return_value = [
            {
                "incident_id": "inc-a",
                "incident_type": "accident",
                "severity": "high",
                "fiber_id": "carros",
                "channel_start": 100,
                "timestamp": datetime(2025, 6, 1, 12, 0, 0),
                "status": "active",
                "duration_seconds": None,
            }
        ]
        resp_a = authenticated_client.get("/api/incidents")
        data_a = resp_a.json()
        assert len(data_a["results"]) == 1
        assert data_a["results"][0]["fiberLine"] == "carros:0"  # Directional suffix

        # Org B: even with the cache warm for org A, B should query separately
        mock_query.return_value = [
            {
                "incident_id": "inc-b",
                "incident_type": "congestion",
                "severity": "low",
                "fiber_id": "promenade",
                "channel_start": 50,
                "timestamp": datetime(2025, 6, 1, 13, 0, 0),
                "status": "active",
                "duration_seconds": None,
            }
        ]
        resp_b = other_org_client.get("/api/incidents")
        data_b = resp_b.json()
        assert len(data_b["results"]) == 1
        assert data_b["results"][0]["fiberLine"] == "promenade:0"  # Directional suffix

    @patch("apps.fibers.views.get_client")
    def test_fiber_cache_per_org(
        self, mock_get_client, authenticated_client, other_org_client, org, other_org
    ):
        """
        Org A's cached fiber list must not be served to org B.
        """
        FiberAssignment.objects.create(organization=org, fiber_id="carros")
        FiberAssignment.objects.create(organization=other_org, fiber_id="promenade")

        mock_client = MagicMock()

        # First call: org A sees carros
        mock_result_a = MagicMock()
        mock_result_a.named_results.return_value = [
            {
                "fiber_id": "carros",
                "fiber_name": "Carros",
                "color": "#ff0000",
                "channel_coordinates": [(7.1, 43.7)],
                "landmark_labels": [None],
            }
        ]
        # Second call: org B sees promenade
        mock_result_b = MagicMock()
        mock_result_b.named_results.return_value = [
            {
                "fiber_id": "promenade",
                "fiber_name": "Promenade",
                "color": "#00ff00",
                "channel_coordinates": [(7.25, 43.69)],
                "landmark_labels": [None],
            }
        ]
        mock_client.query.side_effect = [mock_result_a, mock_result_b]
        mock_get_client.return_value = mock_client

        resp_a = authenticated_client.get("/api/fibers")
        results_a = resp_a.json()["results"]
        # 1 physical cable × 2 directions = 2 directional fibers
        assert len(results_a) == 2
        assert results_a[0]["id"] == "carros:0"
        assert results_a[0]["parentFiberId"] == "carros"
        assert results_a[1]["id"] == "carros:1"

        resp_b = other_org_client.get("/api/fibers")
        results_b = resp_b.json()["results"]
        assert len(results_b) == 2
        assert results_b[0]["id"] == "promenade:0"
        assert results_b[0]["parentFiberId"] == "promenade"
        assert results_b[1]["id"] == "promenade:1"

    @patch("apps.monitoring.views.query_scalar")
    def test_stats_cache_per_org(
        self, mock_scalar, authenticated_client, other_org_client, org, other_org
    ):
        """
        Org A's cached stats must not be served to org B.
        """
        FiberAssignment.objects.create(organization=org, fiber_id="carros")
        FiberAssignment.objects.create(organization=other_org, fiber_id="promenade")

        # Org A: fiber_count=3
        mock_scalar.side_effect = [3, 2500, 5, 42.5, 17]
        resp_a = authenticated_client.get("/api/stats")
        assert resp_a.json()["fiberCount"] == 3

        # Org B: fiber_count=1 (different stats)
        mock_scalar.side_effect = [1, 500, 0, 10.0, 3]
        resp_b = other_org_client.get("/api/stats")
        assert resp_b.json()["fiberCount"] == 1
        assert resp_b.json()["fiberCount"] != resp_a.json()["fiberCount"]


# ---------------------------------------------------------------------------
# WebSocket org-scoped group isolation
# ---------------------------------------------------------------------------


class TestWebSocketIsolation:
    """WebSocket consumers must join org-scoped groups.

    Authentication uses message-based JWT: connect first, then send
    {"action": "authenticate", "token": "<jwt>"}.
    """

    @pytest.mark.asyncio
    async def test_broadcast_to_wrong_org_not_received(self):
        """
        A broadcast sent to org B's group should NOT be received by
        a consumer connected as an org A user.
        """
        from channels.layers import get_channel_layer
        from channels.routing import URLRouter
        from channels.testing import WebsocketCommunicator
        from django.urls import path
        from rest_framework_simplejwt.tokens import AccessToken

        from apps.realtime.consumers import RealtimeConsumer

        org_a = await _create_org_async("Org A")
        org_b = await _create_org_async("Org B")
        user_a = await _create_user_async(org_a, "ws_user_a")

        application = URLRouter([path("ws/", RealtimeConsumer.as_asgi())])
        communicator = WebsocketCommunicator(application, "/ws/")
        connected, _ = await communicator.connect()
        assert connected

        # Authenticate via message-based JWT
        token = await sync_to_async(lambda: str(AccessToken.for_user(user_a)))()
        await communicator.send_json_to({"action": "authenticate", "token": token})
        auth_resp = await communicator.receive_json_from(timeout=2)
        assert auth_resp["success"] is True

        # Subscribe to detections
        await communicator.send_json_to(
            {
                "action": "subscribe",
                "channel": "detections",
            }
        )
        await communicator.receive_nothing(timeout=0.2)

        # Send broadcast to org B's group
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f"realtime_detections_org_{org_b.pk}",
            {
                "type": "broadcast.message",
                "channel": "detections",
                "data": [{"speed": 999}],
            },
        )

        # User A should NOT receive it
        nothing = await communicator.receive_nothing(timeout=1)
        assert nothing is True

        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_broadcast_to_own_org_received(self):
        """
        A broadcast sent to org A's group SHOULD be received by
        a consumer connected as an org A user.
        """
        from channels.layers import get_channel_layer
        from channels.routing import URLRouter
        from channels.testing import WebsocketCommunicator
        from django.urls import path
        from rest_framework_simplejwt.tokens import AccessToken

        from apps.realtime.consumers import RealtimeConsumer

        org_a = await _create_org_async("Org Rx")
        user_a = await _create_user_async(org_a, "ws_user_rx")

        application = URLRouter([path("ws/", RealtimeConsumer.as_asgi())])
        communicator = WebsocketCommunicator(application, "/ws/")
        connected, _ = await communicator.connect()
        assert connected

        # Authenticate via message-based JWT
        token = await sync_to_async(lambda: str(AccessToken.for_user(user_a)))()
        await communicator.send_json_to({"action": "authenticate", "token": token})
        auth_resp = await communicator.receive_json_from(timeout=2)
        assert auth_resp["success"] is True

        await communicator.send_json_to(
            {
                "action": "subscribe",
                "channel": "detections",
            }
        )
        await communicator.receive_nothing(timeout=0.2)

        channel_layer = get_channel_layer()
        org_id = str(org_a.pk)
        await channel_layer.group_send(
            f"realtime_detections_org_{org_id}",
            {
                "type": "broadcast.message",
                "channel": "detections",
                "data": [{"speed": 42}],
            },
        )

        response = await communicator.receive_json_from(timeout=2)
        assert response["channel"] == "detections"
        assert response["data"] == [{"speed": 42}]

        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_superuser_receives_all_group(self):
        """
        Superusers join the __all__ group and receive broadcasts to it.
        """
        from channels.layers import get_channel_layer
        from channels.routing import URLRouter
        from channels.testing import WebsocketCommunicator
        from django.urls import path
        from rest_framework_simplejwt.tokens import AccessToken

        from apps.realtime.consumers import RealtimeConsumer

        org = await _create_org_async("Org SU")
        su = await _create_user_async(org, "ws_super", is_superuser=True, is_staff=True)

        application = URLRouter([path("ws/", RealtimeConsumer.as_asgi())])
        communicator = WebsocketCommunicator(application, "/ws/")
        connected, _ = await communicator.connect()
        assert connected

        # Authenticate via message-based JWT
        token = await sync_to_async(lambda: str(AccessToken.for_user(su)))()
        await communicator.send_json_to({"action": "authenticate", "token": token})
        auth_resp = await communicator.receive_json_from(timeout=2)
        assert auth_resp["success"] is True

        await communicator.send_json_to(
            {
                "action": "subscribe",
                "channel": "counts",
            }
        )
        await communicator.receive_nothing(timeout=0.2)

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            "realtime_counts_org___all__",
            {
                "type": "broadcast.message",
                "channel": "counts",
                "data": [{"count": 77}],
            },
        )

        response = await communicator.receive_json_from(timeout=2)
        assert response["channel"] == "counts"
        assert response["data"] == [{"count": 77}]

        await communicator.disconnect()


# ---------------------------------------------------------------------------
# Async helpers for WebSocket tests (create ORM objects from async context)
# ---------------------------------------------------------------------------

from asgiref.sync import sync_to_async  # noqa: E402


@sync_to_async
def _create_org_async(name):
    return OrganizationFactory(name=name)


@sync_to_async
def _create_user_async(org, username, **kwargs):
    return UserFactory(organization=org, username=username, **kwargs)
