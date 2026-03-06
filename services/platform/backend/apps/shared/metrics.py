"""
Prometheus metrics for SequoIA platform.

Exposes counters, histograms, and gauges for critical data paths:
  - ClickHouse query performance and failures
  - Kafka message consumption
  - WebSocket connection lifecycle
  - API request latencies
  - Incident counts

Metrics are collected by prometheus_client's default registry and
exposed via the /metrics endpoint (MetricsView).
"""

from prometheus_client import Counter, Gauge, Histogram

# ---------- ClickHouse ----------

CLICKHOUSE_QUERIES = Counter(
    "sequoia_clickhouse_queries_total",
    "Total ClickHouse queries executed",
    ["query_type", "status"],  # status: success, error, circuit_breaker
)

CLICKHOUSE_QUERY_DURATION = Histogram(
    "sequoia_clickhouse_query_duration_seconds",
    "ClickHouse query latency",
    ["query_type"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 15.0),
)

CLICKHOUSE_CIRCUIT_BREAKER_TRIPS = Counter(
    "sequoia_clickhouse_circuit_breaker_trips_total",
    "Times the ClickHouse circuit breaker tripped",
)

# ---------- Kafka ----------

KAFKA_MESSAGES_CONSUMED = Counter(
    "sequoia_kafka_messages_consumed_total",
    "Messages consumed from Kafka",
    ["topic"],
)

KAFKA_CONSUMER_LAG = Gauge(
    "sequoia_kafka_consumer_lag_seconds",
    "Estimated consumer lag from message timestamp to processing time",
    ["topic"],
)

KAFKA_DESERIALIZATION_ERRORS = Counter(
    "sequoia_kafka_deserialization_errors_total",
    "Avro deserialization failures",
    ["topic"],
)

# ---------- WebSocket ----------

WEBSOCKET_CONNECTIONS = Gauge(
    "sequoia_websocket_connections_active",
    "Currently active WebSocket connections",
)

WEBSOCKET_MESSAGES_SENT = Counter(
    "sequoia_websocket_messages_sent_total",
    "Messages sent to WebSocket clients",
    ["channel"],
)

WEBSOCKET_AUTH_FAILURES = Counter(
    "sequoia_websocket_auth_failures_total",
    "WebSocket authentication failures",
)

WEBSOCKET_SEND_TIMEOUTS = Counter(
    "sequoia_websocket_send_timeouts_total",
    "WebSocket send timeouts (slow clients)",
)

# ---------- Incidents ----------

INCIDENTS_ACTIVE = Gauge(
    "sequoia_incidents_active",
    "Currently active incidents",
)

# ---------- Replay Buffer ----------

REPLAY_BUFFER_SIZE = Gauge(
    "sequoia_replay_buffer_items",
    "Items currently queued in the replay buffer",
)

REPLAY_BUFFER_DELAY = Histogram(
    "sequoia_replay_buffer_delay_seconds",
    "Replay buffer scheduling delay (wall time - target time)",
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0),
)
