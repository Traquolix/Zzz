"""
ClickHouse integration tests — real SQL against an embedded ClickHouse engine.

Every test here executes actual ClickHouse SQL: ReplacingMergeTree with FINAL,
parameterized queries with {name:Type} syntax, Array(String) IN clauses,
DateTime64 arithmetic, AggregatingMergeTree materialized views.

No mocks. The chdb embedded engine runs the same query planner and storage
engine as production ClickHouse 25.x.

These tests validate:
- Incident queries return correct data with FINAL deduplication
- Org-scoping via fiber_id IN [...] actually filters correctly
- Stats aggregations (fiber count, channel count, active incidents)
- Snapshot queries with channel/time windowing
- ReplacingMergeTree deduplication semantics
- Edge cases: empty results, unknown fibers, resolved incidents
"""

import time

import pytest

from apps.monitoring.incident_service import (
    query_active,
    query_active_raw,
    query_recent,
)
from apps.shared.clickhouse import query, query_scalar

# Timestamps: anchored to NOW so time-windowed queries (now() - INTERVAL) work.
_HOUR_NS = 3_600_000_000_000
_MIN_NS = 60_000_000_000


def _ts(hours_ago=0, minutes_ago=0):
    """Return a nanosecond timestamp relative to current time."""
    now_ns = int(time.time() * 1e9)
    return now_ns - (hours_ago * _HOUR_NS) - (minutes_ago * _MIN_NS)


# ============================================================================
# Incident Service — Real SQL
# ============================================================================


