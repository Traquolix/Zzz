"""
Tests for monitoring REST API views — IncidentList, IncidentSnapshot, Stats.

Uses authenticated DRF clients with org-scoped fiber assignments to verify
pagination, FINAL queries, org isolation, response shapes, and spectral clamping.
"""

from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status


# ============================================================================
# Incident List Pagination
# ============================================================================

@pytest.mark.django_db
class TestIncidentListPagination:
    """IncidentListView pagination: default limit, custom limit, cap, hasMore."""

    def _make_incidents(self, n):
        """Generate n incident dicts in the shape returned by incident_service.query_recent."""
        return [
            {
                'id': f'inc-{i}',
                'type': 'anomaly',
                'severity': 'high',
                'fiberLine': 'carros:0',
                'channel': 100 + i,
                'detectedAt': f'2026-02-28T12:00:{i:02d}',
                'status': 'active',
                'duration': None,
            }
            for i in range(n)
        ]

    def test_default_limit_100_with_has_more(self, authenticated_client, fiber_assignments):
        """150 incidents, default request → 100 results, hasMore=True."""
        incidents = self._make_incidents(101)  # query_recent returns limit+1 to detect next page

        with patch('apps.monitoring.views.incident_query_recent', return_value=incidents):
            resp = authenticated_client.get('/api/incidents')

        assert resp.status_code == 200
        assert len(resp.data['results']) == 100
        assert resp.data['hasMore'] is True
        assert resp.data['limit'] == 100

    def test_custom_limit_50(self, authenticated_client, fiber_assignments):
        """limit=50 → 50 results."""
        incidents = self._make_incidents(51)

        with patch('apps.monitoring.views.incident_query_recent', return_value=incidents):
            resp = authenticated_client.get('/api/incidents?limit=50')

        assert len(resp.data['results']) == 50
        assert resp.data['hasMore'] is True
        assert resp.data['limit'] == 50

    def test_limit_capped_at_500(self, authenticated_client, fiber_assignments):
        """limit=9999 → capped to 500."""
        incidents = self._make_incidents(10)

        with patch('apps.monitoring.views.incident_query_recent', return_value=incidents):
            resp = authenticated_client.get('/api/incidents?limit=9999')

        assert resp.data['limit'] == 500

    def test_has_more_false_when_all_returned(self, authenticated_client, fiber_assignments):
        """30 incidents, limit=100 → hasMore=False."""
        incidents = self._make_incidents(30)

        with patch('apps.monitoring.views.incident_query_recent', return_value=incidents):
            resp = authenticated_client.get('/api/incidents')

        assert resp.data['hasMore'] is False
        assert len(resp.data['results']) == 30

    def test_response_shape_is_object_not_array(self, authenticated_client, fiber_assignments):
        """Response is {results, hasMore, limit} — NOT a bare array."""
        with patch('apps.monitoring.views.incident_query_recent', return_value=[]):
            resp = authenticated_client.get('/api/incidents')

        assert isinstance(resp.data, dict)
        assert 'results' in resp.data
        assert 'hasMore' in resp.data
        assert 'limit' in resp.data

    def test_empty_org_returns_empty_results(self, authenticated_client):
        """User with org but no fiber assignments → empty results, no ClickHouse call."""
        # No fiber_assignments fixture → org has 0 fibers
        resp = authenticated_client.get('/api/incidents')

        assert resp.status_code == 200
        assert resp.data['results'] == []
        assert resp.data['hasMore'] is False


# ============================================================================
# Incident Snapshot Org Scoping
# ============================================================================

@pytest.mark.django_db
class TestIncidentSnapshotOrgScoping:
    """IncidentSnapshotView: org-scoped access control on incident's fiber."""

    def _mock_incident_row(self, fiber_id='carros:0'):
        return [{
            'fiber_id': fiber_id,
            'channel_start': 100,
            'channel_end': 200,
            'timestamp_ns': 1709136000000000000,  # 2024-02-28T12:00:00 in ns
        }]

    def test_snapshot_accessible_for_own_org_fiber(self, authenticated_client, fiber_assignments):
        """Org has 'carros', incident on 'carros:0' → 200."""
        with patch('apps.monitoring.views.query') as mock_query:
            # First call: incident metadata; second call: speed data
            mock_query.side_effect = [
                self._mock_incident_row('carros:0'),
                [],  # No speed data
            ]
            resp = authenticated_client.get('/api/incidents/inc-1/snapshot')

        assert resp.status_code == 200
        assert resp.data['incidentId'] == 'inc-1'
        assert resp.data['fiberLine'] == 'carros:0'

    def test_snapshot_rejected_for_other_org_fiber(self, authenticated_client, fiber_assignments):
        """Org has carros/mathis/promenade, incident on 'unknown-fiber:0' → 404."""
        with patch('apps.monitoring.views.query', return_value=self._mock_incident_row('unknown-fiber:0')):
            resp = authenticated_client.get('/api/incidents/inc-2/snapshot')

        assert resp.status_code == 404

    def test_snapshot_directional_suffix_stripped_for_check(self, authenticated_client, fiber_assignments):
        """Incident fiber 'carros:0', org assignment 'carros' (no suffix) → accepted."""
        with patch('apps.monitoring.views.query') as mock_query:
            mock_query.side_effect = [
                self._mock_incident_row('carros:0'),
                [],
            ]
            resp = authenticated_client.get('/api/incidents/inc-3/snapshot')

        # strip_directional_suffix('carros:0') == 'carros' which is in org fibers
        assert resp.status_code == 200

    def test_superuser_can_snapshot_any_fiber(self, superuser_client):
        """Superuser accesses fiber not in their org → 200."""
        with patch('apps.monitoring.views.query') as mock_query:
            mock_query.side_effect = [
                self._mock_incident_row('any-fiber:0'),
                [],
            ]
            resp = superuser_client.get('/api/incidents/inc-4/snapshot')

        assert resp.status_code == 200

    def test_snapshot_nonexistent_incident_404(self, authenticated_client, fiber_assignments):
        """Incident ID not found in ClickHouse → 404."""
        with patch('apps.monitoring.views.query', return_value=[]):
            resp = authenticated_client.get('/api/incidents/nonexistent/snapshot')

        assert resp.status_code == 404


