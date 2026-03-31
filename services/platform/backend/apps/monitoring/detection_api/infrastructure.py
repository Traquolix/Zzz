"""
Public infrastructure list and SHM status endpoints.
"""

import random

import numpy as np
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.monitoring.detection_serializers import (
    InfrastructureListResponseSerializer,
    InfrastructureStatusSerializer,
)
from apps.monitoring.models import Infrastructure
from apps.monitoring.shm_intelligence import compute_baseline, detect_frequency_shift

from .auth import IsAPIKeyUser, PublicAPIThrottle


class InfrastructureListAPIView(APIView):
    """GET /api/v1/infrastructure — list SHM infrastructure items for the org."""

    permission_classes = [IsAPIKeyUser]
    throttle_classes = [PublicAPIThrottle]

    @extend_schema(
        responses={200: InfrastructureListResponseSerializer},
        tags=["Infrastructure"],
        operation_id="listInfrastructure",
        summary="List infrastructure",
        description="List SHM infrastructure items (bridges, tunnels) for your organization.",
    )
    def get(self, request: Request) -> Response:
        org = request.user.organization
        items = Infrastructure.objects.filter(organization=org)

        data = [
            {
                "id": item.id,
                "type": item.type,
                "name": item.name,
                "fiberId": item.fiber_id,
                "direction": item.direction,
                "startChannel": item.start_channel,
                "endChannel": item.end_channel,
            }
            for item in items
        ]

        return Response({"data": data})


class InfrastructureStatusAPIView(APIView):
    """GET /api/v1/infrastructure/<id>/status — current SHM status for an item."""

    permission_classes = [IsAPIKeyUser]
    throttle_classes = [PublicAPIThrottle]

    @extend_schema(
        responses={200: InfrastructureStatusSerializer},
        tags=["Infrastructure"],
        operation_id="getInfrastructureStatus",
        summary="Infrastructure SHM status (demo)",
        description=(
            "Get the current structural health monitoring status for an infrastructure item.\n\n"
            "**Note:** This endpoint currently returns deterministic demo data for "
            "development and integration testing purposes. Real SHM data will be "
            "connected in a future release."
        ),
    )
    def get(self, request: Request, infra_id: str) -> Response:
        org = request.user.organization
        if not Infrastructure.objects.filter(id=infra_id, organization=org).exists():
            return Response(
                {"detail": "Infrastructure not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Deterministic demo data seeded by infra_id
        rng = random.Random(infra_id)
        baseline_freqs = np.array([1.10 + rng.gauss(0, 0.02) for _ in range(20)])
        baseline = compute_baseline(baseline_freqs)

        if baseline is None:
            return Response(
                {"detail": "Insufficient baseline data", "code": "insufficient_data"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        current_freqs = np.array([1.12 + rng.gauss(0, 0.03) for _ in range(10)])
        shift = detect_frequency_shift(baseline, current_freqs)

        status_map = {
            "normal": "nominal",
            "warning": "warning",
            "alert": "warning",
            "critical": "critical",
        }

        return Response(
            {
                "data": {
                    "status": status_map.get(shift.severity, "nominal"),
                    "currentMean": round(shift.current_mean, 4),
                    "baselineMean": round(shift.baseline_mean, 4),
                    "deviationSigma": round(shift.deviation_sigma, 2),
                    "direction": shift.direction,
                    "severity": shift.severity,
                },
                "demo": True,
            }
        )