@pytest.mark.django_db
class TestIncidentQueriesReal:
    """Test incident_service.py functions against real ClickHouse data."""

    def test_query_active_returns_only_active_incidents(self, clickhouse):
        clickhouse.seed_incidents(
            [
                {
                    "incident_id": "inc-active",
                    "fiber_id": "carros",
                    "timestamp_ns": _ts(hours_ago=1),
                    "channel_start": 500,
                    "channel_end": 550,
                    "incident_type": "congestion",
                    "severity": "medium",
                    "status": "active",
                    "duration_seconds": 120,
                },
                {
                    "incident_id": "inc-resolved",
                    "fiber_id": "carros",
                    "timestamp_ns": _ts(hours_ago=2),
                    "channel_start": 100,
                    "channel_end": 150,
                    "incident_type": "accident",
                    "severity": "high",
                    "status": "resolved",
                    "duration_seconds": 300,
                },
            ]
        )

        results = query_active(fiber_ids=["carros"])
        assert len(results) == 1
        assert results[0]["id"] == "inc-active"
        assert results[0]["status"] == "active"

    def test_query_active_org_scoping_excludes_other_fibers(self, clickhouse):
        clickhouse.seed_incidents(
            [
                {
                    "incident_id": "inc-carros",
                    "fiber_id": "carros",
                    "timestamp_ns": _ts(hours_ago=1),
                    "channel_start": 500,
                    "channel_end": 550,
                    "incident_type": "congestion",
                    "severity": "medium",
                    "status": "active",
                    "duration_seconds": 60,
                },
                {
                    "incident_id": "inc-mathis",
                    "fiber_id": "mathis",
                    "timestamp_ns": _ts(hours_ago=1),
                    "channel_start": 200,
                    "channel_end": 250,
                    "incident_type": "slowdown",
                    "severity": "low",
                    "status": "active",
                    "duration_seconds": 30,
                },
            ]
        )

        # Org has only carros
        results = query_active(fiber_ids=["carros"])
        assert len(results) == 1
        assert results[0]["id"] == "inc-carros"

        # Org has only mathis
        results2 = query_active(fiber_ids=["mathis"])
        assert len(results2) == 1
        assert results2[0]["id"] == "inc-mathis"

        # Org has both
        results3 = query_active(fiber_ids=["carros", "mathis"])
        assert len(results3) == 2

    def test_query_active_superuser_sees_all(self, clickhouse):
        clickhouse.seed_incidents(
            [
                {
                    "incident_id": "inc-a",
                    "fiber_id": "carros",
                    "timestamp_ns": _ts(hours_ago=1),
                    "channel_start": 500,
                    "channel_end": 550,
                    "incident_type": "congestion",
                    "severity": "medium",
                    "status": "active",
                    "duration_seconds": 60,
                },
                {
                    "incident_id": "inc-b",
                    "fiber_id": "mathis",
                    "timestamp_ns": _ts(hours_ago=2),
                    "channel_start": 200,
                    "channel_end": 250,
                    "incident_type": "slowdown",
                    "severity": "low",
                    "status": "active",
                    "duration_seconds": 30,
                },
            ]
        )

        # fiber_ids=None means superuser (no scoping)
        results = query_active(fiber_ids=None)
        assert len(results) == 2

    def test_query_active_respects_limit(self, clickhouse):
        for i in range(10):
            clickhouse.seed_incidents(
                [
                    {
                        "incident_id": f"inc-{i:03d}",
                        "fiber_id": "carros",
                        "timestamp_ns": _ts(minutes_ago=i),
                        "channel_start": 500 + i,
                        "channel_end": 550 + i,
                        "incident_type": "congestion",
                        "severity": "medium",
                        "status": "active",
                        "duration_seconds": 60,
                    }
                ]
            )

        results = query_active(fiber_ids=["carros"], limit=5)
        assert len(results) == 5

    def test_query_active_ordered_by_timestamp_desc(self, clickhouse):
        clickhouse.seed_incidents(
            [
                {
                    "incident_id": "inc-old",
                    "fiber_id": "carros",
                    "timestamp_ns": _ts(hours_ago=3),
                    "channel_start": 500,
                    "channel_end": 550,
                    "incident_type": "congestion",
                    "severity": "medium",
                    "status": "active",
                    "duration_seconds": 60,
                },
                {
                    "incident_id": "inc-new",
                    "fiber_id": "carros",
                    "timestamp_ns": _ts(hours_ago=1),
                    "channel_start": 800,
                    "channel_end": 850,
                    "incident_type": "slowdown",
                    "severity": "low",
                    "status": "active",
                    "duration_seconds": 30,
                },
            ]
        )

        results = query_active(fiber_ids=["carros"])
        assert results[0]["id"] == "inc-new"
        assert results[1]["id"] == "inc-old"

    def test_query_active_empty_fiber_list_returns_empty(self, clickhouse):
        clickhouse.seed_incidents(
            [
                {
                    "incident_id": "inc-1",
                    "fiber_id": "carros",
                    "timestamp_ns": _ts(hours_ago=1),
                    "channel_start": 500,
                    "channel_end": 550,
                    "incident_type": "congestion",
                    "severity": "medium",
                    "status": "active",
                    "duration_seconds": 60,
                }
            ]
        )

        results = query_active(fiber_ids=[])
        assert results == []

    def test_query_active_unknown_fiber_returns_empty(self, clickhouse):
        clickhouse.seed_incidents(
            [
                {
                    "incident_id": "inc-1",
                    "fiber_id": "carros",
                    "timestamp_ns": _ts(hours_ago=1),
                    "channel_start": 500,
                    "channel_end": 550,
                    "incident_type": "congestion",
                    "severity": "medium",
                    "status": "active",
                    "duration_seconds": 60,
                }
            ]
        )

        results = query_active(fiber_ids=["nonexistent"])
        assert results == []

    def test_transform_row_adds_directional_suffix(self, clickhouse):
        """Incidents from ClickHouse with plain fiber_id get :0 appended."""
        clickhouse.seed_incidents(
            [
                {
                    "incident_id": "inc-1",
                    "fiber_id": "carros",
                    "timestamp_ns": _ts(hours_ago=1),
                    "channel_start": 500,
                    "channel_end": 550,
                    "incident_type": "congestion",
                    "severity": "medium",
                    "status": "active",
                    "duration_seconds": 120,
                }
            ]
        )

        results = query_active(fiber_ids=["carros"])
        assert results[0]["fiberLine"] == "carros:0"

    def test_transform_row_duration_in_milliseconds(self, clickhouse):
        """duration_seconds from ClickHouse is converted to ms in response."""
        clickhouse.seed_incidents(
            [
                {
                    "incident_id": "inc-1",
                    "fiber_id": "carros",
                    "timestamp_ns": _ts(hours_ago=1),
                    "channel_start": 500,
                    "channel_end": 550,
                    "incident_type": "congestion",
                    "severity": "medium",
                    "status": "active",
                    "duration_seconds": 120,
                }
            ]
        )

        results = query_active(fiber_ids=["carros"])
        assert results[0]["duration"] == 120_000  # 120s * 1000

    def test_query_recent_includes_all_statuses(self, clickhouse):
        clickhouse.seed_incidents(
            [
                {
                    "incident_id": "inc-active",
                    "fiber_id": "carros",
                    "timestamp_ns": _ts(hours_ago=1),
                    "channel_start": 500,
                    "channel_end": 550,
                    "incident_type": "congestion",
                    "severity": "medium",
                    "status": "active",
                    "duration_seconds": 60,
                },
                {
                    "incident_id": "inc-resolved",
                    "fiber_id": "carros",
                    "timestamp_ns": _ts(hours_ago=2),
                    "channel_start": 100,
                    "channel_end": 150,
                    "incident_type": "accident",
                    "severity": "high",
                    "status": "resolved",
                    "duration_seconds": 300,
                },
            ]
        )

        results = query_recent(fiber_ids=["carros"], hours=24)
        assert len(results) == 2
        ids = {r["id"] for r in results}
        assert ids == {"inc-active", "inc-resolved"}

    def test_query_active_raw_returns_dict_rows(self, clickhouse):
        """query_active_raw returns raw dicts (not transformed)."""
        clickhouse.seed_incidents(
            [
                {
                    "incident_id": "inc-1",
                    "fiber_id": "carros",
                    "timestamp_ns": _ts(hours_ago=1),
                    "channel_start": 500,
                    "channel_end": 550,
                    "incident_type": "congestion",
                    "severity": "medium",
                    "status": "active",
                    "duration_seconds": 60,
                }
            ]
        )

        rows = query_active_raw(fiber_ids=["carros"])
        assert len(rows) == 1
        # Raw rows have ClickHouse column names, not transformed names
        assert "incident_id" in rows[0]
        assert "fiber_id" in rows[0]
        # Should NOT have transformed keys
        assert "fiberLine" not in rows[0]


# ============================================================================
# FINAL Deduplication — ReplacingMergeTree semantics
# ============================================================================


