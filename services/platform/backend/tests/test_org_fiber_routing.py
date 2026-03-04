"""
Tests for org-scoped fiber routing, directional ID normalization, and incident polling.

Verifies the full data path: ClickHouse fiber_id → directional normalization →
fiber_org_map lookup → org-scoped Channels group broadcast → incident lifecycle.
"""

import asyncio
from collections import defaultdict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.monitoring.incident_service import (
    _ensure_directional_fiber_id,
    strip_directional_suffix,
    transform_row,
)


# ============================================================================
# Directional Fiber ID Normalization
# ============================================================================

class TestEnsureDirectionalFiberId:
    """_ensure_directional_fiber_id: plain → directional, already-directional → no-op."""

    def test_plain_id_gets_colon_0(self):
        """Plain fiber ID receives default direction :0."""
        assert _ensure_directional_fiber_id('carros') == 'carros:0'

    def test_idempotent_on_colon_0(self):
        """Already-directional :0 is unchanged."""
        assert _ensure_directional_fiber_id('carros:0') == 'carros:0'

    def test_preserves_colon_1(self):
        """Direction :1 is preserved, not overwritten to :0."""
        assert _ensure_directional_fiber_id('carros:1') == 'carros:1'

    def test_empty_string_gets_colon_0(self):
        """Edge case: empty string still gets suffix (guard, not crash)."""
        assert _ensure_directional_fiber_id('') == ':0'

    def test_multiple_colons_left_alone(self):
        """Fiber ID with embedded colons (e.g. 'a:b:0') is not double-suffixed."""
        result = _ensure_directional_fiber_id('a:b:0')
        assert result == 'a:b:0'


class TestStripDirectionalSuffix:
    """strip_directional_suffix: directional → plain parent fiber ID."""

    def test_strips_colon_0(self):
        assert strip_directional_suffix('carros:0') == 'carros'

    def test_strips_colon_1(self):
        assert strip_directional_suffix('carros:1') == 'carros'

    def test_idempotent_on_plain(self):
        assert strip_directional_suffix('carros') == 'carros'

    def test_empty_string_returns_empty(self):
        assert strip_directional_suffix('') == ''

    def test_multiple_colons_strips_last(self):
        """'a:b:0' → 'a:b' (rsplit on last colon only)."""
        assert strip_directional_suffix('a:b:0') == 'a:b'


class TestRoundtripNormalization:
    """Ensure→strip and strip→ensure compose correctly."""

    def test_ensure_then_strip(self):
        """strip(ensure('carros')) == 'carros'."""
        assert strip_directional_suffix(_ensure_directional_fiber_id('carros')) == 'carros'

    def test_strip_then_ensure(self):
        """ensure(strip('carros:0')) == 'carros:0'."""
        assert _ensure_directional_fiber_id(strip_directional_suffix('carros:0')) == 'carros:0'

    def test_strip_then_ensure_direction_1(self):
        """ensure(strip('carros:1')) == 'carros:0' — direction info lost (expected)."""
        result = _ensure_directional_fiber_id(strip_directional_suffix('carros:1'))
        assert result == 'carros:0'  # :1 is not recoverable through strip→ensure


class TestTransformRow:
    """transform_row produces frontend-compatible shape with directional fiberLine."""

    def test_plain_fiber_id_becomes_directional(self):
        """ClickHouse row with plain fiber_id → fiberLine with :0 suffix."""
        row = {
            'incident_id': 'inc-1',
            'incident_type': 'anomaly',
            'severity': 'high',
            'fiber_id': 'carros',
            'channel_start': 150,
            'timestamp': '2026-02-28T12:00:00',
            'status': 'active',
            'duration_seconds': None,
        }
        result = transform_row(row)
        assert result['fiberLine'] == 'carros:0'
        assert result['id'] == 'inc-1'
        assert result['type'] == 'anomaly'
        assert result['severity'] == 'high'
        assert result['channel'] == 150

    def test_directional_fiber_id_preserved(self):
        """ClickHouse row with directional fiber_id → fiberLine unchanged."""
        row = {
            'incident_id': 'inc-2',
            'incident_type': 'speed',
            'severity': 'medium',
            'fiber_id': 'mathis:1',
            'channel_start': 200,
            'timestamp': '2026-02-28T12:00:00',
            'status': 'active',
            'duration_seconds': 120,
        }
        result = transform_row(row)
        assert result['fiberLine'] == 'mathis:1'


