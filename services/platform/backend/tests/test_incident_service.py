"""
Tests for apps.monitoring.incident_service — centralized incident transforms and queries.

These tests are strict about behavioral correctness:
- transform_row normalizes fiber_id to include directional suffix
- transform_simulation_incident always produces directional fiberLine
- strip_directional_suffix extracts parent fiber ID
- _ensure_directional_fiber_id is idempotent
- query functions delegate to ClickHouse with correct SQL and parameters
- ClickHouseUnavailableError propagates (caller handles fallback)
"""

from datetime import datetime
from unittest.mock import patch

import pytest

from apps.monitoring.incident_service import (
    _ensure_directional_fiber_id,
    query_active,
    query_active_raw,
    query_recent,
    strip_directional_suffix,
    transform_row,
    transform_simulation_incident,
)
from apps.shared.exceptions import ClickHouseUnavailableError

# ============================================================================
# _ensure_directional_fiber_id
# ============================================================================


class TestEnsureDirectionalFiberId:
    """
    Contract: fiber_id without ':' gets ':0' appended.
    fiber_id already containing ':' passes through unchanged.
    Must be idempotent: applying twice yields the same result.
    """

    def test_plain_fiber_id_gets_default_direction(self):
        assert _ensure_directional_fiber_id("carros") == "carros:0"

    def test_directional_fiber_id_passes_through(self):
        assert _ensure_directional_fiber_id("carros:0") == "carros:0"

    def test_direction_1_passes_through(self):
        assert _ensure_directional_fiber_id("carros:1") == "carros:1"

    def test_idempotent_on_plain(self):
        once = _ensure_directional_fiber_id("mathis")
        twice = _ensure_directional_fiber_id(once)
        assert once == twice == "mathis:0"

    def test_idempotent_on_directional(self):
        once = _ensure_directional_fiber_id("mathis:1")
        twice = _ensure_directional_fiber_id(once)
        assert once == twice == "mathis:1"

    def test_empty_string_gets_suffix(self):
        assert _ensure_directional_fiber_id("") == ":0"

    def test_complex_fiber_id_with_hyphens(self):
        assert (
            _ensure_directional_fiber_id("fiber-promenade-des-anglais")
            == "fiber-promenade-des-anglais:0"
        )

    def test_already_complex_directional(self):
        assert _ensure_directional_fiber_id("fiber-promenade:0") == "fiber-promenade:0"


# ============================================================================
# strip_directional_suffix
# ============================================================================


class TestStripDirectionalSuffix:
    """
    Contract: removes everything after the last ':'.
    Plain IDs (no ':') pass through unchanged.
    Used by org routing where fiber_org_map keys are plain fiber IDs.
    """

    def test_strips_direction_0(self):
        assert strip_directional_suffix("carros:0") == "carros"

    def test_strips_direction_1(self):
        assert strip_directional_suffix("carros:1") == "carros"

    def test_plain_passes_through(self):
        assert strip_directional_suffix("carros") == "carros"

    def test_empty_string(self):
        assert strip_directional_suffix("") == ""

    def test_multiple_colons_strips_only_last(self):
        # Edge case: fiber ID with embedded colons (shouldn't happen in practice,
        # but the rsplit(':', 1) contract must hold)
        assert strip_directional_suffix("a:b:0") == "a:b"

    def test_roundtrip_with_ensure(self):
        """strip(ensure(x)) == x for plain IDs."""
        plain = "mathis"
        directional = _ensure_directional_fiber_id(plain)
        assert strip_directional_suffix(directional) == plain


# ============================================================================
# transform_row
# ============================================================================


