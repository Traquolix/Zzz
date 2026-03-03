"""
Tests for ClickHouse connection manager and circuit breaker.

Verifies the full circuit breaker state machine, thread-local client isolation,
Prometheus metrics instrumentation, Sentry error capture, and query helpers.
"""

import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock, patch

import pytest

from apps.shared.clickhouse import (
    _get_cooldown,
    _is_in_cooldown,
    _record_failure,
    _record_success,
    get_client,
    health,
    query,
    query_scalar,
)
from apps.shared.exceptions import ClickHouseUnavailableError
import apps.shared.clickhouse as ch


# ============================================================================
# Circuit Breaker State Machine
# ============================================================================

class TestCircuitBreakerStateMachine:
    """Verify the full state machine: healthy → failure → cooldown → recovery."""

    def test_initial_state_allows_queries(self):
        """Fresh module state: no failures, not in cooldown."""
        assert ch._consecutive_failures == 0
        assert not _is_in_cooldown()
        h = health()
        assert h['consecutive_failures'] == 0
        assert h['in_cooldown'] is False

    def test_first_failure_starts_cooldown(self):
        """A single failure transitions to cooldown state."""
        _record_failure()
        assert ch._consecutive_failures == 1
        assert ch._last_failure_time > 0
        # Immediately after failure, should be in cooldown
        assert _is_in_cooldown()

    def test_cooldown_blocks_get_client(self):
        """During cooldown, get_client raises without attempting connection."""
        _record_failure()

        with pytest.raises(ClickHouseUnavailableError, match='circuit breaker'):
            get_client()

    def test_exponential_backoff_1s_2s_4s_8s_cap(self):
        """Cooldown doubles with each failure, capping at 8s."""
        # Seed random for deterministic jitter=0
        with patch('apps.shared.clickhouse.random.random', return_value=0.5):
            # At jitter_factor=0.5 and random()=0.5, jitter = base * 0.5 * (2*0.5 - 1) = 0
            ch._consecutive_failures = 1
            assert abs(_get_cooldown() - 1.0) < 0.01

            ch._consecutive_failures = 2
            assert abs(_get_cooldown() - 2.0) < 0.01

            ch._consecutive_failures = 3
            assert abs(_get_cooldown() - 4.0) < 0.01

            ch._consecutive_failures = 4
            assert abs(_get_cooldown() - 8.0) < 0.01

            # Cap: 5th failure still 8s
            ch._consecutive_failures = 5
            assert abs(_get_cooldown() - 8.0) < 0.01

    def test_jitter_stays_within_50pct_band(self):
        """Jitter never exceeds ±50% of base cooldown."""
        rng = random.Random(42)
        ch._consecutive_failures = 2  # base = 2s

        cooldowns = []
        with patch('apps.shared.clickhouse.random.random', side_effect=lambda: rng.random()):
            for _ in range(200):
                cooldowns.append(_get_cooldown())

        base = 2.0
        for c in cooldowns:
            assert c >= base * 0.5, f"Cooldown {c} below 50% of base {base}"
            assert c <= base * 1.5, f"Cooldown {c} above 150% of base {base}"

        # Verify actual spread (not all the same value)
        assert max(cooldowns) - min(cooldowns) > 0.1

    def test_successful_query_resets_breaker(self):
        """Successful connection after failures resets counter to zero."""
        _record_failure()
        _record_failure()
        _record_failure()
        assert ch._consecutive_failures == 3

        _record_success()
        assert ch._consecutive_failures == 0
        assert ch._last_failure_time == 0.0
        assert not _is_in_cooldown()

    def test_health_reflects_current_state(self):
        """health() returns accurate snapshot of breaker state."""
        _record_failure()
        _record_failure()

        h = health()
        assert h['consecutive_failures'] == 2
        assert h['in_cooldown'] is True
        assert h['last_failure'] > 0

    def test_cooldown_expires_allows_retry(self):
        """After cooldown period, get_client attempts reconnection."""
        ch._consecutive_failures = 1
        # Set failure time far enough in the past that cooldown expired
        ch._last_failure_time = time.time() - 20.0  # 20s ago, well past 8s max

        assert not _is_in_cooldown()

        # Now get_client should attempt connection (not raise circuit breaker)
        mock_client = MagicMock()
        with patch('clickhouse_connect.get_client', return_value=mock_client):
            client = get_client()
            assert client is mock_client
            assert ch._consecutive_failures == 0  # Reset on success


