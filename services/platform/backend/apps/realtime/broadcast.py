"""
Shared org-scoped broadcast helpers for the realtime app.

Used by both the Kafka bridge (live flow) and the simulation engine (sim flow).

- ``broadcast_to_orgs``: send the same payload to all orgs via Channels layer
  (used for incidents — low-frequency, reliable delivery).
- ``pubsub_broadcast_detections`` / ``pubsub_broadcast_shm``: high-frequency
  broadcasts via Redis pub/sub (fire-and-forget, no stale backlog).
"""

import logging

logger = logging.getLogger("sequoia.realtime.broadcast")


# ============================================================================
# ORG MAP LOADERS
# ============================================================================


def _load_fiber_org_map_sync() -> dict[str, list[str]]:
    """Load fiber→org mapping from DB (sync version, cached 5min)."""
    from apps.fibers.utils import get_fiber_org_map

    return get_fiber_org_map()


async def load_fiber_org_map() -> dict[str, list[str]]:
    """Load fiber→org mapping from DB (async-safe, cached 5min)."""
    from asgiref.sync import sync_to_async

    return await sync_to_async(_load_fiber_org_map_sync, thread_sensitive=True)()


# ============================================================================
# ORG GROUPING
# ============================================================================


def group_by_org(
    items: list[dict],
    fiber_org_map: dict[str, list[str]],
    fiber_key: str = "fiberId",
) -> dict[str, list[dict]]:
    """
    Group items by org ownership based on their fiber ID.

    Items are expected to have a plain ``fiberId`` field (no directional suffix).

    Returns:
        ``{org_id: [items belonging to that org]}``
    """
    org_items: dict[str, list[dict]] = {}
    for item in items:
        fid = item.get(fiber_key, "")
        for org_id in fiber_org_map.get(fid, []):
            org_items.setdefault(org_id, []).append(item)
    return org_items


# ============================================================================
# BROADCAST HELPERS
# ============================================================================


async def broadcast_to_orgs(
    channel_layer,
    channel: str,
    data,
    fiber_org_map: dict[str, list[str]],
    fiber_ids: set[str] | None = None,
    *,
    flow: str,
):
    """
    Send the same payload to all org groups that own the given fibers, plus ``__all__``.

    Args:
        channel_layer: Django Channels layer.
        channel: Channel name (e.g. ``"incidents"``).
        data: Payload to send (dict or list — sent as-is to each group).
        fiber_org_map: ``{fiber_id: [org_id, ...]}`` mapping.
        fiber_ids: Plain fiber IDs in this payload. ``None`` = send to all known orgs.
        flow: ``"sim"`` or ``"live"`` — determines group name prefix.
    """
    message = {
        "type": "broadcast_message",
        "channel": channel,
        "data": data,
    }

    # Always send to superuser group
    await channel_layer.group_send(f"realtime_{flow}_{channel}_org___all__", message)

    if fiber_ids is None:
        # Broadcast to all known orgs
        sent_orgs: set[str] = set()
        for org_ids in fiber_org_map.values():
            for org_id in org_ids:
                if org_id not in sent_orgs:
                    sent_orgs.add(org_id)
                    await channel_layer.group_send(
                        f"realtime_{flow}_{channel}_org_{org_id}", message
                    )
    else:
        # Broadcast to orgs that own these specific fibers
        sent_orgs = set()
        for fid in fiber_ids:
            for org_id in fiber_org_map.get(fid, []):
                if org_id not in sent_orgs:
                    sent_orgs.add(org_id)
                    await channel_layer.group_send(
                        f"realtime_{flow}_{channel}_org_{org_id}", message
                    )


async def broadcast_config_updated(
    channel_layer,
    config_type: str,
    fiber_org_map: dict[str, list[str]],
):
    """
    Notify all connected clients that configuration data has changed.

    Args:
        channel_layer: Django Channels layer.
        config_type: What changed — ``"fibers"`` or ``"infrastructure"``.
        fiber_org_map: ``{fiber_id: [org_id, ...]}`` mapping.
    """
    message = {
        "type": "broadcast_message",
        "channel": "config_updated",
        "data": {"type": config_type},
    }

    # Send to both flows, all orgs + superuser group
    for flow in ("sim", "live"):
        await channel_layer.group_send(f"realtime_{flow}_config_updated_org___all__", message)
        sent_orgs: set[str] = set()
        for org_ids in fiber_org_map.values():
            for org_id in org_ids:
                if org_id not in sent_orgs:
                    sent_orgs.add(org_id)
                    await channel_layer.group_send(
                        f"realtime_{flow}_config_updated_org_{org_id}", message
                    )


# ============================================================================
# PUB/SUB BROADCAST HELPERS (high-frequency channels)
# ============================================================================


async def pubsub_broadcast_detections(
    items: list[dict],
    fiber_org_map: dict[str, list[str]],
    *,
    flow: str,
):
    """Broadcast detections via Redis pub/sub (fire-and-forget)."""
    from apps.realtime.redis_pubsub import pubsub_publish_per_org

    await pubsub_publish_per_org("detections", items, fiber_org_map, flow=flow)


async def pubsub_broadcast_shm(
    readings: list[dict],
    fiber_org_map: dict[str, list[str]],
    *,
    flow: str,
):
    """Broadcast SHM readings via Redis pub/sub (fire-and-forget)."""
    from apps.realtime.redis_pubsub import pubsub_publish_shm

    await pubsub_publish_shm(readings, fiber_org_map, flow=flow)
