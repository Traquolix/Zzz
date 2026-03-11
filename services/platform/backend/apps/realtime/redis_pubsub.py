"""
Redis pub/sub transport for high-frequency realtime broadcasts.

Detections (10 Hz) and SHM readings (1 Hz) use Redis pub/sub instead of
the Django Channels layer. Pub/sub is fire-and-forget: if a subscriber
is slow, it simply misses the message — no stale backlog, no time jumps.

Low-frequency channels (incidents, fibers) stay on the Channels layer
where reliable delivery matters.

Channel naming: ``sequoia:{flow}:{channel}:org:{org_id}``
  e.g. ``sequoia:sim:detections:org:__all__``
"""

import asyncio
import json
import logging

import redis.asyncio as aioredis
from django.conf import settings

from apps.realtime.broadcast import group_by_org

logger = logging.getLogger("sequoia.pubsub")

# One Redis publish client per event loop, keyed by loop id.
# Avoids "Future attached to a different loop" when multiple
# threads each run their own asyncio event loop.
_publish_clients: dict[int, aioredis.Redis] = {}


def pubsub_channel_name(flow: str, channel: str, org_id: str) -> str:
    """Build the Redis pub/sub channel name."""
    return f"sequoia:{flow}:{channel}:org:{org_id}"


async def get_publish_client() -> aioredis.Redis:
    """Return a per-event-loop async Redis client for publishing.

    Each event loop gets its own client to avoid the
    'Future attached to a different loop' error that occurs when
    a client created in one loop is reused in another.
    """
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    client = _publish_clients.get(loop_id)
    if client is None:
        url: str = getattr(settings, "REDIS_PUBSUB_URL", "redis://localhost:6379/0")
        client = aioredis.Redis.from_url(url, decode_responses=True)  # type: ignore[assignment]
        _publish_clients[loop_id] = client
    return client


async def close_publish_client() -> None:
    """Close the publish client for the current event loop."""
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    client = _publish_clients.pop(loop_id, None)
    if client is not None:
        await client.aclose()


def create_subscriber() -> aioredis.Redis:
    """Create a new async Redis client for subscribing (one per consumer)."""
    url: str = getattr(settings, "REDIS_PUBSUB_URL", "redis://localhost:6379/0")
    client: aioredis.Redis = aioredis.Redis.from_url(url, decode_responses=True)  # type: ignore[assignment]
    return client


async def pubsub_publish_per_org(
    channel: str,
    items: list[dict],
    fiber_org_map: dict[str, list[str]],
    *,
    flow: str,
    fiber_key: str = "fiberId",
) -> None:
    """
    Publish items split by org to Redis pub/sub channels.

    Always publishes the full set to the ``__all__`` channel for superusers.
    """
    if not items:
        return

    from apps.shared.metrics import PUBSUB_MESSAGES_PUBLISHED

    client = await get_publish_client()
    envelope = {"channel": channel, "data": items}
    payload = json.dumps(envelope)

    # Always send full data to superuser channel
    all_channel = pubsub_channel_name(flow, channel, "__all__")
    try:
        await client.publish(all_channel, payload)
        PUBSUB_MESSAGES_PUBLISHED.labels(channel=channel).inc()
    except Exception:
        logger.warning("Pub/sub publish failed for %s", all_channel, exc_info=True)

    # Send org-scoped subsets
    for org_id, org_items in group_by_org(items, fiber_org_map, fiber_key).items():
        org_channel = pubsub_channel_name(flow, channel, org_id)
        org_envelope = {"channel": channel, "data": org_items}
        try:
            await client.publish(org_channel, json.dumps(org_envelope))
            PUBSUB_MESSAGES_PUBLISHED.labels(channel=channel).inc()
        except Exception:
            logger.warning("Pub/sub publish failed for %s", org_channel, exc_info=True)


async def pubsub_publish_shm(
    readings: list[dict],
    fiber_org_map: dict[str, list[str]],
    *,
    flow: str,
) -> None:
    """Publish SHM readings split by org to Redis pub/sub channels."""
    if not readings:
        return

    from apps.shared.metrics import PUBSUB_MESSAGES_PUBLISHED

    client = await get_publish_client()
    channel = "shm_readings"
    envelope = {"channel": channel, "data": readings}
    payload = json.dumps(envelope)

    all_channel = pubsub_channel_name(flow, channel, "__all__")
    try:
        await client.publish(all_channel, payload)
        PUBSUB_MESSAGES_PUBLISHED.labels(channel=channel).inc()
    except Exception:
        logger.warning("Pub/sub publish failed for %s", all_channel, exc_info=True)

    for org_id, org_items in group_by_org(readings, fiber_org_map, "fiberId").items():
        org_channel = pubsub_channel_name(flow, channel, org_id)
        org_envelope = {"channel": channel, "data": org_items}
        try:
            await client.publish(org_channel, json.dumps(org_envelope))
            PUBSUB_MESSAGES_PUBLISHED.labels(channel=channel).inc()
        except Exception:
            logger.warning("Pub/sub publish failed for %s", org_channel, exc_info=True)
