"""Pure OpenTelemetry metrics for pipeline services.

This module provides OTEL-only metrics (no local state, no locks).
All metrics are thread-safe by default via OTEL SDK.

Metrics exported:
- messages.processed.total (counter)
- messages.sent.total (counter)
- errors.total (counter)
- message.processing.duration (histogram)
- message.send.duration (histogram)
- kafka.consumer.lag (gauge)
- circuit_breaker.state (gauge)
- dlq.depth (gauge)
- buffer.active.count (gauge) - number of active buffers in BufferedTransformer
- buffer.evictions.total (counter) - LRU evictions when buffer limit reached
- buffer.size (histogram) - number of messages in buffer when processed

Query examples in Prometheus:
    # Throughput
    rate(messages_processed_total[1m])

    # p99 latency
    histogram_quantile(0.99, rate(message_processing_duration_bucket[1m]))

    # Consumer lag
    kafka_consumer_lag{service_name="processor"}

    # Buffer evictions (should be 0 under normal operation)
    rate(buffer_evictions_total{service_name="ai-engine"}[5m])

    # Active buffer count
    buffer_active_count{service_name="ai-engine"}
"""

import os

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import DEPLOYMENT_ENVIRONMENT, SERVICE_NAME, Resource


class MessageMetrics:
    """OTEL-based metrics for message processing.

    All metrics are thread-safe and automatically exported to OTEL collector.
    No local state, no locks, no manual aggregation.
    """

    def __init__(self, service_name: str = "unknown"):
        """Initialize OTEL metrics.

        Args:
            service_name: Name of the service for metric labeling
        """
        self.service_name = service_name

        # Get meter from global provider (set by otel_setup.py)
        # If not set, create a local provider (fallback)
        try:
            meter = metrics.get_meter(__name__)
        except Exception:
            # Fallback: create local provider
            self._setup_local_provider()
            meter = metrics.get_meter(__name__)

        # Counter: Total messages processed
        self.messages_processed_counter = meter.create_counter(
            name="messages.processed.total",
            description="Total number of messages processed",
            unit="1",
        )

        # Counter: Total messages sent
        self.messages_sent_counter = meter.create_counter(
            name="messages.sent.total", description="Total number of messages sent", unit="1"
        )

        # Counter: Total errors
        self.errors_counter = meter.create_counter(
            name="errors.total", description="Total number of errors", unit="1"
        )

        # Histogram: Message processing duration
        self.processing_duration_histogram = meter.create_histogram(
            name="message.processing.duration",
            description="Time spent processing messages",
            unit="s",
        )

        # Histogram: Message send duration
        self.send_duration_histogram = meter.create_histogram(
            name="message.send.duration", description="Time spent sending messages", unit="s"
        )

        # Gauge: Consumer lag (up-down counter acts as gauge)
        self.consumer_lag_gauge = meter.create_up_down_counter(
            name="kafka.consumer.lag",
            description="Number of messages behind in Kafka partition",
            unit="messages",
        )

        # Gauge: Circuit breaker state (0=closed, 1=half_open, 2=open)
        self.circuit_breaker_state_gauge = meter.create_up_down_counter(
            name="circuit_breaker.state", description="Circuit breaker state", unit="1"
        )

        # Gauge: DLQ depth
        self.dlq_depth_gauge = meter.create_up_down_counter(
            name="dlq.depth", description="Dead letter queue message count", unit="messages"
        )

        # Gauge: Active buffer count (for BufferedTransformer)
        self.buffer_active_count_gauge = meter.create_up_down_counter(
            name="buffer.active.count",
            description="Number of active message buffers",
            unit="buffers",
        )

        # Counter: Buffer evictions
        self.buffer_evictions_counter = meter.create_counter(
            name="buffer.evictions.total", description="Total number of buffer evictions", unit="1"
        )

        # Histogram: Buffer size when processed
        self.buffer_size_histogram = meter.create_histogram(
            name="buffer.size",
            description="Number of messages in buffer when processed",
            unit="messages",
        )

        # Track last lag values for gauge updates
        self._last_lag_values = {}
        self._last_buffer_count = 0

    def _setup_local_provider(self):
        """Setup local OTEL provider if global not configured."""
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-lgtm:4317")

        metric_exporter = OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True)

        metric_reader = PeriodicExportingMetricReader(
            exporter=metric_exporter, export_interval_millis=10000
        )

        resource = Resource.create(
            {
                SERVICE_NAME: self.service_name,
                DEPLOYMENT_ENVIRONMENT: os.getenv("ENVIRONMENT", "development"),
            }
        )

        provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(provider)

    def record_message_processed(self, processing_time: float, **labels):
        """Record a processed message.

        Args:
            processing_time: Time taken to process in seconds
            **labels: Additional labels (fiber_id, etc.)
        """
        attributes = {"service_name": self.service_name, **labels}
        self.messages_processed_counter.add(1, attributes)
        self.processing_duration_histogram.record(processing_time, attributes)

    def record_message_sent(self, send_time: float, **labels):
        """Record a sent message.

        Args:
            send_time: Time taken to send in seconds
            **labels: Additional labels (topic, etc.)
        """
        attributes = {"service_name": self.service_name, **labels}
        self.messages_sent_counter.add(1, attributes)
        self.send_duration_histogram.record(send_time, attributes)

    def record_error(self, error_type: str, **labels):
        """Record an error occurrence.

        Args:
            error_type: Type/category of error
            **labels: Additional labels
        """
        attributes = {"service_name": self.service_name, "error_type": error_type, **labels}
        self.errors_counter.add(1, attributes)

    def update_consumer_lag(self, topic: str, partition: int, lag: int):
        """Update consumer lag gauge.

        Since OTEL gauges are up-down counters, we need to calculate delta.

        Args:
            topic: Kafka topic name
            partition: Partition number
            lag: Current lag value
        """
        key = f"{topic}-{partition}"
        last_value = self._last_lag_values.get(key, 0)
        delta = lag - last_value

        attributes = {
            "service_name": self.service_name,
            "topic": topic,
            "partition": str(partition),
        }

        self.consumer_lag_gauge.add(delta, attributes)
        self._last_lag_values[key] = lag

    def update_circuit_breaker_state(self, breaker_name: str, state: str):
        """Update circuit breaker state.

        Args:
            breaker_name: Name of circuit breaker (consumer, producer)
            state: State string (closed, half_open, open)
        """
        # Map state to numeric value
        state_values = {"closed": 0, "half_open": 1, "open": 2}

        attributes = {"service_name": self.service_name, "breaker_name": breaker_name}

        # Set absolute value (OTEL SDK will handle changes)
        value = state_values.get(state, 0)
        self.circuit_breaker_state_gauge.add(value, attributes)

    def update_dlq_depth(self, depth: int):
        """Update dead letter queue depth.

        Args:
            depth: Current number of messages in DLQ
        """
        attributes = {"service_name": self.service_name}
        self.dlq_depth_gauge.add(depth, attributes)

    def update_buffer_count(self, count: int):
        """Update active buffer count gauge.

        Args:
            count: Current number of active buffers
        """
        delta = count - self._last_buffer_count
        attributes = {"service_name": self.service_name}
        self.buffer_active_count_gauge.add(delta, attributes)
        self._last_buffer_count = count

    def record_buffer_eviction(self, buffer_key: str):
        """Record a buffer eviction.

        Args:
            buffer_key: Key of the evicted buffer
        """
        attributes = {"service_name": self.service_name, "buffer_key": buffer_key}
        self.buffer_evictions_counter.add(1, attributes)

    def record_buffer_processed(self, buffer_size: int, buffer_key: str, partial: bool):
        """Record a processed buffer.

        Args:
            buffer_size: Number of messages in the buffer
            buffer_key: Key of the buffer
            partial: Whether this was a partial buffer (timeout/eviction)
        """
        attributes = {
            "service_name": self.service_name,
            "buffer_key": buffer_key,
            "partial": str(partial),
        }
        self.buffer_size_histogram.record(buffer_size, attributes)

    def get_lag_details(self) -> dict:
        """Get current lag values (for backward compatibility).

        Returns:
            Dict mapping topic-partition to lag value
        """
        return dict(self._last_lag_values)

    def get_summary(self) -> str:
        """Get a summary string of current metrics state.

        Returns:
            Summary string with lag information
        """
        lag_str = ", ".join(f"{k}={v}" for k, v in self._last_lag_values.items())
        return f"lag=[{lag_str}], buffers={self._last_buffer_count}"
