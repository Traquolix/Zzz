"""
Shared views: health checks.
"""

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as s
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    """Basic health check — returns 200 if the server is running."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []  # Exempt from rate limiting (used by Docker healthcheck)

    @extend_schema(
        responses={200: inline_serializer('HealthResponse', fields={
            'status': s.CharField(),
        })},
        tags=['health'],
    )
    def get(self, request):
        return Response({'status': 'ok'})


class ReadinessCheckView(APIView):
    """Readiness check — verifies database connectivity."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []  # Exempt from rate limiting

    @extend_schema(
        responses={200: inline_serializer('ReadinessResponse', fields={
            'status': s.CharField(),
        })},
        tags=['health'],
    )
    def get(self, request):
        from django.db import connection

        checks = {}

        # PostgreSQL
        try:
            connection.ensure_connection()
            checks['database'] = 'ok'
        except Exception:
            checks['database'] = 'unavailable'

        # ClickHouse
        try:
            from apps.shared.clickhouse import get_client
            client = get_client()
            client.query('SELECT 1')
            checks['clickhouse'] = 'ok'
        except Exception:
            checks['clickhouse'] = 'unavailable'

        all_ok = all(v == 'ok' for v in checks.values())
        return Response(
            {'status': 'ready' if all_ok else 'degraded', 'checks': checks},
            status=200 if all_ok else 503,
        )
