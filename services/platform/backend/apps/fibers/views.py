"""
Fiber data views — reads from PostgreSQL FiberCable model.

Data is org-scoped: non-superusers only see fibers assigned to their
organization via FiberAssignment. Superusers see all fibers.

Each physical cable is expanded into two directional fibers (direction 0 and 1)
before returning to the frontend, so that sections, landmarks, and interactions
are per-direction.
"""

import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.fibers.models import FiberCable
from apps.fibers.serializers import FiberLineSerializer
from apps.fibers.utils import get_org_fiber_ids
from apps.shared.permissions import IsActiveUser
from apps.shared.utils import build_org_cache_key

FIBERS_CACHE_TTL = 5 * 60  # 5 minutes


def add_cache_control(max_age: int = 300, public: bool = True) -> Callable[..., Any]:
    """Decorator to add Cache-Control headers to response."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(self: Any, request: Request, *args: Any, **kwargs: Any) -> Response:
            response = func(self, request, *args, **kwargs)
            cache_control_value = f"max-age={max_age}"
            if public:
                cache_control_value += ", public"
            response["Cache-Control"] = cache_control_value
            return response

        return wrapper

    return decorator


def _paginate(items: list) -> dict:
    """Wrap a list in the standard paginated envelope."""
    return {"results": items, "hasMore": False, "limit": len(items)}


logger = logging.getLogger("sequoia")


def _expand_to_directional(fiber: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand a single physical fiber into two directional fibers (direction 0 and 1).

    If `directional_paths` is provided in the fiber data with matching channel counts,
    those explicit coordinates are used. Otherwise, the frontend will compute
    perpendicular offsets from the base coordinates.
    """
    parent_id = fiber["id"]
    base_coords = fiber["coordinates"]
    directional_paths = fiber.get("directional_paths", {})
    result = []

    for direction in (0, 1):
        dir_key = str(direction)
        explicit_path = directional_paths.get(dir_key)

        # Use explicit path if provided and has matching channel count
        if explicit_path and len(explicit_path) == len(base_coords):
            coords = explicit_path
            coords_precomputed = True
        else:
            coords = base_coords
            coords_precomputed = False

        result.append(
            {
                "id": f"{parent_id}:{direction}",
                "parentFiberId": parent_id,
                "direction": direction,
                "name": fiber["name"],
                "color": fiber["color"],
                "coordinates": coords,
                "baseCoordinates": base_coords,
                "coordsPrecomputed": coords_precomputed,
                "landmarks": fiber.get("landmarks"),
                "dataCoverage": fiber.get("data_coverage", []),
            }
        )
    return result


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
            landmarks = []
            for idx, label in enumerate(cable.landmark_labels or []):
                if label:
                    landmarks.append({"channel": idx, "name": label})

            physical = {
                "id": cable.id,
                "name": cable.name,
                "color": cable.color,
                "coordinates": cable.coordinates,
                "directional_paths": cable.directional_paths or {},
                "landmarks": landmarks if landmarks else None,
                "data_coverage": cable.data_coverage or [],
            }
            fibers.extend(_expand_to_directional(physical))

        result = _paginate(fibers)
        cache.set(cache_key, result, FIBERS_CACHE_TTL)
        return Response(result)
