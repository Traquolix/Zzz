"""
View mixins for the monitoring app.
"""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger("sequoia")


class FlowAwareMixin:
    """
    Mixin for DRF views that need to distinguish between sim and live data flows.

    Parses the ``?flow=`` query parameter and provides helpers for
    simulation fallback logic.

    Usage::

        class MyView(FlowAwareMixin, APIView):
            def get(self, request):
                # Try simulation first (skipped when flow=live)
                sim_data = self.get_sim_fallback(
                    request, get_simulation_data, fiber_key="fiberLine"
                )
                if sim_data is not None:
                    return Response(sim_data)
                # ... ClickHouse path ...
    """

    def _get_flow(self, request) -> str:
        """Return the active flow for this request ('sim' or 'live')."""
        flow = request.query_params.get("flow", "sim")
        return flow if flow in ("sim", "live") else "sim"

    def _allow_sim(self, request) -> bool:
        """Return True if simulation fallback is allowed for this request."""
        return self._get_flow(request) != "live"

    def get_sim_fallback(
        self,
        request,
        sim_fn: Callable[[], list[dict]],
        fiber_key: str = "fiberLine",
    ) -> list[dict] | None:
        """
        Try to get data from the simulation cache.

        Returns the org-filtered sim data list, or None if:
        - The client is on the live flow
        - The simulation is not running
        - The sim function returns no data
        - The sim data has no items matching the user's org

        Args:
            request: DRF request (used for flow param and user org-scoping).
            sim_fn: Callable that returns simulation data (e.g. get_simulation_incidents).
            fiber_key: Key in each item dict that holds the directional fiber ID.
        """
        if not self._allow_sim(request):
            return None

        from apps.realtime.simulation_manager import SimulationManager

        if not SimulationManager.instance().is_running:
            return None

        try:
            data = sim_fn()
        except ImportError:
            return None

        if not data:
            return None

        # Org-scope: filter to user's assigned fibers
        if not request.user.is_superuser:
            from apps.fibers.utils import filter_by_org, get_org_fiber_ids

            fiber_ids = get_org_fiber_ids(request.user.organization)
            if not fiber_ids:
                return []
            data = filter_by_org(data, fiber_ids, fiber_key=fiber_key)

        return data if data else None
