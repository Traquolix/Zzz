"""
Fiber-to-organization mapping utilities with caching.

These functions are the single source of truth for "which fibers belong
to which org" across REST views, WebSocket consumers, and broadcast logic.
"""

import logging
from typing import Any

from django.core.cache import cache

logger = logging.getLogger("sequoia.fibers.utils")

# Cache TTLs
_ORG_FIBER_TTL = 300  # 5 minutes
_FIBER_MAP_TTL = 300


def get_org_fiber_ids(organization: Any) -> list[str]:
    """Return list of fiber_ids assigned to an organization (cached 5min)."""
    cache_key = f"org_fibers:{organization.pk}"
    result: list[str] | None = cache.get(cache_key)
    if result is not None:
        return result

    from apps.fibers.models import FiberAssignment

    fiber_ids = list(
        FiberAssignment.objects.filter(organization=organization).values_list("fiber_id", flat=True)
    )
    cache.set(cache_key, fiber_ids, _ORG_FIBER_TTL)
    return fiber_ids


def get_fiber_org_map() -> dict[str, list[str]]:
    """Return {fiber_id: [org_id, ...]} mapping (cached 5min).

    Used by simulation/kafka_bridge to route broadcasts to the correct
    org-scoped Channels groups.
    """
    cache_key = "fiber_org_map"
    result: dict[str, list[str]] | None = cache.get(cache_key)
    if result is not None:
        return result

    from apps.fibers.models import FiberAssignment

    mapping: dict[str, list[str]] = {}
    for fiber_id, org_id in FiberAssignment.objects.values_list("fiber_id", "organization_id"):
        org_id_str = str(org_id)
        mapping.setdefault(fiber_id, []).append(org_id_str)

    cache.set(cache_key, mapping, _FIBER_MAP_TTL)
    return mapping


def filter_by_org(
    items: list[dict],
    fiber_ids: list[str],
    fiber_key: str = "fiberId",
) -> list[dict]:
    """Filter a list of dicts to only items whose fiber belongs to the given org.

    Args:
        items: List of dicts, each containing a ``fiberId`` field.
        fiber_ids: Allowed fiber IDs for the user's org (from ``get_org_fiber_ids``).
        fiber_key: Key in each item dict that holds the plain fiber ID.
    """
    allowed = set(fiber_ids)
    return [item for item in items if item.get(fiber_key, "") in allowed]


def fiber_belongs_to_org(fiber_id: str, fiber_ids: list[str]) -> bool:
    """Check if a fiber ID belongs to the given org's fiber set.

    Args:
        fiber_id: Plain fiber ID (e.g. ``"carros"``).
        fiber_ids: Allowed fiber IDs for the user's org.
    """
    return fiber_id in set(fiber_ids)


def invalidate_org_fiber_cache(org_id: Any) -> None:
    """Invalidate all fiber caches related to an org after admin changes."""
    cache.delete(f"org_fibers:{org_id}")
    # Also invalidate view-level fiber caches
    cache.delete(f"fibers:org:{org_id}")
    cache.delete("fibers:all")  # superuser cache
    logger.debug("Invalidated org fiber cache for %s", org_id)


def invalidate_fiber_org_map() -> None:
    """Invalidate the global fiber→org mapping cache."""
    cache.delete("fiber_org_map")
    logger.debug("Invalidated fiber_org_map cache")


def expand_to_directional(fiber: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand a single physical fiber into two directional fibers (direction 0 and 1).

    If ``directional_paths`` is provided in the fiber data with matching channel counts,
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


def cable_to_physical_dict(cable: Any) -> dict[str, Any]:
    """Convert a FiberCable model instance to the physical dict used by views and consumers.

    The returned dict is the input for ``expand_to_directional`` which splits
    a physical cable into two directional fibers.
    """
    landmarks = []
    for idx, label in enumerate(cable.landmark_labels or []):
        if label:
            landmarks.append({"channel": idx, "name": label})

    return {
        "id": cable.id,
        "name": cable.name,
        "color": cable.color,
        "coordinates": cable.coordinates,
        "directional_paths": cable.directional_paths or {},
        "landmarks": landmarks or None,
        "data_coverage": cable.data_coverage or [],
    }
