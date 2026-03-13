"""
Subprocess entry points for simulation and Kafka bridge.

These functions are spawned as separate processes by ``run_realtime``.
They must NOT import Django or application code at the module level
because ``multiprocessing.spawn`` imports this module before
``django.setup()`` runs in the child.
"""

import asyncio
import os


def simulation_worker(settings_module: str, fibers: list, infrastructure: list) -> None:
    """Entry point for the simulation subprocess."""
    import django

    os.environ["DJANGO_SETTINGS_MODULE"] = settings_module
    django.setup()

    from apps.realtime.simulation import FiberConfig, run_simulation_loop

    asyncio.run(
        run_simulation_loop(
            [FiberConfig(**f) for f in fibers],
            infrastructure,
        )
    )


def kafka_worker(settings_module: str, infrastructure: list) -> None:
    """Entry point for the Kafka bridge subprocess with auto-restart."""
    import logging
    import time as _time

    import django

    os.environ["DJANGO_SETTINGS_MODULE"] = settings_module
    django.setup()

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