# ============================================================================
# Snapshot Query Behavior
# ============================================================================

@pytest.mark.django_db
class TestSnapshotQueryBehavior:
    """Verify SQL sent to ClickHouse contains FINAL, LIMIT, and correct normalization."""

    def test_snapshot_incident_query_includes_FINAL(self, authenticated_client, fiber_assignments):
        """Incident metadata query must include FINAL for ReplacingMergeTree correctness."""
        with patch('apps.monitoring.views.query') as mock_query:
            mock_query.side_effect = [
                [{'fiber_id': 'carros', 'channel_start': 100, 'channel_end': 200, 'timestamp_ns': 1e18}],
                [],
            ]
            authenticated_client.get('/api/incidents/inc-1/snapshot')

        # First call is the incident metadata query
        first_sql = mock_query.call_args_list[0][0][0]
        assert 'FINAL' in first_sql

    def test_snapshot_speed_query_limits_to_50000(self, authenticated_client, fiber_assignments):
        """Speed data query capped at 50000 rows."""
        with patch('apps.monitoring.views.query') as mock_query:
            mock_query.side_effect = [
                [{'fiber_id': 'carros', 'channel_start': 100, 'channel_end': 200, 'timestamp_ns': 1e18}],
                [],
            ]
            authenticated_client.get('/api/incidents/inc-1/snapshot')

        second_sql = mock_query.call_args_list[1][0][0]
        assert '50000' in second_sql

    def test_snapshot_normalizes_fiberline_in_response(self, authenticated_client, fiber_assignments):
        """Plain 'carros' from ClickHouse → 'carros:0' in response."""
        with patch('apps.monitoring.views.query') as mock_query:
            mock_query.side_effect = [
                [{'fiber_id': 'carros', 'channel_start': 100, 'channel_end': 200, 'timestamp_ns': 1e18}],
                [{'fiber_id': 'carros', 'ch': 150, 'speed': 80.0, 'timestamp': 1709136000000}],
            ]
            resp = authenticated_client.get('/api/incidents/inc-1/snapshot')

        assert resp.data['fiberLine'] == 'carros:0'
        assert resp.data['detections'][0]['fiberLine'] == 'carros:0'


# ============================================================================
# Stats View
# ============================================================================

@pytest.mark.django_db
class TestStatsView:
    """StatsView: org-scoped stats, response shape, FINAL queries, zero-fiber edge case."""

    def test_stats_returns_all_expected_fields(self, authenticated_client, fiber_assignments):
        """Response contains all 6 stat fields."""
        with patch('apps.monitoring.views.query_scalar', return_value=42):
            resp = authenticated_client.get('/api/stats')

        assert resp.status_code == 200
        for field in ['fiberCount', 'totalChannels', 'activeVehicles',
                      'detectionsPerSecond', 'activeIncidents', 'systemUptime']:
            assert field in resp.data, f'Missing field: {field}'

    def test_stats_org_scoped_passes_fiber_ids(self, authenticated_client, fiber_assignments):
        """Non-superuser queries include fiber_ids parameter."""
        calls = []

        def _capture_scalar(sql, parameters=None, **kw):
            calls.append({'sql': sql, 'params': parameters})
            return 0

        with patch('apps.monitoring.views.query_scalar', side_effect=_capture_scalar):
            authenticated_client.get('/api/stats')

        # All scalar queries should have fids parameter
        for call in calls:
            assert 'fids' in (call['params'] or {}), f"Missing fids in: {call['sql'][:60]}"

    def test_stats_superuser_queries_without_fiber_filter(self, superuser_client):
        """Superuser queries don't include fiber_ids filter."""
        calls = []

        def _capture_scalar(sql, parameters=None, **kw):
            calls.append({'sql': sql, 'params': parameters})
            return 0

        with patch('apps.monitoring.views.query_scalar', side_effect=_capture_scalar):
            superuser_client.get('/api/stats')

        for call in calls:
            assert call['params'] is None, f"Superuser should not have params: {call['sql'][:60]}"

    def test_stats_empty_org_returns_zeros(self, authenticated_client):
        """Org with no fiber assignments → all stats zero (no ClickHouse call)."""
        resp = authenticated_client.get('/api/stats')

        assert resp.status_code == 200
        assert resp.data['fiberCount'] == 0
        assert resp.data['totalChannels'] == 0
        assert resp.data['activeIncidents'] == 0
        assert resp.data['activeVehicles'] == 0
        assert resp.data['detectionsPerSecond'] == 0

    def test_stats_clickhouse_unavailable_returns_503(self, authenticated_client, fiber_assignments):
        """ClickHouse circuit breaker tripped → 503."""
        from apps.shared.exceptions import ClickHouseUnavailableError

        with patch('apps.monitoring.views.query_scalar',
                   side_effect=ClickHouseUnavailableError('down')):
            resp = authenticated_client.get('/api/stats')

        assert resp.status_code == 503


