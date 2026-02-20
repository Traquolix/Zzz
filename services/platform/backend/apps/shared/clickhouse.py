"""
ClickHouse connection manager.

Provides thread-local clients for read-only queries to the ClickHouse
time-series database that stores pipeline data (speeds, counts, incidents).

Uses thread-local storage to avoid "concurrent queries within same session"
errors when the Kafka bridge and API requests run simultaneously.
"""

import logging
import threading
import time

from django.conf import settings

from apps.shared.exceptions import ClickHouseUnavailableError

logger = logging.getLogger('sequoia.clickhouse')

_local = threading.local()
_last_failure_time = 0.0
_failure_lock = threading.Lock()
_RETRY_COOLDOWN = 10.0  # seconds before retrying after a connection failure


def get_client():
    """
    Get or create a thread-local ClickHouse client.

    Each thread gets its own client to avoid concurrent query errors.
    Caches connection failures for _RETRY_COOLDOWN seconds to avoid
    blocking every request with a slow connection timeout when ClickHouse is down.
    """
    global _last_failure_time

    # Return existing thread-local client if available
    client = getattr(_local, 'client', None)
    if client is not None:
        return client

    # Don't retry if we failed recently (check is thread-safe via atomic read)
    now = time.time()
    if now - _last_failure_time < _RETRY_COOLDOWN:
        raise ClickHouseUnavailableError("ClickHouse unavailable (cooldown)")

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
        logger.info(
            "Connected to ClickHouse at %s:%s/%s",
            settings.CLICKHOUSE_HOST,
            settings.CLICKHOUSE_HTTP_PORT,
            settings.CLICKHOUSE_DATABASE,
        )
        return client
    except Exception as e:
        with _failure_lock:
            _last_failure_time = time.time()
        logger.error("Failed to connect to ClickHouse: %s", e)
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
    try:
        client = get_client()
        result = client.query(sql, parameters=parameters)
        columns = result.column_names
        return [dict(zip(columns, row)) for row in result.result_rows]
    except ClickHouseUnavailableError:
        raise
    except Exception as e:
        # Reset thread-local client so next call reconnects (connection may be stale)
        _local.client = None
        logger.error("ClickHouse query failed: %s", e)
        raise ClickHouseUnavailableError(str(e))


def query_scalar(sql, parameters=None):
    """Execute a query and return a single scalar value."""
    rows = query(sql, parameters=parameters)
    if rows and rows[0]:
        return list(rows[0].values())[0]
    return None