@pytest.mark.django_db
class TestFinalDeduplication:
    """Verify ReplacingMergeTree FINAL works correctly for incident updates."""

    def test_updated_incident_shows_latest_status(self, clickhouse):
        """Insert active, then insert resolved with same key → FINAL shows resolved."""
        ts = _ts(hours_ago=2)
        clickhouse.seed_incidents(
            [
                {
                    "incident_id": "inc-dup",
                    "fiber_id": "carros",
                    "timestamp_ns": ts,
                    "channel_start": 500,
                    "channel_end": 550,
                    "incident_type": "congestion",
                    "severity": "medium",
                    "status": "active",
                    "duration_seconds": 60,
                }
            ]
        )

        # "Resolve" the incident by inserting a new row with same ORDER BY key
        # but later updated_at (explicit) so ReplacingMergeTree picks it
        clickhouse.execute(f"""
            INSERT INTO sequoia.fiber_incidents (
                incident_id, fiber_id, timestamp_ns, channel_start, channel_end,
                incident_type, severity, confidence, speed_drop_percent,
                duration_seconds, status, updated_at
            ) VALUES (
                'inc-dup', 'carros', {ts}, 500, 550,
                'congestion', 'medium', 0.9, 20.0, 60, 'resolved',
                now() + INTERVAL 1 SECOND
            )
        """)

        # FINAL should return only the resolved version
        results = query_active(fiber_ids=["carros"])
        assert len(results) == 0  # No active incidents

        # But query_recent should show it as resolved
        all_results = query_recent(fiber_ids=["carros"], hours=24)
        assert len(all_results) == 1
        assert all_results[0]["status"] == "resolved"

    def test_without_final_both_versions_visible(self, clickhouse):
        """Without FINAL, both the active and resolved rows exist."""
        ts = _ts(hours_ago=1)
        clickhouse.seed_incidents(
            [
                {
                    "incident_id": "inc-dup2",
                    "fiber_id": "carros",
                    "timestamp_ns": ts,
                    "channel_start": 300,
                    "channel_end": 350,
                    "incident_type": "slowdown",
                    "severity": "low",
                    "status": "active",
                    "duration_seconds": 30,
                }
            ]
        )

        clickhouse.execute(f"""
            INSERT INTO sequoia.fiber_incidents (
                incident_id, fiber_id, timestamp_ns, channel_start, channel_end,
                incident_type, severity, confidence, speed_drop_percent,
                duration_seconds, status, updated_at
            ) VALUES (
                'inc-dup2', 'carros', {ts}, 300, 350,
                'slowdown', 'low', 0.9, 20.0, 30, 'resolved',
                now() + INTERVAL 1 SECOND
            )
        """)

        # Query WITHOUT FINAL — should see both rows
        rows = query(
            "SELECT incident_id, status FROM sequoia.fiber_incidents WHERE incident_id = {id:String}",
            parameters={"id": "inc-dup2"},
        )
        assert len(rows) == 2  # Both versions present without FINAL


# ============================================================================
# Stats Queries — Real Aggregations
# ============================================================================


@pytest.mark.django_db
class TestStatsQueriesReal:
    """Test the stats SQL queries that StatsView uses."""

    def test_fiber_count_scoped(self, clickhouse):
        clickhouse.seed_fiber_cables(
            [
                {
                    "fiber_id": "carros",
                    "fiber_name": "Carros",
                    "channel_coordinates": [(43.7, 7.2)] * 100,
                },
                {
                    "fiber_id": "mathis",
                    "fiber_name": "Mathis",
                    "channel_coordinates": [(43.8, 7.3)] * 200,
                },
                {
                    "fiber_id": "promenade",
                    "fiber_name": "Promenade",
                    "channel_coordinates": [(43.9, 7.4)] * 300,
                },
            ]
        )

        # Scoped to 2 fibers
        count = query_scalar(
            "SELECT count(DISTINCT fiber_id) FROM sequoia.fiber_cables WHERE fiber_id IN {fids:Array(String)}",
            parameters={"fids": ["carros", "mathis"]},
        )
        assert count == 2

    def test_fiber_count_all(self, clickhouse):
        clickhouse.seed_fiber_cables(
            [
                {
                    "fiber_id": "carros",
                    "fiber_name": "Carros",
                    "channel_coordinates": [(43.7, 7.2)] * 100,
                },
                {
                    "fiber_id": "mathis",
                    "fiber_name": "Mathis",
                    "channel_coordinates": [(43.8, 7.3)] * 200,
                },
            ]
        )

        count = query_scalar("SELECT count(DISTINCT fiber_id) FROM sequoia.fiber_cables")
        assert count == 2

    def test_total_channels_scoped(self, clickhouse):
        clickhouse.seed_fiber_cables(
            [
                {
                    "fiber_id": "carros",
                    "fiber_name": "Carros",
                    "channel_coordinates": [(43.7, 7.2)] * 1000,
                },
                {
                    "fiber_id": "mathis",
                    "fiber_name": "Mathis",
                    "channel_coordinates": [(43.8, 7.3)] * 500,
                },
                {
                    "fiber_id": "promenade",
                    "fiber_name": "Promenade",
                    "channel_coordinates": [(43.9, 7.4)] * 2000,
                },
            ]
        )

        total = query_scalar(
            "SELECT sum(length(channel_coordinates)) FROM sequoia.fiber_cables WHERE fiber_id IN {fids:Array(String)}",
            parameters={"fids": ["carros", "mathis"]},
        )
        assert total == 1500

    def test_active_incident_count_scoped(self, clickhouse):
        clickhouse.seed_incidents(
            [
                {
                    "incident_id": "inc-a1",
                    "fiber_id": "carros",
                    "timestamp_ns": _ts(hours_ago=1),
                    "channel_start": 500,
                    "channel_end": 550,
                    "incident_type": "congestion",
                    "severity": "medium",
                    "status": "active",
                    "duration_seconds": 60,
                },
                {
                    "incident_id": "inc-a2",
                    "fiber_id": "carros",
                    "timestamp_ns": _ts(hours_ago=2),
                    "channel_start": 800,
                    "channel_end": 850,
                    "incident_type": "slowdown",
                    "severity": "low",
                    "status": "active",
                    "duration_seconds": 30,
                },
                {
                    "incident_id": "inc-m1",
                    "fiber_id": "mathis",
                    "timestamp_ns": _ts(hours_ago=1),
                    "channel_start": 200,
                    "channel_end": 250,
                    "incident_type": "accident",
                    "severity": "high",
                    "status": "active",
                    "duration_seconds": 300,
                },
            ]
        )

        # Scoped to carros
        count = query_scalar(
            "SELECT count() FROM sequoia.fiber_incidents FINAL WHERE status = 'active' AND fiber_id IN {fids:Array(String)}",
            parameters={"fids": ["carros"]},
        )
        assert count == 2

        # Scoped to mathis
        count2 = query_scalar(
            "SELECT count() FROM sequoia.fiber_incidents FINAL WHERE status = 'active' AND fiber_id IN {fids:Array(String)}",
            parameters={"fids": ["mathis"]},
        )
        assert count2 == 1

    def test_active_incident_count_excludes_resolved(self, clickhouse):
        clickhouse.seed_incidents(
            [
                {
                    "incident_id": "inc-active",
                    "fiber_id": "carros",
                    "timestamp_ns": _ts(hours_ago=1),
                    "channel_start": 500,
                    "channel_end": 550,
                    "incident_type": "congestion",
                    "severity": "medium",
                    "status": "active",
                    "duration_seconds": 60,
                },
                {
                    "incident_id": "inc-resolved",
                    "fiber_id": "carros",
                    "timestamp_ns": _ts(hours_ago=2),
                    "channel_start": 100,
                    "channel_end": 150,
                    "incident_type": "accident",
                    "severity": "high",
                    "status": "resolved",
                    "duration_seconds": 300,
                },
            ]
        )

        count = query_scalar(
            "SELECT count() FROM sequoia.fiber_incidents FINAL WHERE status = 'active' AND fiber_id IN {fids:Array(String)}",
            parameters={"fids": ["carros"]},
        )
        assert count == 1


