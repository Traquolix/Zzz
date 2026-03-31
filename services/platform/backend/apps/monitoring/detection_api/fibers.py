"""
Public fiber list endpoint.
"""

from datetime import datetime, timedelta, timezone

from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.fibers.models import FiberCable
from apps.fibers.utils import get_org_fiber_ids
from apps.monitoring.detection_serializers import PublicFiberListResponseSerializer
from apps.monitoring.detection_utils import TIER_TABLES
from apps.shared.clickhouse import clickhouse_fallback, query

from .auth import IsAPIKeyUser, PublicAPIThrottle


class PublicFiberListView(APIView):
    """
    GET /api/v1/fibers — list fibers accessible to the API key's organization,
    with data availability metadata.

    Returns fiber IDs, names, directions, channel ranges, and the time range
    of available detection data per fiber.
    """

    permission_classes = [IsAPIKeyUser]
    throttle_classes = [PublicAPIThrottle]

    @extend_schema(
        responses={200: PublicFiberListResponseSerializer},
        tags=["Fibers"],
        operation_id="listFibers",
        summary="List accessible fibers",
        description=(
            "List fibers accessible to your API key's organization, with data "
            "availability metadata (earliest/latest timestamps, hires coverage)."
        ),
    )
    @clickhouse_fallback()
    def get(self, request: Request) -> Response:
        org = request.user.organization
        fiber_ids = get_org_fiber_ids(org)

        if not fiber_ids:
            return Response({"data": []})

        # Get fiber metadata from PostgreSQL
        cable_meta: dict[str, dict] = {}
        for cable in FiberCable.objects.filter(id__in=fiber_ids).order_by("id"):
            cable_meta[cable.id] = {
                "name": cable.name,
                "channel_count": cable.channel_count,
            }

        # Get data availability from detection_1h (permanent storage)
        avail_rows = query(
            f"""
            SELECT fiber_id,
                   min(ts) as earliest,
                   max(ts) as latest
            FROM {TIER_TABLES["1h"]}
            WHERE fiber_id IN {{fids:Array(String)}}
            GROUP BY fiber_id
            """,
            parameters={"fids": fiber_ids},
        )

        availability: dict[str, dict] = {}
        for row in avail_rows:
            availability[row["fiber_id"]] = {
                "earliest": row["earliest"],
                "latest": row["latest"],
            }

        # Build response — include all assigned fibers, even without cable metadata
        data = []
        for fid in sorted(fiber_ids):
            meta = cable_meta.get(fid, {})
            avail = availability.get(fid, {})
            ch_count = meta.get("channel_count", 0)

            data.append(
                {
                    "fiber_id": fid,
                    "name": meta.get("name", fid),
                    "directions": [0, 1],
                    "channel_range": [0, ch_count - 1] if ch_count > 0 else [0, 0],
                    "data_available": {
                        "earliest": avail.get("earliest"),
                        "latest": avail.get("latest"),
                        "hires_since": (
                            datetime.now(tz=timezone.utc) - timedelta(hours=48)
                        ).isoformat()
                        if avail
                        else None,
                    },
                }
            )

        return Response({"data": data})
