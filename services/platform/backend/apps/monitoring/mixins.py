"""
View mixins for the monitoring app.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from asgiref.sync import sync_to_async
from rest_framework.request import Request

logger = logging.getLogger("sequoia.monitoring.mixins")


class FlowAwareMixin:
    """
    Mixin for DRF views that need to distinguish between sim and live data flows.

    Parses the ``?flow=`` query parameter and provides helpers for
    routing to the correct data source.

    Strict isolation: ``flow=sim`` → simulation cache only,
    ``flow=live`` → ClickHouse only.  Data never crosses between flows.

    Usage::

        class MyView(FlowAwareMixin, APIView):
            def get(self, request):
                if self._is_sim(request):
                    return self._handle_sim(request)
                # ... ClickHouse path (live flow) ...
    """

    def _get_flow(self, request: Request) -> str:
        """Return the active flow for this request ('sim' or 'live')."""
        flow = request.query_params.get("flow", "sim")
        return flow if flow in ("sim", "live") else "sim"

    def _is_sim(self, request: Request) -> bool:
        """Return True if the client is on the simulation flow."""
        return self._get_flow(request) == "sim"

    def _get_sim_data(
        self,
        request: Request,
        sim_fn: Callable[[], list[dict[str, Any]]],
        fiber_key: str = "fiberId",
    ) -> list[dict[str, Any]]:
        """
        Get data from the simulation cache, org-filtered.

        Only call this when ``_is_sim(request)`` is True.
        Returns an empty list when the simulation is not running or has no data.

        Args:
            request: DRF request (used for user org-scoping).
            sim_fn: Callable that returns simulation data (e.g. get_simulation_incidents).
            fiber_key: Key in each item dict that holds the directional fiber ID.
        """
        try:
            data = sim_fn()
        except ImportError:
            return []

        if not data:
            return []

        # Org-scope: filter to user's assigned fibers
        if not request.user.is_superuser:
            from apps.fibers.utils import filter_by_org, get_org_fiber_ids

            fiber_ids = get_org_fiber_ids(request.user.organization)
            if not fiber_ids:
                return []
            data = filter_by_org(data, fiber_ids, fiber_key=fiber_key)

        return data

    async def _async_get_sim_data(
        self,
        request: Request,
        sim_fn: Callable[[], list[dict[str, Any]]],
        fiber_key: str = "fiberId",
    ) -> list[dict[str, Any]]:
        """Async version of _get_sim_data — wraps ORM call for async views."""
        try:
            data = sim_fn()
        except ImportError:
            return []

        if not data:
            return []

        if not request.user.is_superuser:
            from apps.fibers.utils import filter_by_org, get_org_fiber_ids

            fiber_ids = await sync_to_async(get_org_fiber_ids)(request.user.organization)
            if not fiber_ids:
                return []
            data = filter_by_org(data, fiber_ids, fiber_key=fiber_key)

        return data