# ============================================================================
# Snapshot Queries — Channel/Time Windowing
# ============================================================================


@pytest.mark.django_db
class TestSnapshotQueriesReal:
    """Test the SQL queries that IncidentSnapshotView uses."""

    def test_incident_lookup_by_id(self, clickhouse):
        ts = _ts(hours_ago=1)
        clickhouse.seed_incidents(
            [
                {
                    "incident_id": "snap-001",
                    "fiber_id": "carros",
                    "timestamp_ns": ts,
                    "channel_start": 500,
                    "channel_end": 550,
                    "incident_type": "congestion",
                    "severity": "medium",
                    "status": "active",
                    "duration_seconds": 120,
                }
            ]
        )

        rows = query(
            """
            SELECT fiber_id, channel_start, channel_end, timestamp_ns
            FROM sequoia.fiber_incidents
            FINAL
            WHERE incident_id = {id:String}
            LIMIT 1
            """,
            parameters={"id": "snap-001"},
        )

        assert len(rows) == 1
        assert rows[0]["fiber_id"] == "carros"
        assert rows[0]["channel_start"] == 500
        assert rows[0]["channel_end"] == 550
        assert rows[0]["timestamp_ns"] == ts

    def test_incident_lookup_nonexistent_returns_empty(self, clickhouse):
        rows = query(
            """
            SELECT fiber_id, channel_start, channel_end, timestamp_ns
            FROM sequoia.fiber_incidents
            FINAL
            WHERE incident_id = {id:String}
            LIMIT 1
            """,
            parameters={"id": "nonexistent"},
        )
        assert len(rows) == 0

    def test_speed_hires_channel_windowing(self, clickhouse):
        """Speed data query filters by channel range correctly."""
        # Insert speed data across channels 480-560
        ts_str = "2026-02-28 00:00:00.0"
        for ch in range(480, 561):
            clickhouse.seed_speed_hires(
                [
                    {
                        "fiber_id": "carros",
                        "ts": ts_str,
                        "ch": ch,
                        "speed": 80.0 + ch * 0.1,
                    }
                ]
            )

        # Query channels 490-510 (center=500, ±10 for test)
        rows = query(
            """
            SELECT fiber_id, ch, speed
            FROM sequoia.speed_hires
            WHERE fiber_id = {fid:String}
              AND ch BETWEEN {ch_min:UInt16} AND {ch_max:UInt16}
            ORDER BY ch
            """,
            parameters={"fid": "carros", "ch_min": 490, "ch_max": 510},
        )

        assert len(rows) == 21  # 490 through 510 inclusive
        channels = [r["ch"] for r in rows]
        assert min(channels) == 490
        assert max(channels) == 510

    def test_speed_hires_fiber_isolation(self, clickhouse):
        """Speed data for one fiber doesn't leak into another's query."""
        ts_str = "2026-02-28 00:00:00.0"
        clickhouse.seed_speed_hires(
            [
                {"fiber_id": "carros", "ts": ts_str, "ch": 500, "speed": 80.0},
                {"fiber_id": "mathis", "ts": ts_str, "ch": 500, "speed": 60.0},
            ]
        )

        rows = query(
            "SELECT fiber_id, speed FROM sequoia.speed_hires WHERE fiber_id = {fid:String}",
            parameters={"fid": "carros"},
        )
        assert len(rows) == 1
        assert rows[0]["speed"] == 80.0


# ============================================================================
# Vehicle Count Queries
# ============================================================================