# ============================================================================
# Org-Scoped Broadcast Routing
# ============================================================================

class _FakeChannelLayer:
    """Minimal channel layer mock that records group_send calls."""

    def __init__(self):
        self.sent: dict[str, list] = defaultdict(list)

    async def group_send(self, group, message):
        self.sent[group].append(message)


class TestOrgBroadcastDict:
    """_org_broadcast with a single dict item (e.g. one incident)."""

    @pytest.fixture
    def channel_layer(self):
        return _FakeChannelLayer()

    @pytest.fixture
    def fiber_org_map(self):
        return {
            'carros': ['org-1'],
            'mathis': ['org-1', 'org-2'],
        }

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_directional_fiberline_routes_to_correct_org(self, channel_layer, fiber_org_map):
        """fiberLine='carros:0', org-1 owns 'carros' → org-1 group receives."""
        from apps.realtime.kafka_bridge import _org_broadcast

        data = {'fiberLine': 'carros:0', 'id': 'inc-1', 'type': 'anomaly'}
        self._run(_org_broadcast(channel_layer, 'incidents', data, fiber_org_map))

        # org-1 receives
        org1_key = 'realtime_incidents_org_org-1'
        assert len(channel_layer.sent[org1_key]) == 1
        assert channel_layer.sent[org1_key][0]['data']['id'] == 'inc-1'

        # org-2 does NOT receive (doesn't own 'carros')
        org2_key = 'realtime_incidents_org_org-2'
        assert len(channel_layer.sent[org2_key]) == 0

    def test_superuser_all_group_always_receives(self, channel_layer, fiber_org_map):
        """__all__ group receives every broadcast regardless of fiber ownership."""
        from apps.realtime.kafka_bridge import _org_broadcast

        data = {'fiberLine': 'carros:0', 'id': 'inc-1'}
        self._run(_org_broadcast(channel_layer, 'incidents', data, fiber_org_map))

        all_key = 'realtime_incidents_org___all__'
        assert len(channel_layer.sent[all_key]) == 1

    def test_shared_fiber_routes_to_both_orgs(self, channel_layer, fiber_org_map):
        """'mathis' is shared between org-1 and org-2 — both receive."""
        from apps.realtime.kafka_bridge import _org_broadcast

        data = {'fiberLine': 'mathis:0', 'id': 'inc-2'}
        self._run(_org_broadcast(channel_layer, 'incidents', data, fiber_org_map))

        assert len(channel_layer.sent['realtime_incidents_org_org-1']) == 1
        assert len(channel_layer.sent['realtime_incidents_org_org-2']) == 1

    def test_unknown_fiber_routes_only_to_all(self, channel_layer, fiber_org_map):
        """Fiber not in org map → only __all__ group receives (no crash)."""
        from apps.realtime.kafka_bridge import _org_broadcast

        data = {'fiberLine': 'unknown:0', 'id': 'inc-3'}
        self._run(_org_broadcast(channel_layer, 'incidents', data, fiber_org_map))

        # __all__ always gets it
        assert len(channel_layer.sent['realtime_incidents_org___all__']) == 1
        # No org-specific groups
        assert len(channel_layer.sent['realtime_incidents_org_org-1']) == 0
        assert len(channel_layer.sent['realtime_incidents_org_org-2']) == 0

    def test_empty_fiberline_handled_gracefully(self, channel_layer, fiber_org_map):
        """Empty fiberLine doesn't crash — routes to __all__ only."""
        from apps.realtime.kafka_bridge import _org_broadcast

        data = {'fiberLine': '', 'id': 'inc-4'}
        self._run(_org_broadcast(channel_layer, 'incidents', data, fiber_org_map))

        assert len(channel_layer.sent['realtime_incidents_org___all__']) == 1


