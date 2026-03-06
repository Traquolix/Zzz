"""
ClickHouse connection manager with circuit breaker.

Provides thread-local clients for read-only queries to the ClickHouse
time-series database that stores pipeline data (speeds, counts, incidents).

Uses thread-local storage to avoid "concurrent queries within same session"
errors when the Kafka bridge and API requests run simultaneously.

Circuit breaker: on connection failure, backs off exponentially
(1s → 2s → 4s → 8s max) with jitter to prevent thundering herd.
Individual threads are not blocked by other threads' failures.
"""

import functools
import logging
import random
import threading
import time

from django.conf import settings
from rest_framework.response import Response

from apps.shared.exceptions import ClickHouseUnavailableError

logger = logging.getLogger("sequoia.clickhouse")

_local = threading.local()

# Circuit breaker state (protected by lock)
_breaker_lock = threading.Lock()
_consecutive_failures = 0
_last_failure_time = 0.0
_MIN_COOLDOWN = 1.0  # seconds
_MAX_COOLDOWN = 8.0  # seconds
_JITTER_FACTOR = 0.5  # ±50% jitter


def _get_cooldown() -> float:
    """Calculate current cooldown with exponential backoff and jitter."""
    base = min(_MAX_COOLDOWN, _MIN_COOLDOWN * (2 ** (_consecutive_failures - 1)))
    jitter = base * _JITTER_FACTOR * (2 * random.random() - 1)
    return float(max(0, base + jitter))


def _is_in_cooldown() -> bool:
    """Check if circuit breaker is active (thread-safe)."""
    with _breaker_lock:
        if _consecutive_failures == 0:
            return False
        cooldown = _get_cooldown()
        return (time.time() - _last_failure_time) < cooldown


def _record_failure():
    """Record a connection failure (thread-safe)."""
    global _consecutive_failures, _last_failure_time
    with _breaker_lock:
        _consecutive_failures += 1
        _last_failure_time = time.time()
        cooldown = _get_cooldown()
        logger.warning(
            "ClickHouse circuit breaker: failure #%d, cooldown %.1fs",
            _consecutive_failures,
            cooldown,
        )


def _record_success():
    """Reset circuit breaker on successful connection (thread-safe)."""
    global _consecutive_failures, _last_failure_time
    with _breaker_lock:
        if _consecutive_failures > 0:
            logger.info(
                "ClickHouse circuit breaker: recovered after %d failures", _consecutive_failures
            )
            _consecutive_failures = 0
            _last_failure_time = 0.0


def get_client():
    """
    Get or create a thread-local ClickHouse client.

    Each thread gets its own client to avoid concurrent query errors.
    Uses circuit breaker with exponential backoff on connection failures.
    """
    # Return existing thread-local client if available
    client = getattr(_local, "client", None)
    if client is not None:
        return client

    # Circuit breaker check
    if _is_in_cooldown():
        from apps.shared.metrics import CLICKHOUSE_CIRCUIT_BREAKER_TRIPS

        CLICKHOUSE_CIRCUIT_BREAKER_TRIPS.inc()
        raise ClickHouseUnavailableError("ClickHouse unavailable (circuit breaker)")

    try:
        import clickhouse_connect

        client = clickhouse_connect.get_client(
            host=settings.CLICKHOUSE_HOST,
            port=settings.CLICKHOUSE_HTTP_PORT,
            database=settings.CLICKHOUSE_DATABASE,
            username=settings.CLICKHOUSE_USER,
            password=settings.CLICKHOUSE_PASSWORD,
            connect_timeout=3,
            send_receive_timeout=15,
        )
        _local.client = client
        _record_success()
        logger.info(
            "Connected to ClickHouse at %s:%s/%s",
            settings.CLICKHOUSE_HOST,
            settings.CLICKHOUSE_HTTP_PORT,
            settings.CLICKHOUSE_DATABASE,
        )
        return client
    except Exception as e:
        _record_failure()
        raise ClickHouseUnavailableError(str(e))