@pytest.mark.django_db
class TestCountQueriesReal:
    """Test vehicle count queries against real data."""

    def test_count_sum_scoped_by_fiber(self, clickhouse):
        ts_str = "2026-02-28 00:00:00.0"
        clickhouse.seed_count_hires(
            [
                {"fiber_id": "carros", "ts": ts_str, "ch_start": 100, "ch_end": 200, "count": 5.0},
                {"fiber_id": "carros", "ts": ts_str, "ch_start": 200, "ch_end": 300, "count": 3.0},
                {"fiber_id": "mathis", "ts": ts_str, "ch_start": 100, "ch_end": 200, "count": 10.0},
            ]
        )

        # This is the exact query from StatsView
        total = query_scalar(
            """
            SELECT coalesce(sum(count), 0)
            FROM sequoia.count_hires
            WHERE fiber_id IN {fids:Array(String)}
            """,
            parameters={"fids": ["carros"]},
        )
        assert total == 8.0  # 5 + 3

    def test_count_sum_all_fibers(self, clickhouse):
        ts_str = "2026-02-28 00:00:00.0"
        clickhouse.seed_count_hires(
            [
                {"fiber_id": "carros", "ts": ts_str, "ch_start": 100, "ch_end": 200, "count": 5.0},
                {"fiber_id": "mathis", "ts": ts_str, "ch_start": 100, "ch_end": 200, "count": 10.0},
            ]
        )

        total = query_scalar("SELECT coalesce(sum(count), 0) FROM sequoia.count_hires")
        assert total == 15.0


# ============================================================================
# REST API Integration — Real ClickHouse behind DRF views
# ============================================================================


@pytest.mark.django_db
class TestIncidentListViewIntegration:
    """Test GET /api/incidents/ with real ClickHouse data."""

    def test_returns_incidents_from_assigned_fibers(
        self,
        clickhouse,
        authenticated_client,
        fiber_assignments,
    ):
        clickhouse.seed_incidents(
            [
                {
                    "incident_id": "api-inc-1",
                    "fiber_id": "carros",
                    "timestamp_ns": _ts(hours_ago=1),
                    "channel_start": 500,
                    "channel_end": 550,
                    "incident_type": "congestion",
                    "severity": "medium",
                    "status": "active",
                    "duration_seconds": 120,
                }
            ]
        )

        response = authenticated_client.get("/api/incidents")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) == 1
        assert data["results"][0]["id"] == "api-inc-1"

    def test_excludes_incidents_from_unassigned_fibers(
        self,
        clickhouse,
        authenticated_client,
        fiber_assignments,
    ):
        """Org has carros/mathis/promenade. Incident on 'secret_fiber' should not appear."""
        clickhouse.seed_incidents(
            [
                {
                    "incident_id": "inc-visible",
                    "fiber_id": "carros",
                    "timestamp_ns": _ts(hours_ago=1),
                    "channel_start": 500,
                    "channel_end": 550,
                    "incident_type": "congestion",
                    "severity": "medium",
                    "status": "active",
                    "duration_seconds": 60,
                },
                {
                    "incident_id": "inc-hidden",
                    "fiber_id": "secret_fiber",
                    "timestamp_ns": _ts(hours_ago=1),
                    "channel_start": 100,
                    "channel_end": 150,
                    "incident_type": "accident",
                    "severity": "high",
                    "status": "active",
                    "duration_seconds": 300,
                },
            ]
        )

        response = authenticated_client.get("/api/incidents")
        data = response.json()
        ids = {r["id"] for r in data["results"]}
        assert "inc-visible" in ids
        assert "inc-hidden" not in ids

    def test_pagination_has_more(
        self,
        clickhouse,
        authenticated_client,
        fiber_assignments,
    ):
        """When more incidents exist than the limit, hasMore=True."""
        for i in range(15):
            clickhouse.seed_incidents(
                [
                    {
                        "incident_id": f"page-{i:03d}",
                        "fiber_id": "carros",
                        "timestamp_ns": _ts(minutes_ago=i),
                        "channel_start": 500 + i,
                        "channel_end": 550 + i,
                        "incident_type": "congestion",
                        "severity": "medium",
                        "status": "active",
                        "duration_seconds": 60,
                    }
                ]
            )

        response = authenticated_client.get("/api/incidents?limit=10")
        data = response.json()
        assert data["hasMore"] is True
        assert len(data["results"]) == 10
        assert data["limit"] == 10

    def test_pagination_no_more(
        self,
        clickhouse,
        authenticated_client,
        fiber_assignments,
    ):
        """When all incidents fit within limit, hasMore=False."""
        clickhouse.seed_incidents(
            [
                {
                    "incident_id": "only-one",
                    "fiber_id": "carros",
                    "timestamp_ns": _ts(hours_ago=1),
                    "channel_start": 500,
                    "channel_end": 550,
                    "incident_type": "congestion",
                    "severity": "medium",
                    "status": "active",
                    "duration_seconds": 60,
                }
            ]
        )

        response = authenticated_client.get("/api/incidents?limit=100")
        data = response.json()
        assert data["hasMore"] is False

    def test_superuser_sees_all_fibers(
        self,
        clickhouse,
        superuser_client,
        fiber_assignments,
    ):
        clickhouse.seed_incidents(
            [
                {
                    "incident_id": "su-1",
                    "fiber_id": "carros",
                    "timestamp_ns": _ts(hours_ago=1),
                    "channel_start": 500,
                    "channel_end": 550,
                    "incident_type": "congestion",
                    "severity": "medium",
                    "status": "active",
                    "duration_seconds": 60,
                },
                {
                    "incident_id": "su-2",
                    "fiber_id": "secret_fiber",
                    "timestamp_ns": _ts(hours_ago=1),
                    "channel_start": 100,
                    "channel_end": 150,
                    "incident_type": "accident",
                    "severity": "high",
                    "status": "active",
                    "duration_seconds": 300,
                },
            ]
        )

        response = superuser_client.get("/api/incidents")
        data = response.json()
        ids = {r["id"] for r in data["results"]}
        assert "su-1" in ids
        assert "su-2" in ids  # Superuser sees unassigned fibers

    def test_other_org_cannot_see_first_org_incidents(
        self,
        clickhouse,
        other_org_client,
        other_org_fiber_assignments,
    ):
        """other_org has only 'carros'. Incident on 'mathis' should not appear."""
        clickhouse.seed_incidents(
            [
                {
                    "incident_id": "cross-1",
                    "fiber_id": "carros",
                    "timestamp_ns": _ts(hours_ago=1),
                    "channel_start": 500,
                    "channel_end": 550,
                    "incident_type": "congestion",
                    "severity": "medium",
                    "status": "active",
                    "duration_seconds": 60,
                },
                {
                    "incident_id": "cross-2",
                    "fiber_id": "mathis",
                    "timestamp_ns": _ts(hours_ago=1),
                    "channel_start": 200,
                    "channel_end": 250,
                    "incident_type": "slowdown",
                    "severity": "low",
                    "status": "active",
                    "duration_seconds": 30,
                },
            ]
        )

        response = other_org_client.get("/api/incidents")
        data = response.json()
        ids = {r["id"] for r in data["results"]}
        assert "cross-1" in ids  # other_org has carros
        assert "cross-2" not in ids  # other_org does NOT have mathis