class TestOrgBroadcastList:
    """_org_broadcast with a list of items (e.g. detection batch)."""

    @pytest.fixture
    def channel_layer(self):
        return _FakeChannelLayer()

    @pytest.fixture
    def fiber_org_map(self):
        return {
            'carros': ['org-1'],
            'mathis': ['org-2'],
        }

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_list_items_grouped_by_org(self, channel_layer, fiber_org_map):
        """Mixed-fiber list: org-1 gets carros items, org-2 gets mathis items."""
        from apps.realtime.kafka_bridge import _org_broadcast

        data = [
            {'fiberLine': 'carros:0', 'speed': 80},
            {'fiberLine': 'carros:0', 'speed': 90},
            {'fiberLine': 'mathis:0', 'speed': 60},
        ]
        self._run(_org_broadcast(channel_layer, 'detections', data, fiber_org_map))

        org1_msgs = channel_layer.sent['realtime_detections_org_org-1']
        assert len(org1_msgs) == 1
        assert len(org1_msgs[0]['data']) == 2  # 2 carros items

        org2_msgs = channel_layer.sent['realtime_detections_org_org-2']
        assert len(org2_msgs) == 1
        assert len(org2_msgs[0]['data']) == 1  # 1 mathis item

    def test_list_all_group_gets_full_data(self, channel_layer, fiber_org_map):
        """__all__ group receives the complete unfiltered list."""
        from apps.realtime.kafka_bridge import _org_broadcast

        data = [
            {'fiberLine': 'carros:0', 'speed': 80},
            {'fiberLine': 'mathis:0', 'speed': 60},
        ]
        self._run(_org_broadcast(channel_layer, 'detections', data, fiber_org_map))

        all_msgs = channel_layer.sent['realtime_detections_org___all__']
        assert len(all_msgs) == 1
        assert len(all_msgs[0]['data']) == 2  # full list


# ============================================================================
# Incident Polling Lifecycle
# ============================================================================

class TestPollIncidents:
    """_poll_incidents: new detection, steady state, and resolution broadcasts."""

    @pytest.fixture(autouse=True)
    def _mock_alerting(self):
        """Prevent alerting DB queries (SQLite can't handle async concurrent access)."""
        with patch('apps.realtime.kafka_bridge.check_alerts_for_incident', new_callable=AsyncMock):
            yield

    @pytest.fixture
    def channel_layer(self):
        return _FakeChannelLayer()

    @pytest.fixture
    def fiber_org_map(self):
        return {'carros': ['org-1'], 'mathis': ['org-2']}

    def _make_raw_row(self, incident_id, fiber_id='carros', status='active'):
        return {
            'incident_id': incident_id,
            'incident_type': 'anomaly',
            'severity': 'high',
            'fiber_id': fiber_id,
            'channel_start': 100,
            'timestamp': '2026-02-28T12:00:00',
            'status': status,
            'duration_seconds': None,
        }

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_new_incident_broadcast_to_correct_org(self, channel_layer, fiber_org_map):
        """New incident on 'carros' → org-1 receives, org-2 doesn't."""
        from apps.realtime.kafka_bridge import _poll_incidents

        rows = [self._make_raw_row('inc-new', fiber_id='carros')]
        known = {}

        with patch('apps.monitoring.incident_service.query_active_raw', return_value=rows):
            self._run(_poll_incidents(channel_layer, known, fiber_org_map))

        org1_msgs = channel_layer.sent['realtime_incidents_org_org-1']
        assert len(org1_msgs) == 1
        assert org1_msgs[0]['data']['id'] == 'inc-new'

        assert len(channel_layer.sent['realtime_incidents_org_org-2']) == 0

    def test_known_incident_not_rebroadcast(self, channel_layer, fiber_org_map):
        """Incident already in known set → no new broadcast."""
        from apps.realtime.kafka_bridge import _poll_incidents

        rows = [self._make_raw_row('inc-existing', fiber_id='carros')]
        known = {'inc-existing': 'carros:0'}  # Already tracked

        with patch('apps.monitoring.incident_service.query_active_raw', return_value=rows):
            self._run(_poll_incidents(channel_layer, known, fiber_org_map))

        # Only __all__ from the _org_broadcast of new incidents — but since
        # this incident is already known, it should NOT be broadcast
        org1_msgs = channel_layer.sent.get('realtime_incidents_org_org-1', [])
        assert len(org1_msgs) == 0

    def test_resolved_incident_broadcast_to_correct_org(self, channel_layer, fiber_org_map):
        """Incident disappears from active list → resolved broadcast to owning org."""
        from apps.realtime.kafka_bridge import _poll_incidents

        # Previously known incident, now absent from active query
        known = {'inc-resolved': 'carros:0'}
        rows = []  # Empty: incident is no longer active

        with patch('apps.monitoring.incident_service.query_active_raw', return_value=rows):
            self._run(_poll_incidents(channel_layer, known, fiber_org_map))

        org1_msgs = channel_layer.sent['realtime_incidents_org_org-1']
        assert len(org1_msgs) == 1
        assert org1_msgs[0]['data']['status'] == 'resolved'
        assert org1_msgs[0]['data']['id'] == 'inc-resolved'
        assert org1_msgs[0]['data']['fiberLine'] == 'carros:0'

    def test_resolved_incident_not_sent_to_wrong_org(self, channel_layer, fiber_org_map):
        """Incident on carros (org-1) resolves → org-2 must NOT receive."""
        from apps.realtime.kafka_bridge import _poll_incidents

        known = {'inc-resolved': 'carros:0'}
        rows = []

        with patch('apps.monitoring.incident_service.query_active_raw', return_value=rows):
            self._run(_poll_incidents(channel_layer, known, fiber_org_map))

        assert len(channel_layer.sent.get('realtime_incidents_org_org-2', [])) == 0

    def test_known_incidents_updated_after_poll(self, channel_layer, fiber_org_map):
        """After poll, known_incidents reflects current active set exactly."""
        from apps.realtime.kafka_bridge import _poll_incidents

        rows = [
            self._make_raw_row('inc-a', fiber_id='carros'),
            self._make_raw_row('inc-b', fiber_id='mathis'),
        ]
        known = {'inc-old': 'carros:0'}  # Will be resolved

        with patch('apps.monitoring.incident_service.query_active_raw', return_value=rows):
            self._run(_poll_incidents(channel_layer, known, fiber_org_map))

        assert 'inc-a' in known
        assert 'inc-b' in known
        assert 'inc-old' not in known

    def test_clickhouse_unavailable_does_not_crash(self, channel_layer, fiber_org_map):
        """ClickHouse circuit breaker tripped → polling skips silently."""
        from apps.realtime.kafka_bridge import _poll_incidents
        from apps.shared.exceptions import ClickHouseUnavailableError

        known = {'inc-1': 'carros:0'}

        with patch('apps.monitoring.incident_service.query_active_raw',
                    side_effect=ClickHouseUnavailableError('circuit breaker')):
            self._run(_poll_incidents(channel_layer, known, fiber_org_map))

        # known_incidents unchanged (poll was skipped)
        assert 'inc-1' in known
        # No broadcasts
        assert len(channel_layer.sent) == 0


