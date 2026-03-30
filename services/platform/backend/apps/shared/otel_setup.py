"""OpenTelemetry initialization for the Django backend.

Sets up traces, metrics, and log correlation. All three signals are
exported via OTLP to the otel-lgtm collector, which forwards them to
Tempo (traces), Prometheus (metrics), and Loki (logs).

Call ``init_otel()`` once at ASGI startup (before Django processes requests).
"""

import logging
import os

logger = logging.getLogger(__name__)

_HAS_OTEL = True
try:
    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.django import DjangoInstrumentor
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import DEPLOYMENT_ENVIRONMENT, SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
except ImportError:
    _HAS_OTEL = False


def init_otel() -> None:
    """Initialize OpenTelemetry tracing, metrics, and log correlation."""
    if not _HAS_OTEL:
        logger.warning("opentelemetry not installed — skipping OTel init (run `make setup` to fix)")
        return

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-lgtm:4317")
    otlp_insecure = os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() == "true"
    environment = os.getenv("ENVIRONMENT", "production")

    resource = Resource.create(
        {
            SERVICE_NAME: "sequoia-backend",
            DEPLOYMENT_ENVIRONMENT: environment,
        }
    )

    # Traces
    trace_provider = TracerProvider(resource=resource)
    trace_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=otlp_insecure)
    trace_provider.add_span_processor(
        BatchSpanProcessor(trace_exporter, max_queue_size=2048, schedule_delay_millis=5000)
    )
    trace.set_tracer_provider(trace_provider)

    # Metrics
    metric_exporter = OTLPMetricExporter(endpoint=otlp_endpoint, insecure=otlp_insecure)
    metric_reader = PeriodicExportingMetricReader(
        exporter=metric_exporter, export_interval_millis=10000
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # Auto-inject trace_id and span_id into every log record
    LoggingInstrumentor().instrument(set_logging_format=True)

    # Auto-create spans for Django request/response lifecycle
    DjangoInstrumentor().instrument()

    logger.info(
        "OpenTelemetry initialized",
        extra={"otlp_endpoint": otlp_endpoint, "environment": environment},
    )