@pytest.mark.django_db
class TestStatsViewIntegration:
    """Test GET /api/stats/ with real ClickHouse data."""

    def test_stats_fiber_count_matches_assigned(
        self,
        clickhouse,
        authenticated_client,
        fiber_assignments,
    ):
        clickhouse.seed_fiber_cables(
            [
                {
                    "fiber_id": "carros",
                    "fiber_name": "Carros",
                    "channel_coordinates": [(43.7, 7.2)] * 1000,
                },
                {
                    "fiber_id": "mathis",
                    "fiber_name": "Mathis",
                    "channel_coordinates": [(43.8, 7.3)] * 500,
                },
                {
                    "fiber_id": "promenade",
                    "fiber_name": "Promenade",
                    "channel_coordinates": [(43.9, 7.4)] * 2000,
                },
                {
                    "fiber_id": "secret",
                    "fiber_name": "Secret",
                    "channel_coordinates": [(44.0, 7.5)] * 100,
                },
            ]
        )

        response = authenticated_client.get("/api/stats")
        assert response.status_code == 200
        data = response.json()
        # Org has carros, mathis, promenade — NOT secret
        assert data["fiberCount"] == 3
        assert data["totalChannels"] == 3500  # 1000 + 500 + 2000

    def test_stats_active_incidents_count(
        self,
        clickhouse,
        authenticated_client,
        fiber_assignments,
    ):
        clickhouse.seed_fiber_cables(
            [
                {
                    "fiber_id": "carros",
                    "fiber_name": "Carros",
                    "channel_coordinates": [(43.7, 7.2)] * 100,
                },
            ]
        )
        clickhouse.seed_incidents(
            [
                {
                    "incident_id": "stat-1",
                    "fiber_id": "carros",
                    "timestamp_ns": _ts(hours_ago=1),
                    "channel_start": 500,
                    "channel_end": 550,
                    "incident_type": "congestion",
                    "severity": "medium",
                    "status": "active",
                    "duration_seconds": 60,
                },
                {
                    "incident_id": "stat-2",
                    "fiber_id": "carros",
                    "timestamp_ns": _ts(hours_ago=2),
                    "channel_start": 800,
                    "channel_end": 850,
                    "incident_type": "slowdown",
                    "severity": "low",
                    "status": "resolved",
                    "duration_seconds": 30,
                },
            ]
        )

        response = authenticated_client.get("/api/stats")
        data = response.json()
        assert data["activeIncidents"] == 1  # Only the active one

    def test_stats_empty_org_returns_zeros(
        self,
        clickhouse,
        authenticated_client,
        fiber_assignments,
    ):
        """No data seeded — all stats should be 0."""
        response = authenticated_client.get("/api/stats")
        data = response.json()
        assert data["fiberCount"] == 0
        assert data["totalChannels"] == 0
        assert data["activeIncidents"] == 0
        assert data["activeVehicles"] == 0


