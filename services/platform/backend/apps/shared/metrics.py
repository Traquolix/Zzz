"""
OpenTelemetry metrics for the SequoIA platform.

All metrics are exported via OTLP to the otel-lgtm collector, which
forwards them to Prometheus. Histograms observed inside an active span
automatically carry trace exemplars for metric → trace drill-down in Grafana.

Metric names use dots (OTel convention); the collector maps them to
underscores for Prometheus compatibility.
"""

from opentelemetry import metrics

meter = metrics.get_meter("sequoia.backend")

# ---------- ClickHouse ----------

CLICKHOUSE_QUERIES = meter.create_counter(
    "sequoia.clickhouse.queries",
    description="Total ClickHouse queries executed",
)

CLICKHOUSE_QUERY_DURATION = meter.create_histogram(
    "sequoia.clickhouse.query.duration",
    unit="s",
    description="ClickHouse query latency",
)

CLICKHOUSE_CIRCUIT_BREAKER_TRIPS = meter.create_counter(
    "sequoia.clickhouse.circuit_breaker.trips",
    description="Times the ClickHouse circuit breaker tripped",
)

# ---------- Kafka ----------

KAFKA_MESSAGES_CONSUMED = meter.create_counter(
    "sequoia.kafka.messages.consumed",
    description="Messages consumed from Kafka",
)

KAFKA_DESERIALIZATION_ERRORS = meter.create_counter(
    "sequoia.kafka.deserialization.errors",
    description="Avro deserialization failures",
)

# ---------- WebSocket ----------

WEBSOCKET_CONNECTIONS = meter.create_up_down_counter(
    "sequoia.websocket.connections",
    description="Currently active WebSocket connections",
)

WEBSOCKET_MESSAGES_SENT = meter.create_counter(
    "sequoia.websocket.messages.sent",
    description="Messages sent to WebSocket clients",
)

WEBSOCKET_AUTH_FAILURES = meter.create_counter(
    "sequoia.websocket.auth.failures",
    description="WebSocket authentication failures",
)

WEBSOCKET_SEND_TIMEOUTS = meter.create_counter(
    "sequoia.websocket.send.timeouts",
    description="WebSocket send timeouts (slow clients)",
)

# ---------- Incidents ----------

INCIDENTS_ACTIVE = meter.create_up_down_counter(
    "sequoia.incidents.active",
    description="Currently active incidents",
)

# ---------- Replay Buffer ----------

REPLAY_BUFFER_SIZE = meter.create_up_down_counter(
    "sequoia.replay_buffer.items",
    description="Items currently queued in the replay buffer",
)

REPLAY_BUFFER_DELAY = meter.create_histogram(
    "sequoia.replay_buffer.delay",
    unit="s",
    description="Replay buffer scheduling delay (wall time - target time)",
)

# ---------- Redis Pub/Sub ----------

PUBSUB_MESSAGES_PUBLISHED = meter.create_counter(
    "sequoia.pubsub.messages.published",
    description="Messages published to Redis pub/sub",
)