# ============================================================================
# Fiber Org Map (DB → cache)
# ============================================================================

@pytest.mark.django_db
class TestFiberOrgMap:
    """get_fiber_org_map: builds correct mapping from FiberAssignment rows."""

    def test_single_org_single_fiber(self, org, fiber_assignments):
        """Basic mapping: org has 3 fibers, each maps back to org."""
        from apps.fibers.utils import get_fiber_org_map

        fom = get_fiber_org_map()
        org_id = str(org.pk)

        assert org_id in fom.get('carros', [])
        assert org_id in fom.get('mathis', [])
        assert org_id in fom.get('promenade', [])

    def test_shared_fiber_maps_to_multiple_orgs(self, org, other_org, fiber_assignments, other_org_fiber_assignments):
        """'carros' assigned to both org and other_org → both in list."""
        from apps.fibers.utils import get_fiber_org_map

        # Clear cache to ensure fresh load
        from django.core.cache import cache
        cache.delete('fiber_org_map')

        fom = get_fiber_org_map()
        carros_orgs = fom.get('carros', [])

        assert str(org.pk) in carros_orgs
        assert str(other_org.pk) in carros_orgs

    def test_no_assignments_returns_empty_map(self):
        """No FiberAssignment rows → empty dict."""
        from apps.fibers.utils import get_fiber_org_map
        from django.core.cache import cache
        cache.delete('fiber_org_map')

        fom = get_fiber_org_map()
        assert fom == {}

    def test_map_cached_after_first_call(self, org, fiber_assignments):
        """Second call returns cached result (no DB hit)."""
        from apps.fibers.utils import get_fiber_org_map
        from django.core.cache import cache
        cache.delete('fiber_org_map')

        first = get_fiber_org_map()
        assert first  # Should have data

        # Verify second call returns cached result by checking the cache directly
        second = get_fiber_org_map()
        assert first == second

        # Verify the cache key exists
        assert cache.get('fiber_org_map') is not None