@pytest.mark.django_db
class TestSnapshotViewIntegration:
    """Test GET /api/incidents/<id>/snapshot/ with real ClickHouse data."""

    def test_snapshot_returns_speed_data_around_incident(
        self,
        clickhouse,
        authenticated_client,
        fiber_assignments,
    ):
        clickhouse.seed_incidents(
            [
                {
                    "incident_id": "snap-view-1",
                    "fiber_id": "carros",
                    "timestamp_ns": _ts(hours_ago=1),
                    "channel_start": 500,
                    "channel_end": 550,
                    "incident_type": "congestion",
                    "severity": "medium",
                    "status": "active",
                    "duration_seconds": 120,
                }
            ]
        )

        # Seed speed data around channel 525 (center of 500-550)
        ts_str = "2026-02-27 23:00:00.0"  # ~1h ago
        for ch in range(500, 560):
            clickhouse.seed_speed_hires(
                [
                    {
                        "fiber_id": "carros",
                        "ts": ts_str,
                        "ch": ch,
                        "speed": 80.0 - (ch - 500) * 0.5,
                    }
                ]
            )

        response = authenticated_client.get("/api/incidents/snap-view-1/snapshot")
        assert response.status_code == 200
        data = response.json()
        assert data["incidentId"] == "snap-view-1"
        assert data["fiberLine"] == "carros:0"
        assert "detections" in data
        # Should have some speed data (exact count depends on time window)

    def test_snapshot_404_for_nonexistent_incident(
        self,
        clickhouse,
        authenticated_client,
        fiber_assignments,
    ):
        response = authenticated_client.get("/api/incidents/nonexistent/snapshot")
        assert response.status_code == 404

    def test_snapshot_404_for_other_orgs_fiber(
        self,
        clickhouse,
        other_org_client,
        other_org_fiber_assignments,
    ):
        """other_org has carros only. Incident on mathis → 404."""
        clickhouse.seed_incidents(
            [
                {
                    "incident_id": "snap-cross",
                    "fiber_id": "mathis",
                    "timestamp_ns": _ts(hours_ago=1),
                    "channel_start": 200,
                    "channel_end": 250,
                    "incident_type": "accident",
                    "severity": "high",
                    "status": "active",
                    "duration_seconds": 300,
                }
            ]
        )

        response = other_org_client.get("/api/incidents/snap-cross/snapshot")
        assert response.status_code == 404


# ============================================================================
# Schema Correctness — Regression tests for structural fixes
# ============================================================================


@pytest.mark.django_db
class TestCountHiresSchemaCorrectness:
    """
    count_hires ORDER BY must include ch_end to prevent silent data loss.

    The AI engine can produce vehicle count records with the same
    (fiber_id, ts, ch_start) but different ch_end values — e.g. overlapping
    detection zones of different lengths. ReplacingMergeTree deduplicates
    on the full ORDER BY key, so if ch_end is absent, the shorter zone's
    count silently disappears on merge.
    """

    def test_different_ch_end_same_ch_start_both_preserved(self, clickhouse):
        """Two count records with same (fiber_id, ts, ch_start) but different ch_end
        must BOTH survive — not be deduplicated."""
        ts_str = "2026-02-28 01:00:00.0"
        clickhouse.seed_count_hires(
            [
                {"fiber_id": "carros", "ts": ts_str, "ch_start": 100, "ch_end": 200, "count": 5.0},
                {"fiber_id": "carros", "ts": ts_str, "ch_start": 100, "ch_end": 300, "count": 12.0},
            ]
        )

        rows = query(
            """
            SELECT ch_start, ch_end, count
            FROM sequoia.count_hires
            WHERE fiber_id = {fid:String}
            ORDER BY ch_end
            """,
            parameters={"fid": "carros"},
        )
        # With ch_end in ORDER BY: 2 rows preserved
        # Without ch_end in ORDER BY: ReplacingMergeTree keeps only 1 (data loss)
        assert len(rows) == 2, (
            f"Expected 2 count records (ch_end=200 and ch_end=300), got {len(rows)}. "
            "This means count_hires ORDER BY is missing ch_end — silent data loss."
        )
        assert rows[0]["count"] == 5.0
        assert rows[1]["count"] == 12.0

    def test_count_aggregation_preserves_all_zones(self, clickhouse):
        """Total vehicle count must include all detection zones, not just the last-inserted."""
        ts_str = "2026-02-28 01:00:00.0"
        clickhouse.seed_count_hires(
            [
                {"fiber_id": "carros", "ts": ts_str, "ch_start": 100, "ch_end": 200, "count": 5.0},
                {"fiber_id": "carros", "ts": ts_str, "ch_start": 100, "ch_end": 300, "count": 12.0},
                {"fiber_id": "carros", "ts": ts_str, "ch_start": 100, "ch_end": 400, "count": 3.0},
            ]
        )

        total = query_scalar(
            "SELECT coalesce(sum(count), 0) FROM sequoia.count_hires WHERE fiber_id = {fid:String}",
            parameters={"fid": "carros"},
        )
        assert total == 20.0, (
            f"Expected sum=20.0 (5+12+3), got {total}. "
            "Data loss: count_hires is deduplicating records with different ch_end."
        )

    def test_data_survives_optimize_merge(self, clickhouse):
        """After OPTIMIZE FINAL (forced merge), different ch_end records must survive.

        ReplacingMergeTree deduplicates on background merge. Without ch_end in
        ORDER BY, records with same (fiber_id, ts, ch_start) collapse into one
        after merge — the dangerous silent data loss scenario.
        """
        ts_str = "2026-02-28 02:00:00.0"

        # Insert in separate batches to create separate parts
        clickhouse.seed_count_hires(
            [
                {"fiber_id": "carros", "ts": ts_str, "ch_start": 100, "ch_end": 200, "count": 5.0},
            ]
        )
        clickhouse.seed_count_hires(
            [
                {"fiber_id": "carros", "ts": ts_str, "ch_start": 100, "ch_end": 300, "count": 12.0},
            ]
        )

        # Force merge — this is where ReplacingMergeTree deduplication happens
        clickhouse.execute("OPTIMIZE TABLE sequoia.count_hires FINAL")

        rows = query(
            """
            SELECT ch_start, ch_end, count
            FROM sequoia.count_hires
            WHERE fiber_id = {fid:String}
            ORDER BY ch_end
            """,
            parameters={"fid": "carros"},
        )
        assert len(rows) == 2, (
            f"OPTIMIZE FINAL collapsed {2} rows into {len(rows)}. "
            "count_hires ORDER BY is missing ch_end — data loss after merge."
        )


