"""
Simulation status — read-only health check for the simulation subprocess.

The simulation runs as a separate subprocess managed by ``run_realtime``.
This module provides a read-only interface for health checks and status
queries from the ASGI workers.

Usage:
    from apps.realtime.simulation_manager import SimulationManager
    manager = SimulationManager.instance()
    manager.is_running   # True if simulation subprocess is alive
    manager.health()     # {"status": "running", ...}
"""

import logging
from typing import Optional

logger = logging.getLogger("sequoia.simulation")


class SimulationManager:
    """
    Read-only singleton for simulation status queries.

    Reads status from Redis (written by the simulation subprocess).
    No longer manages simulation lifecycle — that's handled by
    run_realtime via multiprocessing.
    """

    _instance: Optional["SimulationManager"] = None

    @classmethod
    def instance(cls) -> "SimulationManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None

    @property
    def is_running(self) -> bool:
        from apps.realtime.simulation_state import is_running

        return is_running()

    def health(self) -> dict:
        """Return health info for readiness checks."""
        running = self.is_running
        return {
            "status": "running" if running else "idle",
            "error": None,
        }
