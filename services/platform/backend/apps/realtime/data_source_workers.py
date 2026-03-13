"""
Subprocess entry points for simulation and Kafka bridge.

These functions are spawned as separate processes by ``run_realtime``.
They must NOT import Django or application code at the module level
because ``multiprocessing.spawn`` imports this module before
``django.setup()`` runs in the child.

On Linux (fork start method), the child inherits the parent's open DB
connections.  We close them before calling ``django.setup()`` so the
child gets a clean connection pool.
"""

import asyncio
import os


def _init_django(settings_module: str) -> None:
    """Bootstrap Django in a subprocess, closing any inherited connections."""
    import django

    os.environ["DJANGO_SETTINGS_MODULE"] = settings_module
    # Clear the master's warmup-skip flag — data source subprocesses don't
    # serve HTTP so they don't need SHM warmup either, but the flag should
    # not leak into their environment.
    os.environ.pop("_SEQUOIA_SKIP_WARMUP", None)
    django.setup()

    # Close DB connections inherited from the parent process (Linux fork).
    # The child will open fresh connections on first use.
    from django.db import connections

    connections.close_all()


def simulation_worker(settings_module: str, fibers: list, infrastructure: list) -> None:
    """Entry point for the simulation subprocess."""
    _init_django(settings_module)

    import logging

    from apps.realtime.simulation import FiberConfig, run_simulation_loop
    from apps.realtime.simulation_state import store_status

    logger = logging.getLogger("sequoia.simulation")

    try:
        asyncio.run(
            run_simulation_loop(
                [FiberConfig(**f) for f in fibers],
                infrastructure,
            )
        )
    except KeyboardInterrupt:
        logger.info("Simulation stopped (interrupted)")
    except Exception as exc:
        logger.exception("Simulation crashed: %s", exc)
    finally:
        store_status(running=False)


def kafka_worker(settings_module: str, infrastructure: list) -> None:
    """Entry point for the Kafka bridge subprocess with auto-restart."""
    _init_django(settings_module)

    import logging
    import time as _time

    from apps.realtime.kafka_bridge import run_kafka_bridge_loop

    logger = logging.getLogger("sequoia.kafka_bridge")

    while True:
        try:
            asyncio.run(run_kafka_bridge_loop(infrastructure))
            break
        except KeyboardInterrupt:
            break
        except Exception as exc:
            logger.error("Kafka bridge crashed: %s. Restarting in 5s...", exc)
            _time.sleep(5)