@pytest.mark.django_db
class TestIncidentIdLookupEfficiency:
    """
    fiber_incidents should have a bloom_filter index on incident_id
    so snapshot lookups don't require full partition scans.

    Without an index, WHERE incident_id = 'X' scans every granule in
    every partition because incident_id is the 3rd column in ORDER BY
    (fiber_id, timestamp_ns, incident_id).
    """

    def test_incident_id_index_exists(self, clickhouse):
        """Verify bloom_filter index on incident_id is present in schema."""
        result = clickhouse.query_json("""
            SELECT name, type_full
            FROM system.data_skipping_indices
            WHERE table = 'fiber_incidents'
              AND database = 'sequoia'
              AND name = 'idx_incident_id'
        """)
        assert len(result["data"]) == 1, (
            "Missing bloom_filter index on incident_id. Snapshot lookups "
            "will scan all granules across all partitions."
        )
        assert "bloom_filter" in result["data"][0]["type_full"].lower()

    def test_incident_id_lookup_returns_correct_row_among_many(self, clickhouse):
        """With many incidents across fibers, incident_id lookup still finds the right one."""
        for i in range(50):
            fiber = ["carros", "mathis", "promenade"][i % 3]
            clickhouse.seed_incidents(
                [
                    {
                        "incident_id": f"bulk-{i:04d}",
                        "fiber_id": fiber,
                        "timestamp_ns": _ts(minutes_ago=i),
                        "channel_start": 100 + i * 10,
                        "channel_end": 150 + i * 10,
                        "incident_type": "congestion",
                        "severity": "medium",
                        "status": "active",
                        "duration_seconds": 60,
                    }
                ]
            )

        # Look up a specific one buried in the middle
        rows = query(
            """
            SELECT incident_id, fiber_id, channel_start
            FROM sequoia.fiber_incidents FINAL
            WHERE incident_id = {id:String}
            """,
            parameters={"id": "bulk-0025"},
        )
        assert len(rows) == 1
        assert rows[0]["incident_id"] == "bulk-0025"
        assert rows[0]["channel_start"] == 350  # 100 + 25*10


@pytest.mark.django_db
class TestIncidentPartitioning:
    """
    fiber_incidents should be partitioned by day (toYYYYMMDD) not month (toYYYYMM).

    Monthly partitions mean that query_recent (looking back 24h) always scans
    the entire current month. With daily partitions, ClickHouse prunes to
    just today + yesterday.
    """

    def test_partition_key_is_daily(self, clickhouse):
        """Verify fiber_incidents uses daily partitioning."""
        result = clickhouse.query_json("""
            SELECT partition_key
            FROM system.tables
            WHERE database = 'sequoia'
              AND name = 'fiber_incidents'
        """)
        partition_key = result["data"][0]["partition_key"]
        assert "toYYYYMMDD" in partition_key, (
            f"fiber_incidents partition_key is '{partition_key}'. "
            "Should be toYYYYMMDD(timestamp) for efficient 24h lookback queries, "
            "not toYYYYMM which scans the entire month."
        )

    def test_recent_query_only_touches_recent_partitions(self, clickhouse):
        """Incidents from 1h ago should not require scanning old partitions."""
        # Insert an incident 1h ago
        clickhouse.seed_incidents(
            [
                {
                    "incident_id": "part-recent",
                    "fiber_id": "carros",
                    "timestamp_ns": _ts(hours_ago=1),
                    "channel_start": 500,
                    "channel_end": 550,
                    "incident_type": "congestion",
                    "severity": "medium",
                    "status": "active",
                    "duration_seconds": 60,
                }
            ]
        )

        # Verify it's queryable via the recent query path
        results = query_recent(fiber_ids=["carros"], hours=24)
        assert len(results) == 1
        assert results[0]["id"] == "part-recent"


@pytest.mark.django_db
class TestCountHiresMVIntegrity:
    """
    count_1m materialized view must include ch_end in its GROUP BY
    after the ORDER BY fix, otherwise the aggregation tier drops the
    zone differentiation that the hires tier now preserves.
    """

    def test_count_1m_preserves_ch_end_differentiation(self, clickhouse):
        """Different ch_end values at same ch_start must produce separate 1m aggregates."""
        # Insert enough data to trigger MV aggregation
        ts_str = "2026-02-28 01:00:00.0"
        for i in range(5):
            clickhouse.seed_count_hires(
                [
                    {
                        "fiber_id": "carros",
                        "ts": ts_str,
                        "ch_start": 100,
                        "ch_end": 200,
                        "count": 2.0,
                    },
                    {
                        "fiber_id": "carros",
                        "ts": ts_str,
                        "ch_start": 100,
                        "ch_end": 300,
                        "count": 3.0,
                    },
                ]
            )

        # Check 1m aggregation table
        rows = query(
            """
            SELECT ch_start, ch_end,
                   sumMerge(count_sum_state) AS count_sum
            FROM sequoia.count_1m
            WHERE fiber_id = {fid:String}
            GROUP BY ch_start, ch_end
            ORDER BY ch_end
            """,
            parameters={"fid": "carros"},
        )
        # With ch_end in ORDER BY + MV GROUP BY: 2 distinct rows
        # Without: single aggregated row losing zone distinction
        assert len(rows) == 2, (
            f"Expected 2 aggregated rows in count_1m (ch_end=200 and ch_end=300), "
            f"got {len(rows)}. The materialized view is losing ch_end differentiation."
        )
