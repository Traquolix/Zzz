"""
Shared views: health checks and Prometheus metrics.
"""

from typing import Any

from django.http import HttpResponse
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as s
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    """Basic liveness check — returns 200 if the server is running."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes: list[Any] = []  # Exempt from rate limiting (used by Docker healthcheck)

    @extend_schema(
        responses={
            200: inline_serializer(
                "HealthResponse",
                fields={
                    "status": s.CharField(),
                },
            )
        },
        tags=["health"],
    )
    def get(self, request):
        return Response({"status": "ok"})


class ReadinessCheckView(APIView):
    """
    Readiness check — verifies all external dependencies.

    Returns 200 if all dependencies are healthy, 503 if any are degraded.
    Individual check statuses are always returned so the frontend can
    show specific degradation info.
    """

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes: list[Any] = []  # Exempt from rate limiting

    @extend_schema(
        responses={
            200: inline_serializer(
                "ReadinessResponse",
                fields={
                    "status": s.CharField(),
                },
            )
        },
        tags=["health"],
    )
    def get(self, request):
        from django.db import connection

        checks = {}

        # PostgreSQL
        try:
            connection.ensure_connection()
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "unavailable"

        # ClickHouse (uses circuit breaker state for fast response)
        try:
            from apps.shared.clickhouse import health as ch_health

            ch_state = ch_health()
            if ch_state["in_cooldown"]:
                checks["clickhouse"] = "unavailable"
            else:
                from apps.shared.clickhouse import get_client

                client = get_client()
                client.query("SELECT 1")
                checks["clickhouse"] = "ok"
        except Exception:
            checks["clickhouse"] = "unavailable"

        # Redis (used for Channels and caching)
        try:
            from django.core.cache import cache

            cache.set("__health_check", "1", 5)
            val = cache.get("__health_check")
            checks["cache"] = "ok" if val == "1" else "unavailable"
        except Exception:
            checks["cache"] = "unavailable"

        # Kafka (check if bootstrap servers are reachable)
        try:
            from django.conf import settings as django_settings

            bootstrap = getattr(django_settings, "KAFKA_BOOTSTRAP_SERVERS", None)
            if bootstrap:
                import socket

                host, _, port = bootstrap.partition(":")
                port = int(port) if port else 9092
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                sock.connect((host, port))
                sock.close()
                checks["kafka"] = "ok"
            else:
                checks["kafka"] = "not_configured"
        except Exception:
            checks["kafka"] = "unavailable"

        # Simulation status (informational, not blocking)
        try:
            from apps.realtime.simulation_manager import SimulationManager

            sim = SimulationManager.instance().health()
            checks["simulation"] = sim["status"]
        except Exception:
            checks["simulation"] = "unknown"

        # Overall status: degraded if any critical service is down
        critical_services = ["database", "clickhouse", "cache", "kafka"]
        all_critical_ok = all(checks.get(svc) == "ok" for svc in critical_services)

        return Response(
            {
                "status": "ready" if all_critical_ok else "degraded",
                "checks": checks,
            },
            status=200 if all_critical_ok else 503,
        )


class MetricsView(APIView):
    """Prometheus metrics endpoint — scraped by monitoring infrastructure."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes: list[Any] = []

    @extend_schema(exclude=True)  # Not part of the public API docs
    def get(self, request):
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

        # Import metrics module to ensure all collectors are registered
        import apps.shared.metrics  # noqa: F401

        body = generate_latest()
        return HttpResponse(body, content_type=CONTENT_TYPE_LATEST)