def query(sql, parameters=None):
    """
    Execute a read query and return results as a list of dicts.

    Args:
        sql: SQL query string with optional {name:Type} parameter placeholders.
        parameters: Dict of parameter values.

    Returns:
        List of dicts, one per row.
    """
    from apps.shared.metrics import CLICKHOUSE_QUERIES, CLICKHOUSE_QUERY_DURATION

    # Infer query type from SQL for metric labels
    sql_upper = (sql or "").strip().upper()
    query_type = "select" if sql_upper.startswith("SELECT") else "other"
    timer = CLICKHOUSE_QUERY_DURATION.labels(query_type=query_type).time()
    try:
        timer.__enter__()
        client = get_client()
        result = client.query(sql, parameters=parameters)
        columns = result.column_names
        rows = [dict(zip(columns, row)) for row in result.result_rows]
        timer.__exit__(None, None, None)
        CLICKHOUSE_QUERIES.labels(query_type=query_type, status="success").inc()
        return rows
    except ClickHouseUnavailableError:
        timer.__exit__(None, None, None)
        CLICKHOUSE_QUERIES.labels(query_type=query_type, status="circuit_breaker").inc()
        raise
    except Exception as e:
        # Reset thread-local client so next call reconnects (connection may be stale)
        _local.client = None
        _record_failure()
        # Include SQL (truncated) and params for debuggability
        sql_preview = (sql or "").strip()[:500]
        logger.error(
            "ClickHouse query failed: %s | SQL: %s | Params: %s",
            e,
            sql_preview,
            parameters,
        )
        timer.__exit__(None, None, None)
        CLICKHOUSE_QUERIES.labels(query_type=query_type, status="error").inc()
        # Report to Sentry (noop if not configured)
        try:
            import sentry_sdk

            sentry_sdk.capture_exception(e)
        except Exception:
            pass
        raise ClickHouseUnavailableError(str(e))


def query_scalar(sql, parameters=None):
    """Execute a query and return a single scalar value."""
    rows = query(sql, parameters=parameters)
    if rows and rows[0]:
        return list(rows[0].values())[0]
    return None


def health() -> dict:
    """Return circuit breaker state for health checks."""
    with _breaker_lock:
        if _consecutive_failures == 0:
            in_cooldown = False
        else:
            cooldown = _get_cooldown()
            in_cooldown = (time.time() - _last_failure_time) < cooldown
        return {
            "consecutive_failures": _consecutive_failures,
            "in_cooldown": in_cooldown,
            "last_failure": _last_failure_time,
        }


def clickhouse_fallback(fallback_fn=None):
    """
    Decorator for DRF view methods that depend on ClickHouse.

    On ClickHouseUnavailableError:
    - If fallback_fn is provided, calls fallback_fn(self, request, *args, **kwargs)
    - If fallback_fn also fails or is None, returns 503 with standard error body

    Usage:
        class StatsView(APIView):
            @clickhouse_fallback()
            def get(self, request): ...

        class IncidentListView(APIView):
            @clickhouse_fallback(fallback_fn=_incident_fallback)
            def get(self, request): ...
    """

    def decorator(method):
        @functools.wraps(method)
        def wrapper(self, request, *args, **kwargs):
            try:
                return method(self, request, *args, **kwargs)
            except ClickHouseUnavailableError:
                logger.warning(
                    "ClickHouse unavailable for %s %s",
                    request.method,
                    request.path,
                )
                if fallback_fn is not None:
                    try:
                        return fallback_fn(self, request, *args, **kwargs)
                    except Exception:
                        logger.exception(
                            "ClickHouse fallback also failed for %s %s",
                            request.method,
                            request.path,
                        )
                return Response(
                    {
                        "detail": "Analytics temporarily unavailable",
                        "code": "analytics_unavailable",
                    },
                    status=503,
                )

        return wrapper

    return decorator
