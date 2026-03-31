"""
Async broadcast loop — runs the simulation engine and broadcasts via Channels.
"""

import asyncio
import logging
import time

from channels.layers import get_channel_layer

from apps.alerting.integration import check_alerts_for_detections, check_alerts_for_incident
from apps.realtime.broadcast import (
    broadcast_to_orgs,
    group_by_org,
    load_fiber_org_map,
    pubsub_broadcast_detections,
    pubsub_broadcast_shm,
)
from apps.shared.constants import MAP_REFRESH_INTERVAL

from . import cache as _cache
from .cache import (
    _update_simulation_incidents_cache,
    _update_simulation_snapshots,
    _update_simulation_stats,
    transform_simulation_incident,
)
from .engine import SimulationEngine
from .types import Detection, FiberConfig, Incident

logger = logging.getLogger("sequoia.realtime.simulation")


async def run_simulation_loop(fibers: list[FiberConfig], infrastructure: list[dict]):
    """Main async loop — runs the simulation and broadcasts via Channels."""
    channel_layer = get_channel_layer()
    engine = SimulationEngine(fibers, infrastructure)

    # Load fiber→org mapping (refreshed every 5 minutes)
    fiber_org_map = await load_fiber_org_map()
    infra_fiber = {i["id"]: i.get("fiber_id", "") for i in infrastructure}
    last_map_refresh = time.time()

    logger.info(
        "Simulation started: %d fibers, %d infrastructure, hour=%.1f, %d org mappings",
        len(fibers),
        len(infrastructure),
        engine.simulated_hour,
        len(fiber_org_map),
    )

    # No initial incidents — they spawn after the warmup period so
    # snapshot data has time to accumulate from the vehicle simulation
    _update_simulation_incidents_cache(engine.incidents)

    # Clear stale history buffers from any previous simulation run
    _cache._simulation_per_second_buffer.clear()
    _cache._simulation_per_minute_buffer.clear()

    tick_interval = 0.05  # 50ms ticks (20 Hz physics)
    shm_counter = 0
    incident_counter = 0
    snapshot_counter = 0
    last_detection_broadcast = time.time()
    detection_broadcast_interval = 0.1  # 100ms (10 Hz)
    pending_detections: list[Detection] = []  # Accumulate detections between broadcasts
    pending_new_incidents: list[Incident] = []  # Accumulate new incidents between broadcasts
    pending_resolved_incidents: list[Incident] = []

    while True:
        tick_start = time.time()

        # Refresh fiber→org mapping periodically
        if tick_start - last_map_refresh > MAP_REFRESH_INTERVAL:
            fiber_org_map = await load_fiber_org_map()
            last_map_refresh = tick_start

        detections, new_incidents, resolved_incidents = engine.tick(tick_interval * 1000)
        engine.accumulate_detections_for_history(detections, tick_start * 1000)
        engine.rollup_minute_buffer(tick_start)
        shm_counter += 1
        incident_counter += 1
        snapshot_counter += 1
        # Accumulate detections
        pending_detections.extend(detections)
        # Accumulate incidents (broadcast happens every 100 ticks)
        pending_new_incidents.extend(new_incidents)
        pending_resolved_incidents.extend(resolved_incidents)

        # Broadcast detections at 10 Hz (time-based, not tick-based)
        time_since_last_broadcast = tick_start - last_detection_broadcast
        if time_since_last_broadcast >= detection_broadcast_interval and pending_detections:
            last_detection_broadcast = tick_start
            detection_dicts = [
                {
                    "fiberId": d.fiber_line,
                    "direction": d.direction,
                    "channel": d.channel,
                    "speed": round(d.speed, 1),
                    "count": d.count,
                    "nCars": d.n_cars,
                    "nTrucks": d.n_trucks,
                    "timestamp": d.timestamp,
                }
                for d in pending_detections
            ]
            pending_detections.clear()
            await pubsub_broadcast_detections(
                detection_dicts,
                fiber_org_map,
                flow="sim",
            )
            # Check alerts for detections (per-org)
            for org_id, org_dets in group_by_org(detection_dicts, fiber_org_map).items():
                await check_alerts_for_detections(org_dets, org_id)

        # Broadcast SHM every 20 ticks (1 Hz) — per-org via infrastructure ownership
        if shm_counter >= 20:
            shm_counter = 0
            readings = engine.generate_shm_readings()
            if readings:
                shm_dicts = [
                    {
                        "infrastructureId": r.infrastructure_id,
                        "fiberId": infra_fiber.get(r.infrastructure_id, ""),
                        "frequency": r.frequency,
                        "amplitude": r.amplitude,
                        "timestamp": r.timestamp,
                    }
                    for r in readings
                ]
                await pubsub_broadcast_shm(shm_dicts, fiber_org_map, flow="sim")

        # Sync snapshot cache every 20 ticks (1s) so frontend polling gets fresh data
        if snapshot_counter >= 20:
            snapshot_counter = 0
            _update_simulation_snapshots(engine.incident_snapshots)

        # Broadcast incidents every 100 ticks (5 seconds) — per-org
        if incident_counter >= 100:
            incident_counter = 0
            # Update caches for REST API fallback
            _update_simulation_incidents_cache(engine.incidents)
            _update_simulation_stats(engine)
            for inc in pending_new_incidents + pending_resolved_incidents:
                inc_data = transform_simulation_incident(inc)
                await broadcast_to_orgs(
                    channel_layer,
                    "incidents",
                    inc_data,
                    fiber_org_map,
                    fiber_ids={inc_data["fiberId"]},
                    flow="sim",
                )
                # Check alerts for incident
                await check_alerts_for_incident(inc_data, fiber_org_map)
            pending_new_incidents.clear()
            pending_resolved_incidents.clear()

        # Log stats periodically
        if engine.tick_count % 400 == 0:
            active = sum(1 for i in engine.incidents if i.status == "active")
            events = len(engine._road_events.events)
            logger.info(
                "[%.1fh] Vehicles: %d | Active incidents: %d | Road events: %d",
                engine.simulated_hour,
                len(engine.vehicles),
                active,
                events,
            )

        # Sleep for remaining tick time (minimum 1ms to allow event loop I/O)
        elapsed = time.time() - tick_start
        sleep_time = max(0.001, tick_interval - elapsed)
        await asyncio.sleep(sleep_time)
