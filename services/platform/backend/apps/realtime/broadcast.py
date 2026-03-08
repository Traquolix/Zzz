"""
Shared org-scoped broadcast helpers for the realtime app.

Used by both the Kafka bridge (live flow) and the simulation engine (sim flow).
All broadcasts are routed to org-specific Channels groups based on fiber ownership.
Superuser clients join the ``__all__`` group which always receives full data.

Three broadcast patterns:
- ``broadcast_to_orgs``: send the same payload to all orgs that own specific fibers
  (used for single incidents, vehicle counts).
- ``broadcast_per_org``: split a list of items so each org only gets their own fibers'
  items (used for detections, counts).
- ``broadcast_shm``: route SHM readings by infrastructure ownership instead of fiber.
"""

import logging

logger = logging.getLogger("sequoia.broadcast")


def _strip_directional_suffix(fid: str) -> str:
    """Strip directional suffix (e.g. ``"carros:0"`` → ``"carros"``)."""
    return fid.rsplit(":", 1)[0] if ":" in fid else fid


# ============================================================================
# ORG MAP LOADERS
# ============================================================================


def load_infra_org_map(infrastructure: list[dict]) -> dict[str, str]:
    """Build infrastructure_id → org_id mapping from infrastructure list."""
    return {infra["id"]: infra.get("organization_id", "") for infra in infrastructure}


def _load_fiber_org_map_sync() -> dict[str, list[str]]:
    """Load fiber→org mapping from DB (sync version, cached 5min)."""
    from apps.fibers.utils import get_fiber_org_map

    return get_fiber_org_map()


async def load_fiber_org_map() -> dict[str, list[str]]:
    """Load fiber→org mapping from DB (async-safe, cached 5min)."""
    from asgiref.sync import sync_to_async

    return await sync_to_async(_load_fiber_org_map_sync, thread_sensitive=True)()


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
        fiber_ids: Fiber IDs in this payload. ``None`` = send to all known orgs.
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
            parent_fid = _strip_directional_suffix(fid)
            for org_id in fiber_org_map.get(parent_fid, []):
                if org_id not in sent_orgs:
                    sent_orgs.add(org_id)
                    await channel_layer.group_send(
                        f"realtime_{flow}_{channel}_org_{org_id}", message
                    )


async def broadcast_per_org(
    channel_layer,
    channel: str,
    items: list[dict],
    fiber_org_map: dict[str, list[str]],
    fiber_key: str = "fiberLine",
    *,
    flow: str,
):
    """
    Split items by fiber ownership and send each org only their items.

    Used for detections and counts where different items belong to different fibers.
    Always sends the full set to the ``__all__`` group.

    Args:
        channel_layer: Django Channels layer.
        channel: Channel name (e.g. ``"detections"``).
        items: List of dicts, each containing a fiber identifier.
        fiber_org_map: ``{fiber_id: [org_id, ...]}`` mapping.
        fiber_key: Key in each item dict that holds the directional fiber ID.
        flow: ``"sim"`` or ``"live"`` — determines group name prefix.
    """
    if not items:
        return

    # Always send full data to superuser group
    await channel_layer.group_send(
        f"realtime_{flow}_{channel}_org___all__",
        {
            "type": "broadcast_message",
            "channel": channel,
            "data": items,
        },
    )

    # Group items by org
    org_items: dict[str, list[dict]] = {}
    for item in items:
        fid = item.get(fiber_key, "")
        parent_fid = _strip_directional_suffix(fid)
        for org_id in fiber_org_map.get(parent_fid, []):
            org_items.setdefault(org_id, []).append(item)

    for org_id, org_data in org_items.items():
        await channel_layer.group_send(
            f"realtime_{flow}_{channel}_org_{org_id}",
            {
                "type": "broadcast_message",
                "channel": channel,
                "data": org_data,
            },
        )


async def broadcast_shm(
    channel_layer,
    readings: list[dict],
    infra_org_map: dict[str, str],
    *,
    flow: str,
):
    """
    Broadcast SHM readings to org-scoped groups via infrastructure ownership.

    Unlike fiber-based broadcasts, SHM readings are keyed by ``infrastructureId``,
    so org routing uses ``infra_org_map`` instead of ``fiber_org_map``.
    """
    message = {
        "type": "broadcast_message",
        "channel": "shm_readings",
        "data": readings,
    }
    await channel_layer.group_send(f"realtime_{flow}_shm_readings_org___all__", message)

    org_readings: dict[str, list[dict]] = {}
    for shm in readings:
        org_id = infra_org_map.get(str(shm["infrastructureId"]), "")
        if org_id:
            org_readings.setdefault(org_id, []).append(shm)

    for org_id, org_data in org_readings.items():
        await channel_layer.group_send(
            f"realtime_{flow}_shm_readings_org_{org_id}",
            {"type": "broadcast_message", "channel": "shm_readings", "data": org_data},
        )