# ============================================================================
# Thread-Local Client Isolation
# ============================================================================

class TestThreadLocalClients:
    """Verify thread safety: each thread gets its own client, breaker is global."""

    def test_each_thread_gets_own_client(self):
        """Concurrent threads receive distinct client instances."""
        clients = {}
        barrier = threading.Barrier(3)

        def _mock_factory(**kwargs):
            """Each call returns a unique mock (simulates real client creation)."""
            return MagicMock(name=f'client-{threading.current_thread().name}')

        # Patch at module level so all threads see the mock
        with patch('clickhouse_connect.get_client', side_effect=_mock_factory):
            def _get(thread_id):
                barrier.wait(timeout=5)
                c = get_client()
                clients[thread_id] = id(c)

            threads = [threading.Thread(target=_get, args=(i,)) for i in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

        # All 3 threads should have distinct client objects
        assert len(set(clients.values())) == 3

    def test_thread_a_failure_does_not_poison_thread_b_cached_client(self):
        """Thread B's cached client survives thread A's query failure."""
        mock_b = MagicMock(name='client-b')
        results = {}

        def thread_b():
            # Thread B has a cached client
            ch._local.client = mock_b
            time.sleep(0.1)  # Let thread A fail first
            # Thread B's cached client should still be there
            results['b_client'] = get_client()

        def thread_a():
            # Thread A has no cached client, connection fails
            try:
                with patch('clickhouse_connect.get_client', side_effect=Exception('fail')):
                    get_client()
            except ClickHouseUnavailableError:
                results['a_failed'] = True

        ta = threading.Thread(target=thread_a)
        tb = threading.Thread(target=thread_b)
        ta.start()
        tb.start()
        ta.join(timeout=5)
        tb.join(timeout=5)

        assert results.get('a_failed') is True
        assert results.get('b_client') is mock_b

    def test_global_breaker_affects_all_threads(self):
        """Circuit breaker trip in one thread blocks get_client in all threads."""
        # Trip the breaker
        _record_failure()
        assert _is_in_cooldown()

        errors = []

        def _try_get(thread_id):
            try:
                get_client()
            except ClickHouseUnavailableError:
                errors.append(thread_id)

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(_try_get, i) for i in range(3)]
            for f in as_completed(futures):
                f.result()

        # All 3 threads should have been blocked
        assert len(errors) == 3


# ============================================================================
# Query Instrumentation (Metrics + Sentry)
# ============================================================================

