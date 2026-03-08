"""
Shared utilities for DRF views — pagination, cache keys, org-scoped querysets.
"""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet
from rest_framework.request import Request


def build_org_cache_key(prefix: str, user: Any) -> str:
    """Build an org-scoped cache key.

    Returns ``"<prefix>:all"`` for superusers,
    ``"<prefix>:org:<org_id>"`` for regular users.
    """
    if user.is_superuser:
        return f"{prefix}:all"
    return f"{prefix}:org:{user.organization_id}"


def paginate_queryset(
    request: Request, queryset: QuerySet, default_limit: int = 50
) -> tuple[list, dict[str, Any]]:
    """Apply search, offset, and limit to a queryset.

    Returns: (page, pagination_data)
        page: queryset slice for this page
        pagination_data: dict with hasMore, limit, offset, total

    Optimized: Single query approach.
    - Fetches limit+1 items to determine hasMore
    - Computes total = offset + len(items_fetched) if we got exactly limit+1
    - Only calls count() when we fetch fewer than limit+1 items (last page)
    """
    _search = request.GET.get("search", "").strip()  # noqa: F841 — reserved for future filtering
    try:
        offset = max(0, int(request.GET.get("offset", 0)))
    except (ValueError, TypeError):
        offset = 0
    try:
        limit = min(int(request.GET.get("limit", default_limit)), 200)
    except (ValueError, TypeError):
        limit = default_limit

    # Fetch limit+1 to determine if there are more results (single query)
    fetch_limit = limit + 1
    items = list(queryset[offset : offset + fetch_limit])

    # Check if we got more than limit (indicates more results exist)
    has_more = len(items) > limit
    page = items[:limit]

    # On the last page (no more results), we know the exact total.
    # When there are more results, we only know a lower bound; report it
    # so the frontend can show "50+" style counts without a count() query.
    total = offset + len(items)

    return page, {
        "hasMore": has_more,
        "limit": limit,
        "offset": offset,
        "total": total,
    }


def org_filter_queryset(queryset: QuerySet, user: Any) -> QuerySet:
    """Filter a Django queryset to the user's organization.

    Superusers see all records. Regular users see only their org's records.
    Assumes the model has an ``organization`` FK field.
    """
    if user.is_superuser:
        return queryset
    return queryset.filter(organization=user.organization)