class TestTransformRow:
    """
    Contract:
    - Produces exactly 8 keys: id, type, severity, fiberLine, channel, detectedAt, status, duration
    - fiberLine MUST have directional suffix (frontend FiberLine.id = "carros:0")
    - duration is converted from seconds to milliseconds, or None if absent/zero
    - timestamp handles both datetime objects and raw strings
    """

    def _make_row(self, **overrides):
        """Factory for a valid ClickHouse fiber_incidents row."""
        base = {
            "incident_id": "inc-001",
            "incident_type": "accident",
            "severity": "high",
            "fiber_id": "carros",
            "channel_start": 150,
            "timestamp": datetime(2025, 6, 1, 12, 0, 0),
            "status": "active",
            "duration_seconds": 300,
        }
        base.update(overrides)
        return base

    def test_output_shape_has_expected_keys(self):
        result = transform_row(self._make_row())
        expected_keys = {
            "id",
            "type",
            "severity",
            "fiberLine",
            "channel",
            "channelEnd",
            "detectedAt",
            "status",
            "duration",
            "speedBefore",
            "speedDuring",
            "speedDropPercent",
        }
        assert set(result.keys()) == expected_keys

    def test_fiber_id_without_suffix_gets_normalized(self):
        """
        Critical: ClickHouse may store 'carros' (plain).
        Frontend needs 'carros:0' for fibers.find(f => f.id === incident.fiberLine).
        """
        result = transform_row(self._make_row(fiber_id="carros"))
        assert result["fiberLine"] == "carros:0"

    def test_fiber_id_with_suffix_preserved(self):
        """Already-directional fiber_id should not be double-suffixed."""
        result = transform_row(self._make_row(fiber_id="carros:0"))
        assert result["fiberLine"] == "carros:0"

    def test_fiber_id_direction_1_preserved(self):
        result = transform_row(self._make_row(fiber_id="carros:1"))
        assert result["fiberLine"] == "carros:1"

    def test_duration_converted_to_ms(self):
        result = transform_row(self._make_row(duration_seconds=300))
        assert result["duration"] == 300_000

    def test_duration_none_when_absent(self):
        row = self._make_row()
        del row["duration_seconds"]
        result = transform_row(row)
        assert result["duration"] is None

    def test_duration_none_when_zero(self):
        """Zero duration should produce None (falsy check)."""
        result = transform_row(self._make_row(duration_seconds=0))
        assert result["duration"] is None

    def test_duration_none_when_explicit_none(self):
        result = transform_row(self._make_row(duration_seconds=None))
        assert result["duration"] is None

    def test_timestamp_datetime_object(self):
        dt = datetime(2025, 6, 1, 12, 0, 0)
        result = transform_row(self._make_row(timestamp=dt))
        assert result["detectedAt"] == "2025-06-01T12:00:00"

    def test_timestamp_string(self):
        """Some ClickHouse drivers return strings instead of datetime objects."""
        result = transform_row(self._make_row(timestamp="2025-06-01 12:00:00"))
        assert result["detectedAt"] == "2025-06-01 12:00:00"

    def test_field_mapping_is_correct(self):
        result = transform_row(
            self._make_row(
                incident_id="inc-XYZ",
                incident_type="congestion",
                severity="medium",
                fiber_id="mathis:0",
                channel_start=42,
                status="resolved",
            )
        )
        assert result["id"] == "inc-XYZ"
        assert result["type"] == "congestion"
        assert result["severity"] == "medium"
        assert result["fiberLine"] == "mathis:0"
        assert result["channel"] == 42
        assert result["status"] == "resolved"

    def test_fractional_duration(self):
        """Floating-point durations should convert correctly."""
        result = transform_row(self._make_row(duration_seconds=1.5))
        assert result["duration"] == 1500


# ============================================================================
# transform_simulation_incident
# ============================================================================


class TestTransformSimulationIncident:
    """
    Contract:
    - Accepts a simulation Incident dataclass (uses .fiber_line, not .fiber_id)
    - fiberLine is ALWAYS f'{fiber_line}:0' (simulation doesn't track direction)
    - duration passes through as-is (already in ms or None from simulation)
    """

    class _FakeIncident:
        """Minimal stand-in for simulation.Incident dataclass."""

        def __init__(self, **kwargs):
            defaults = {
                "id": "sim-001",
                "type": "slowdown",
                "severity": "low",
                "fiber_line": "carros",
                "channel": 75,
                "detected_at": "2025-06-01T12:00:00Z",
                "status": "active",
                "duration": 5000,
            }
            defaults.update(kwargs)
            for k, v in defaults.items():
                setattr(self, k, v)

    def test_output_shape(self):
        result = transform_simulation_incident(self._FakeIncident())
        expected_keys = {
            "id",
            "type",
            "severity",
            "fiberLine",
            "channel",
            "channelEnd",
            "detectedAt",
            "status",
            "duration",
            "speedBefore",
            "speedDuring",
            "speedDropPercent",
        }
        assert set(result.keys()) == expected_keys

    def test_fiber_line_gets_direction_suffix(self):
        result = transform_simulation_incident(self._FakeIncident(fiber_line="mathis"))
        assert result["fiberLine"] == "mathis:0"

    def test_duration_passes_through(self):
        result = transform_simulation_incident(self._FakeIncident(duration=12345))
        assert result["duration"] == 12345

    def test_duration_none(self):
        result = transform_simulation_incident(self._FakeIncident(duration=None))
        assert result["duration"] is None

    def test_detected_at_passes_through(self):
        result = transform_simulation_incident(
            self._FakeIncident(detected_at="2025-01-01T00:00:00Z")
        )
        assert result["detectedAt"] == "2025-01-01T00:00:00Z"