class TestQueryInstrumentation:
    """Verify Prometheus counters/histograms and Sentry capture on errors."""

    def test_success_increments_queries_counter(self):
        """Successful query increments CLICKHOUSE_QUERIES with status=success."""
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.column_names = ['count']
        mock_result.result_rows = [(42,)]
        mock_client.query.return_value = mock_result

        with patch('apps.shared.clickhouse.get_client', return_value=mock_client):
            from apps.shared.metrics import CLICKHOUSE_QUERIES
            before = CLICKHOUSE_QUERIES.labels(query_type='select', status='success')._value.get()
            query('SELECT count() FROM t')
            after = CLICKHOUSE_QUERIES.labels(query_type='select', status='success')._value.get()
            assert after > before

    def test_error_increments_queries_counter(self):
        """Failed query increments CLICKHOUSE_QUERIES with status=error."""
        mock_client = MagicMock()
        mock_client.query.side_effect = RuntimeError('connection lost')

        with patch('apps.shared.clickhouse.get_client', return_value=mock_client):
            from apps.shared.metrics import CLICKHOUSE_QUERIES
            before = CLICKHOUSE_QUERIES.labels(query_type='select', status='error')._value.get()
            with pytest.raises(ClickHouseUnavailableError):
                query('SELECT 1')
            after = CLICKHOUSE_QUERIES.labels(query_type='select', status='error')._value.get()
            assert after > before

    def test_circuit_breaker_increments_trips_counter(self):
        """Blocked get_client increments CLICKHOUSE_CIRCUIT_BREAKER_TRIPS."""
        _record_failure()  # Trip the breaker

        from apps.shared.metrics import CLICKHOUSE_CIRCUIT_BREAKER_TRIPS
        before = CLICKHOUSE_CIRCUIT_BREAKER_TRIPS._value.get()
        with pytest.raises(ClickHouseUnavailableError):
            get_client()
        after = CLICKHOUSE_CIRCUIT_BREAKER_TRIPS._value.get()
        assert after > before

    def test_sentry_capture_on_query_failure(self):
        """Query failure sends exception to Sentry."""
        mock_client = MagicMock()
        mock_client.query.side_effect = RuntimeError('disk full')

        with patch('apps.shared.clickhouse.get_client', return_value=mock_client), \
             patch('sentry_sdk.capture_exception') as mock_sentry:
            with pytest.raises(ClickHouseUnavailableError):
                query('SELECT 1')
            mock_sentry.assert_called_once()
            captured_exc = mock_sentry.call_args[0][0]
            assert isinstance(captured_exc, RuntimeError)
            assert 'disk full' in str(captured_exc)

    def test_error_log_includes_sql_preview_and_params(self, caplog):
        """Query failure logs truncated SQL and parameters."""
        mock_client = MagicMock()
        mock_client.query.side_effect = RuntimeError('timeout')

        with patch('apps.shared.clickhouse.get_client', return_value=mock_client):
            with pytest.raises(ClickHouseUnavailableError):
                query('SELECT * FROM speed_hires WHERE fiber_id = {fid:String}',
                      parameters={'fid': 'carros'})

        assert 'speed_hires' in caplog.text
        assert 'carros' in caplog.text

    def test_query_failure_resets_thread_local_client(self):
        """After query error, thread-local client is cleared for reconnection."""
        mock_client = MagicMock()
        mock_client.query.side_effect = RuntimeError('stale connection')

        # Pre-cache the client
        ch._local.client = mock_client

        with patch('apps.shared.clickhouse.get_client', return_value=mock_client):
            with pytest.raises(ClickHouseUnavailableError):
                query('SELECT 1')

        # Thread-local should be cleared
        assert getattr(ch._local, 'client', None) is None


# ============================================================================
# query_scalar
# ============================================================================

class TestQueryScalar:
    """Verify scalar extraction convenience function."""

    def test_returns_first_value_from_first_row(self):
        """Single scalar value extracted from first row."""
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.column_names = ['total']
        mock_result.result_rows = [(42,)]
        mock_client.query.return_value = mock_result

        with patch('apps.shared.clickhouse.get_client', return_value=mock_client):
            assert query_scalar('SELECT count()') == 42

    def test_returns_none_on_empty_result(self):
        """No rows → None."""
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.column_names = ['total']
        mock_result.result_rows = []
        mock_client.query.return_value = mock_result

        with patch('apps.shared.clickhouse.get_client', return_value=mock_client):
            assert query_scalar('SELECT count()') is None

    def test_multiple_rows_returns_first_only(self):
        """Multiple rows: only first row's first value returned."""
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.column_names = ['fiber_id']
        mock_result.result_rows = [('carros',), ('mathis',)]
        mock_client.query.return_value = mock_result

        with patch('apps.shared.clickhouse.get_client', return_value=mock_client):
            assert query_scalar('SELECT fiber_id') == 'carros'
