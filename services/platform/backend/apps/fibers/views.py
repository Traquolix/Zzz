"""
Fiber data views — reads from PostgreSQL FiberCable model.

Data is org-scoped: non-superusers only see fibers assigned to their
organization via FiberAssignment. Superusers see all fibers.

Each physical cable is expanded into two directional fibers (direction 0 and 1)
before returning to the frontend, so that sections, landmarks, and interactions
are per-direction.
"""

import logging

from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.fibers.models import FiberCable
from apps.fibers.serializers import FiberLineSerializer
from apps.fibers.utils import cable_to_physical_dict, expand_to_directional, get_org_fiber_ids
from apps.shared.permissions import IsActiveUser
from apps.shared.utils import add_cache_control, build_org_cache_key

FIBERS_CACHE_TTL = 5 * 60  # 5 minutes


def _paginate(items: list) -> dict:
    """Wrap a list in the standard paginated envelope."""
    return {"results": items, "hasMore": False, "limit": len(items)}


logger = logging.getLogger("sequoia")


class FiberListView(APIView):
    """
    GET /api/fibers — returns fiber cables with coordinates.

    Org-scoped: returns only fibers assigned to the user's organization.
    Superusers see all fibers.
    Each physical cable is expanded into two directional fibers.
    """

    permission_classes = [IsActiveUser]

    @add_cache_control(max_age=300, public=True)
    @extend_schema(
        responses={200: FiberLineSerializer(many=True)},
        tags=["fibers"],
    )
    def get(self, request: Request) -> Response:
        cache_key = build_org_cache_key("fibers", request.user)

        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        # Determine allowed fiber IDs
        if not request.user.is_superuser:
            fiber_ids = get_org_fiber_ids(request.user.organization)
            if not fiber_ids:
                result = _paginate([])
                cache.set(cache_key, result, FIBERS_CACHE_TTL)
                return Response(result)
        else:
            fiber_ids = None  # no filter

        queryset = FiberCable.objects.all()
        if fiber_ids is not None:
            queryset = queryset.filter(id__in=fiber_ids)

        fibers = []
        for cable in queryset:
            fibers.extend(expand_to_directional(cable_to_physical_dict(cable)))

        result = _paginate(fibers)
        cache.set(cache_key, result, FIBERS_CACHE_TTL)
        return Response(result)
