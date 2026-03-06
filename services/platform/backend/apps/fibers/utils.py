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
    result = cache.get(cache_key)
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
    result = cache.get(cache_key)
    if result is not None:
        return result

    from apps.fibers.models import FiberAssignment

    mapping: dict[str, list[str]] = {}
    for fiber_id, org_id in FiberAssignment.objects.values_list("fiber_id", "organization_id"):
        org_id_str = str(org_id)
        mapping.setdefault(fiber_id, []).append(org_id_str)

    cache.set(cache_key, mapping, _FIBER_MAP_TTL)
    return mapping


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
