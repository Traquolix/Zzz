"""
Shared helpers for monitoring views.

Extracted from views.py so that the focused sub-modules can import them
without creating circular dependencies.
"""

import time
from typing import Any

from asgiref.sync import sync_to_async
from rest_framework import status
from rest_framework.response import Response

from apps.fibers.utils import get_org_fiber_ids
from apps.monitoring.models import Infrastructure

_PROCESS_START_TIME = time.time()

INCIDENTS_CACHE_TTL = 10  # 10 seconds
STATS_CACHE_TTL = 5  # 5 seconds


def _get_fiber_ids_or_none(user: Any) -> list[str] | None:
    """Return fiber_ids list for org-scoped users, None for superusers."""
    if user.is_superuser:
        return None
    return get_org_fiber_ids(user.organization)


async def _async_get_fiber_ids_or_none(user: Any) -> list[str] | None:
    """Async version — wraps ORM call for use in async views."""
    if user.is_superuser:
        return None
    return await sync_to_async(get_org_fiber_ids)(user.organization)


def _verify_infrastructure_access(user: Any, infrastructure_id: str | None) -> Response | None:
    """Verify the user's org owns the infrastructure. Returns error Response or None."""
    if not infrastructure_id or user.is_superuser:
        return None
    if not Infrastructure.objects.filter(
        id=infrastructure_id,
        organization=user.organization,
    ).exists():
        return Response(
            {"detail": "Infrastructure not found", "code": "not_found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    return None