# ============================================================================
# query_active
# ============================================================================


class TestQueryActive:
    """
    Contract:
    - fiber_ids=None → uses _ACTIVE_SQL_ALL (superuser, no IN clause)
    - fiber_ids=[...] → uses _ACTIVE_SQL_SCOPED (org-scoped, IN clause)
    - Returns transformed rows (not raw)
    - ClickHouseUnavailableError propagates
    """

    @patch("apps.monitoring.incident_service.query")
    def test_scoped_query_passes_fiber_ids(self, mock_query):
        mock_query.return_value = []
        query_active(fiber_ids=["carros", "mathis"], limit=50)

        mock_query.assert_called_once()
        args, kwargs = mock_query.call_args
        sql = args[0]
        params = kwargs.get("parameters") or args[1] if len(args) > 1 else kwargs["parameters"]

        assert "fiber_id IN" in sql
        assert params["fids"] == ["carros", "mathis"]
        assert params["lim"] == 50

    @patch("apps.monitoring.incident_service.query")
    def test_unscoped_query_no_fiber_filter(self, mock_query):
        mock_query.return_value = []
        query_active(fiber_ids=None, limit=200)

        mock_query.assert_called_once()
        sql = mock_query.call_args[0][0]
        assert "fiber_id IN" not in sql

    @patch("apps.monitoring.incident_service.query")
    def test_returns_transformed_rows(self, mock_query):
        mock_query.return_value = [
            {
                "incident_id": "inc-001",
                "incident_type": "accident",
                "severity": "high",
                "fiber_id": "carros",
                "channel_start": 150,
                "timestamp": datetime(2025, 6, 1, 12, 0, 0),
                "status": "active",
                "duration_seconds": 300,
            }
        ]
        result = query_active(fiber_ids=["carros"])
        assert len(result) == 1
        assert result[0]["fiberLine"] == "carros:0"  # Normalized
        assert result[0]["duration"] == 300_000  # Converted to ms

    @patch("apps.monitoring.incident_service.query")
    def test_clickhouse_error_propagates(self, mock_query):
        mock_query.side_effect = ClickHouseUnavailableError("down")
        with pytest.raises(ClickHouseUnavailableError):
            query_active(fiber_ids=["carros"])


# ============================================================================
# query_recent
# ============================================================================


class TestQueryRecent:
    """
    Contract:
    - Same scoping logic as query_active
    - Additional 'hours' parameter in SQL
    - Default hours=24, limit=500
    """

    @patch("apps.monitoring.incident_service.query")
    def test_passes_hours_parameter(self, mock_query):
        mock_query.return_value = []
        query_recent(fiber_ids=["carros"], hours=12, limit=100)

        params = mock_query.call_args[1]["parameters"]
        assert params["hours"] == 12
        assert params["lim"] == 100

    @patch("apps.monitoring.incident_service.query")
    def test_default_parameters(self, mock_query):
        mock_query.return_value = []
        query_recent(fiber_ids=None)

        params = mock_query.call_args[1]["parameters"]
        assert params["hours"] == 24
        assert params["lim"] == 500

    @patch("apps.monitoring.incident_service.query")
    def test_unscoped_recent_no_fiber_filter(self, mock_query):
        mock_query.return_value = []
        query_recent(fiber_ids=None)

        sql = mock_query.call_args[0][0]
        assert "fiber_id IN" not in sql
        assert "INTERVAL" in sql


# ============================================================================
# query_active_raw
# ============================================================================


