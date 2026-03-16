"""
Fiber data views — reads from ClickHouse fiber_cables table.

Falls back to JSON cable files when ClickHouse is unavailable
(e.g. during local development or simulation-only demo).

Data is org-scoped: non-superusers only see fibers assigned to their
organization via FiberAssignment. Superusers see all fibers.

Each physical cable is expanded into two directional fibers (direction 0 and 1)
before returning to the frontend, so that sections, landmarks, and interactions
are per-direction.
"""

import json
import logging
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.fibers.serializers import FiberLineSerializer
from apps.fibers.utils import get_org_fiber_ids
from apps.shared.clickhouse import get_client
from apps.shared.exceptions import ClickHouseUnavailableError
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

_CABLE_FILES = [
    "carros.json",
    "promenade.json",
    "mathis.json",
]


def _get_cables_dir() -> Path:
    return Path(settings.DATA_DIR / "clickhouse" / "cables")


def _load_directional_paths() -> dict[str, dict]:
    """Load directional_paths from JSON cable files.

    Returns {fiber_id: {"0": [...], "1": [...]}}.
    Cached in Django cache so we don't re-read files on every request.
    """
    cache_key = "fibers:directional_paths"
    cached: dict[str, dict] | None = cache.get(cache_key)
    if cached is not None:
        return cached

    cables_dir = _get_cables_dir()
    result = {}
    for cable_file in _CABLE_FILES:
        path = cables_dir / cable_file
        if not path.exists():
            continue
        with open(path) as f:
            data = json.load(f)
        dp = data.get("directional_paths", {})
        if dp:
            result[data["id"]] = dp

    cache.set(cache_key, result, FIBERS_CACHE_TTL)
    return result


def _expand_to_directional(fiber: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand a single physical fiber into two directional fibers (direction 0 and 1).

    If `directional_paths` is provided in the fiber data with matching channel counts,
    those explicit coordinates are used. Otherwise, the frontend will compute
    perpendicular offsets from the base coordinates.

    Expected structure for explicit paths:
        "directional_paths": {
            "0": [[lng, lat], ...],  // path for direction 0
            "1": [[lng, lat], ...]   // path for direction 1
        }
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
                "baseCoordinates": base_coords,  # Original fiber center-line (for CableLayer)
                "coordsPrecomputed": coords_precomputed,  # True = don't apply offset on frontend
                "landmarks": fiber.get("landmarks"),
            }
        )
    return result


def _load_fibers_from_json(fiber_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """Load fiber data from JSON cable files (fallback when ClickHouse is unavailable).

    Returns directional fibers (two per physical cable).
    """
    cables_dir = _get_cables_dir()
    fibers = []

    for cable_file in _CABLE_FILES:
        path = cables_dir / cable_file
        if not path.exists():
            continue

        with open(path) as f:
            data = json.load(f)

        fid = data["id"]
        if fiber_ids is not None and fid not in fiber_ids:
            continue

        # Include all coordinates (valid + null) to preserve channel indexing.
        physical = {
            "id": fid,
            "name": data.get("name", fid),
            "color": data.get("color", "#888888"),
            "coordinates": data.get("coordinates", []),
            "directional_paths": data.get("directional_paths", {}),
            "landmarks": None,
        }
        fibers.extend(_expand_to_directional(physical))

    logger.info(
        "Loaded %d directional fibers from JSON fallback (ClickHouse unavailable)", len(fibers)
    )
    return fibers


class FiberListView(APIView):
    """
    GET /api/fibers — returns fiber cables with coordinates.

    Org-scoped: returns only fibers assigned to the user's organization.
    Superusers see all fibers.
    Falls back to JSON cable files when ClickHouse is unavailable.
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

        try:
            client = get_client()
        except ClickHouseUnavailableError:
            fibers = _load_fibers_from_json(fiber_ids)
            result = _paginate(fibers)
            cache.set(cache_key, result, FIBERS_CACHE_TTL)
            return Response(result)

        try:
            if fiber_ids is not None:
                result = client.query(
                    """
                    SELECT
                        fiber_id,
                        fiber_name,
                        channel_coordinates,
                        color,
                        landmark_labels
                    FROM sequoia.fiber_cables
                    WHERE fiber_id IN {fids:Array(String)}
                    ORDER BY fiber_id
                    """,
                    parameters={"fids": fiber_ids},
                )
            else:
                result = client.query("""
                    SELECT
                        fiber_id,
                        fiber_name,
                        channel_coordinates,
                        color,
                        landmark_labels
                    FROM sequoia.fiber_cables
                    ORDER BY fiber_id
                """)

            dir_paths_map = _load_directional_paths()

            fibers = []
            for row in result.named_results():  # type: ignore[attr-defined]
                coords = []
                for coord in row["channel_coordinates"]:
                    lng, lat = coord
                    if lng is not None and lat is not None:
                        coords.append([lng, lat])
                    else:
                        coords.append([None, None])

                landmarks = []
                for idx, label in enumerate(row["landmark_labels"] or []):
                    if label:
                        landmarks.append({"channel": idx, "name": label})

                physical = {
                    "id": row["fiber_id"],
                    "name": row["fiber_name"],
                    "color": row["color"],
                    "coordinates": coords,
                    "directional_paths": dir_paths_map.get(row["fiber_id"], {}),
                    "landmarks": landmarks if landmarks else None,
                }
                fibers.extend(_expand_to_directional(physical))

            result = _paginate(fibers)
            cache.set(cache_key, result, FIBERS_CACHE_TTL)
            return Response(result)

        except Exception as e:
            logger.error("Failed to query fibers from ClickHouse: %s", e)
            fibers = _load_fibers_from_json(fiber_ids)
            result = _paginate(fibers)
            cache.set(cache_key, result, FIBERS_CACHE_TTL)
            return Response(result)
