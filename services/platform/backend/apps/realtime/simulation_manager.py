"""
Simulation lifecycle manager — decoupled from ASGI request handling.

Manages simulation startup, shutdown, and health status independently
of the HTTP/WebSocket server lifecycle. The simulation can fail or restart
without affecting WebSocket connections.

Usage:
    manager = SimulationManager.instance()
    await manager.start(fibers, infrastructure)
    manager.status  # 'idle' | 'starting' | 'running' | 'failed'
    await manager.stop()
"""

import asyncio
import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger("sequoia.simulation")


class SimulationStatus(str, Enum):
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    FAILED = "failed"
    STOPPED = "stopped"


class SimulationManager:
    """
    Singleton that owns the simulation task lifecycle.

    Separates simulation startup from request handling so that:
    - Simulation failure doesn't block WebSocket connections
    - Simulation can be restarted independently
    - Status is observable via health checks
    """

    _instance: Optional["SimulationManager"] = None

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._status: SimulationStatus = SimulationStatus.IDLE
        self._error: Optional[str] = None
        self._started: bool = False

    @classmethod
    def instance(cls) -> "SimulationManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        """Reset singleton (for testing)."""
        cls._instance = None

    @property
    def status(self) -> SimulationStatus:
        return self._status

    @property
    def error(self) -> Optional[str]:
        return self._error

    @property
    def is_running(self) -> bool:
        return self._status == SimulationStatus.RUNNING

    async def start_if_configured(self):
        """
        Start simulation if REALTIME_AUTO_START_SIMULATION is True.

        Safe to call multiple times — only starts once.
        Never raises; logs errors and sets status to FAILED.
        """
        if self._started:
            return

        from django.conf import settings

        if not getattr(settings, "REALTIME_AUTO_START_SIMULATION", False):
            return

        self._started = True
        self._status = SimulationStatus.STARTING
        self._error = None

        try:
            from asgiref.sync import sync_to_async

            from apps.realtime.management.commands.run_realtime import Command

            cmd = Command()
            fibers = await sync_to_async(cmd._load_fibers)()
            infrastructure = await sync_to_async(cmd._load_infrastructure)()

            if not fibers:
                self._status = SimulationStatus.FAILED
                self._error = "No fiber data found"
                logger.error("Simulation startup failed: no fiber data found")
                return

            self._task = asyncio.create_task(self._run_with_supervision(fibers, infrastructure))
            logger.info(
                "Simulation task created: %d fibers, %d infrastructure",
                len(fibers),
                len(infrastructure),
            )

        except Exception as e:
            self._status = SimulationStatus.FAILED
            self._error = str(e)
            logger.exception("Simulation startup failed: %s", e)

    async def _run_with_supervision(self, fibers, infrastructure):
        """
        Run simulation loop with error capture.

        If the simulation crashes, status is set to FAILED
        instead of propagating the exception.
        """
        from apps.realtime.simulation import run_simulation_loop

        try:
            self._status = SimulationStatus.RUNNING
            await run_simulation_loop(fibers, infrastructure)
        except asyncio.CancelledError:
            self._status = SimulationStatus.STOPPED
            logger.info("Simulation stopped (cancelled)")
        except Exception as e:
            self._status = SimulationStatus.FAILED
            self._error = str(e)
            logger.exception("Simulation crashed: %s", e)

    async def stop(self):
        """Cancel the simulation task if running."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._status = SimulationStatus.STOPPED
        self._task = None

    def health(self) -> dict:
        """Return health info for readiness checks."""
        return {
            "status": self._status.value,
            "error": self._error,
        }