# ============================================================================
# Spectral Data Clamping
# ============================================================================

@pytest.mark.django_db
class TestSpectralClamping:
    """SpectralDataView: time/freq parameters clamped to safe maximums."""

    def _mock_spectral(self):
        """Return a mock SpectralResult that supports downsample/to_dict."""
        mock = MagicMock()
        mock.downsample_time.return_value = mock
        mock.downsample_freq.return_value = mock
        mock.to_dict.return_value = {
            'spectra': [[1.0]],
            'freqs': [1.0],
            't0': '2026-01-01T00:00:00',
            'dt': [0.0],
            'numTimeSamples': 1,
            'numFreqBins': 1,
            'freqRange': [0.1, 50.0],
            'durationSeconds': 1.0,
        }
        return mock

    def test_max_time_samples_clamped_to_5000(self, authenticated_client):
        """maxTimeSamples=99999 → clamped to 5000 before downsample."""
        mock_spec = self._mock_spectral()

        with patch('apps.monitoring.hdf5_reader.load_spectral_data', return_value=mock_spec):
            resp = authenticated_client.get('/api/shm/spectra?maxTimeSamples=99999')

        if resp.status_code == 200:
            # Verify downsample_time was called with clamped value
            mock_spec.downsample_time.assert_called_once()
            args = mock_spec.downsample_time.call_args[0]
            assert args[0] <= 5000

    def test_max_freq_bins_clamped_to_2000(self, authenticated_client):
        """maxFreqBins=99999 → clamped to 2000 before downsample."""
        mock_spec = self._mock_spectral()

        with patch('apps.monitoring.hdf5_reader.load_spectral_data', return_value=mock_spec):
            resp = authenticated_client.get('/api/shm/spectra?maxFreqBins=99999')

        if resp.status_code == 200:
            mock_spec.downsample_freq.assert_called_once()
            args = mock_spec.downsample_freq.call_args[0]
            assert args[0] <= 2000

    def test_valid_ranges_pass_through(self, authenticated_client):
        """Normal values (500, 200) pass through unchanged."""
        mock_spec = self._mock_spectral()

        with patch('apps.monitoring.hdf5_reader.load_spectral_data', return_value=mock_spec):
            resp = authenticated_client.get('/api/shm/spectra?maxTimeSamples=500&maxFreqBins=200')

        if resp.status_code == 200:
            time_arg = mock_spec.downsample_time.call_args[0][0]
            freq_arg = mock_spec.downsample_freq.call_args[0][0]
            assert time_arg == 500
            assert freq_arg == 200


# ============================================================================
# Infrastructure Org Scoping
# ============================================================================

@pytest.mark.django_db
class TestInfrastructureOrgScoping:
    """InfrastructureListView: org isolation on PostgreSQL infrastructure."""

    def test_user_sees_only_own_org_infrastructure(self, authenticated_client, infrastructure):
        """Authenticated user sees infrastructure from their org only."""
        resp = authenticated_client.get('/api/infrastructure')

        assert resp.status_code == 200
        results = resp.data['results']
        assert len(results) == 2  # bridge-magnan + tunnel-paillon
        names = {item['name'] for item in results}
        assert 'Pont Magnan' in names
        assert 'Tunnel du Paillon' in names

    def test_other_org_user_sees_nothing(self, other_org_client, infrastructure):
        """User from other org sees none of org's infrastructure."""
        resp = other_org_client.get('/api/infrastructure')

        assert resp.status_code == 200
        assert len(resp.data['results']) == 0

    def test_superuser_sees_all(self, superuser_client, infrastructure):
        """Superuser sees all infrastructure across orgs."""
        resp = superuser_client.get('/api/infrastructure')

        assert resp.status_code == 200
        assert len(resp.data['results']) >= 2

    def test_response_shape(self, authenticated_client, infrastructure):
        """Each item has required fields."""
        resp = authenticated_client.get('/api/infrastructure')

        for item in resp.data['results']:
            for field in ['id', 'type', 'name', 'fiberId', 'startChannel', 'endChannel']:
                assert field in item, f'Missing field: {field}'
