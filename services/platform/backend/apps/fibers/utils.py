"""
Fiber-to-organization mapping utilities with caching.

These functions are the single source of truth for "which fibers belong
to which org" across REST views, WebSocket consumers, and broadcast logic.
"""

import logging

from django.core.cache import cache

logger = logging.getLogger("sequoia.fibers")

# Cache TTLs
_ORG_FIBER_TTL = 300  # 5 minutes
_FIBER_MAP_TTL = 300


def get_org_fiber_ids(organization) -> list[str]:
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
    fiber_key: str = "fiberLine",
) -> list[dict]:
    """Filter a list of dicts to only items whose fiber belongs to the given org.

    Strips the directional suffix (e.g. ``"carros:0"`` → ``"carros"``) before
    matching against ``fiber_ids`` from ``FiberAssignment``.

    Args:
        items: List of dicts, each containing a fiber identifier.
        fiber_ids: Allowed fiber IDs for the user's org (from ``get_org_fiber_ids``).
        fiber_key: Key in each dict that holds the directional fiber ID.
    """
    from apps.monitoring.incident_service import strip_directional_suffix

    allowed = set(fiber_ids)
    return [item for item in items if strip_directional_suffix(item.get(fiber_key, "")) in allowed]


def fiber_belongs_to_org(fiber_id: str, fiber_ids: list[str]) -> bool:
    """Check if a single fiber ID belongs to the given org's fiber set.

    Strips the directional suffix before matching.

    Args:
        fiber_id: Directional fiber ID (e.g. ``"carros:0"``).
        fiber_ids: Allowed fiber IDs for the user's org.
    """
    from apps.monitoring.incident_service import strip_directional_suffix

    return strip_directional_suffix(fiber_id) in set(fiber_ids)


def invalidate_org_fiber_cache(org_id):
    """Invalidate all fiber caches related to an org after admin changes."""
    cache.delete(f"org_fibers:{org_id}")
    # Also invalidate view-level fiber caches
    cache.delete(f"fibers:org:{org_id}")
    cache.delete("fibers:all")  # superuser cache
    logger.debug("Invalidated org fiber cache for %s", org_id)


def invalidate_fiber_org_map():
    """Invalidate the global fiber→org mapping cache."""
    cache.delete("fiber_org_map")
    logger.debug("Invalidated fiber_org_map cache")
