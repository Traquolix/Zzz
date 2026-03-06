"""Centralized OpenTelemetry setup for all pipeline services.

This module provides a single point of configuration for OTEL traces, metrics,
and logs. All services should call setup_otel() at startup.

Correlation ID Strategy:
- Generated per message in Generator: {fiber_id}_{timestamp_seconds}
- Propagated via baggage (automatic through trace context)
- Added as span attribute for querying in Tempo

Example usage:
    from shared.otel_setup import setup_otel, tracer, create_correlation_id

    # At service startup
    setup_otel("my-service")

    # In message processing
    with tracer.start_as_current_span("operation") as span:
        correlation_id = create_correlation_id("fiber_id")
        set_correlation_id(correlation_id)
        span.set_attribute("correlation_id", correlation_id)
"""

import logging
import os
import time
from typing import Optional

from opentelemetry import metrics, trace
from opentelemetry.baggage import get_baggage, set_baggage
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.b3 import B3MultiFormat
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import (
    DEPLOYMENT_ENVIRONMENT,
    SERVICE_NAME,
    SERVICE_VERSION,
    Resource,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

logger = logging.getLogger(__name__)

# Global tracer instance (set by setup_otel)
tracer: Optional[trace.Tracer] = None


class CorrelationFilter(logging.Filter):
    """Add correlation_id to all log records."""

    def filter(self, record):
        """Inject correlation_id from baggage into log record."""
        record.correlation_id = get_baggage("correlation_id") or "unknown"
        return True


def setup_otel(service_name: str, service_version: str = "1.0.0") -> None:
    """Initialize OpenTelemetry for a service.

    Sets up:
    - Trace export to OTEL collector (OTLP/gRPC)
    - Metrics export to OTEL collector
    - Structured logging with trace correlation
    - Resource attributes (service.name, deployment.environment)
    - Baggage propagation for correlation IDs

    Args:
        service_name: Name of the service (e.g., "generator", "processor")
        service_version: Version string for the service

    Environment Variables:
        LOG_LEVEL: Logging level - DEBUG, INFO, WARNING, ERROR (default: INFO)
        OTEL_EXPORTER_OTLP_ENDPOINT: OTEL collector endpoint (default: http://otel-lgtm:4317)
        OTEL_EXPORTER_OTLP_INSECURE: Use insecure connection (default: true). Set to "false" for TLS in production.
        ENVIRONMENT: Deployment environment (default: development)
    """
    global tracer

    # Get configuration from environment
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-lgtm:4317")
    otlp_insecure = os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() == "true"
    environment = os.getenv("ENVIRONMENT", "development")

    # Create resource with service metadata
    resource = Resource.create(
        {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
            DEPLOYMENT_ENVIRONMENT: environment,
            "service.instance.id": f"{service_name}-{os.getpid()}",
        }
    )

    # Setup trace provider
    trace_provider = TracerProvider(resource=resource)

    # Configure OTLP span exporter
    span_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=otlp_insecure)

    # Use batch processor for better performance
    span_processor = BatchSpanProcessor(
        span_exporter,
        max_queue_size=2048,
        max_export_batch_size=512,
        schedule_delay_millis=5000,  # Export every 5 seconds
    )
    trace_provider.add_span_processor(span_processor)

    # Set as global trace provider
    trace.set_tracer_provider(trace_provider)

    # Setup metrics provider
    metric_exporter = OTLPMetricExporter(endpoint=otlp_endpoint, insecure=otlp_insecure)

    metric_reader = PeriodicExportingMetricReader(
        exporter=metric_exporter,
        export_interval_millis=10000,  # Export every 10 seconds
    )

    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # Setup context propagation (trace context + baggage for correlation IDs)
    set_global_textmap(
        CompositePropagator(
            [
                TraceContextTextMapPropagator(),  # W3C trace context
                W3CBaggagePropagator(),  # W3C baggage (for correlation_id)
                B3MultiFormat(),  # Zipkin B3 (compatibility)
            ]
        )
    )

    # Configure log level from environment (default: INFO)
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.getLogger().setLevel(getattr(logging, log_level, logging.INFO))

    # Setup logging instrumentation (adds trace_id, span_id to logs)
    LoggingInstrumentor().instrument(set_logging_format=True)

    # Add correlation ID filter to all log handlers
    correlation_filter = CorrelationFilter()
    for handler in logging.root.handlers:
        handler.addFilter(correlation_filter)

    # Get tracer instance
    tracer = trace.get_tracer(__name__)

    logger.info(
        f"OpenTelemetry initialized for {service_name}",
        extra={
            "otlp_endpoint": otlp_endpoint,
            "environment": environment,
            "service_version": service_version,
        },
    )


def create_correlation_id(fiber_id: str) -> str:
    """Generate correlation ID for a message batch.

    Format: {fiber_id}_{timestamp_seconds}

    This allows querying all traces for a time window:
    - Single fiber: { resource.correlation_id = "carros_1701234567" }
    - Time range: { resource.correlation_id =~ "carros_170123.*" }

    Args:
        fiber_id: Fiber identifier (e.g., "carros")

    Returns:
        Correlation ID string
    """
    timestamp = int(time.time())
    return f"{fiber_id}_{timestamp}"


def set_correlation_id(correlation_id: str) -> None:
    """Set correlation ID in baggage for automatic propagation.

    The correlation ID will be:
    - Propagated via Kafka message headers automatically
    - Available in all downstream services via get_baggage()
    - Included in trace context propagation

    Args:
        correlation_id: Correlation ID to set
    """
    set_baggage("correlation_id", correlation_id)


def get_correlation_id() -> Optional[str]:
    """Get current correlation ID from baggage.

    Returns:
        Current correlation ID or None if not set
    """
    return get_baggage("correlation_id")


def add_correlation_to_span(span: trace.Span) -> None:
    """Add correlation ID as span attribute for querying.

    This makes the correlation ID queryable in Tempo via TraceQL:
        { resource.correlation_id = "carros_1701234567" }

    Args:
        span: Current span to annotate
    """
    correlation_id = get_correlation_id()
    if correlation_id:
        span.set_attribute("correlation_id", correlation_id)
