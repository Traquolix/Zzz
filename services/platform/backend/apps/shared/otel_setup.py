"""OpenTelemetry initialization for the Django backend.

Sets up trace export and log correlation so every log line includes
trace_id and span_id when an active span exists. Grafana Loki can
then link directly to the corresponding trace in Tempo.

Call ``init_otel()`` once at ASGI startup (before Django processes requests).
"""

import logging
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.resources import DEPLOYMENT_ENVIRONMENT, SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)


def init_otel() -> None:
    """Initialize OpenTelemetry tracing and log correlation."""
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-lgtm:4317")
    otlp_insecure = os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() == "true"
    environment = os.getenv("ENVIRONMENT", "production")

    resource = Resource.create(
        {
            SERVICE_NAME: "sequoia-backend",
            DEPLOYMENT_ENVIRONMENT: environment,
        }
    )

    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=otlp_insecure)
    provider.add_span_processor(
        BatchSpanProcessor(exporter, max_queue_size=2048, schedule_delay_millis=5000)
    )
    trace.set_tracer_provider(provider)

    # Auto-inject trace_id and span_id into every log record
    LoggingInstrumentor().instrument(set_logging_format=True)

    # Auto-create spans for Django request/response lifecycle
    DjangoInstrumentor().instrument()

    logger.info(
        "OpenTelemetry initialized",
        extra={"otlp_endpoint": otlp_endpoint, "environment": environment},
    )