class TestQueryActiveRaw:
    """
    Contract:
    - Returns raw ClickHouse rows (NOT transformed)
    - Used by Kafka bridge for tracking incident_ids
    """

    @patch("apps.monitoring.incident_service.query")
    def test_returns_raw_rows(self, mock_query):
        raw_row = {
            "incident_id": "inc-001",
            "fiber_id": "carros",
            "channel_start": 150,
            "timestamp": datetime(2025, 6, 1, 12, 0, 0),
        }
        mock_query.return_value = [raw_row]
        result = query_active_raw(fiber_ids=["carros"])

        # Raw rows should NOT have transform applied
        assert len(result) == 1
        assert result[0] is raw_row  # Same object, not transformed
        assert "fiberLine" not in result[0]
        assert "fiber_id" in result[0]

    @patch("apps.monitoring.incident_service.query")
    def test_scoped_uses_fiber_filter(self, mock_query):
        mock_query.return_value = []
        query_active_raw(fiber_ids=["carros", "mathis"])

        sql = mock_query.call_args[0][0]
        assert "fiber_id IN" in sql

    @patch("apps.monitoring.incident_service.query")
    def test_unscoped_no_filter(self, mock_query):
        mock_query.return_value = []
        query_active_raw(fiber_ids=None)

        sql = mock_query.call_args[0][0]
        assert "fiber_id IN" not in sql


# ============================================================================
# Integration: transform + strip roundtrip
# ============================================================================


class TestTransformOrgRoutingRoundtrip:
    """
    End-to-end behavioral test for the fiberLine normalization chain:
    1. ClickHouse stores 'carros' (no direction)
    2. transform_row normalizes to 'carros:0'
    3. _org_broadcast strips to 'carros' for fiber_org_map lookup
    4. fiber_org_map (keyed by 'carros') matches → org routing works

    This test verifies the contract that the full chain is coherent.
    """

    def test_plain_fiber_id_roundtrips_through_org_routing(self):
        """Simulates the full ClickHouse → transform → org_broadcast → fiber_org_map chain."""
        fiber_org_map = {"carros": ["org-1", "org-2"], "mathis": ["org-1"]}

        # Step 1: ClickHouse returns plain fiber_id
        ch_row = {
            "incident_id": "inc-001",
            "incident_type": "accident",
            "severity": "high",
            "fiber_id": "carros",  # Plain — no directional suffix
            "channel_start": 150,
            "timestamp": datetime(2025, 6, 1, 12, 0, 0),
            "status": "active",
            "duration_seconds": 300,
        }

        # Step 2: transform_row normalizes
        transformed = transform_row(ch_row)
        assert transformed["fiberLine"] == "carros:0"

        # Step 3: _org_broadcast logic (replicated here)
        fid = transformed["fiberLine"]
        parent_fid = strip_directional_suffix(fid)
        assert parent_fid == "carros"

        # Step 4: fiber_org_map lookup succeeds
        orgs = fiber_org_map.get(parent_fid, [])
        assert orgs == ["org-1", "org-2"]

    def test_already_directional_fiber_id_roundtrips(self):
        """Directional fiber_id from ClickHouse also routes correctly."""
        fiber_org_map = {"carros": ["org-1"]}

        ch_row = {
            "incident_id": "inc-002",
            "incident_type": "congestion",
            "severity": "low",
            "fiber_id": "carros:0",
            "channel_start": 80,
            "timestamp": datetime(2025, 6, 1, 11, 0, 0),
            "status": "active",
            "duration_seconds": None,
        }

        transformed = transform_row(ch_row)
        assert transformed["fiberLine"] == "carros:0"

        parent_fid = strip_directional_suffix(transformed["fiberLine"])
        assert parent_fid == "carros"
        assert fiber_org_map.get(parent_fid) == ["org-1"]

    def test_simulation_incident_roundtrips(self):
        """Simulation incidents also route correctly through the same chain."""
        fiber_org_map = {"mathis": ["org-3"]}

        class FakeInc:
            id = "sim-001"
            type = "slowdown"
            severity = "low"
            fiber_line = "mathis"
            channel = 75
            detected_at = "2025-06-01T12:00:00Z"
            status = "active"
            duration = 5000

        transformed = transform_simulation_incident(FakeInc())
        assert transformed["fiberLine"] == "mathis:0"

        parent_fid = strip_directional_suffix(transformed["fiberLine"])
        assert fiber_org_map.get(parent_fid) == ["org-3"]
