"""
WebSocket consumer for real-time data channels.

Implements the subscribe/unsubscribe JSON protocol that the frontend expects:
  Client sends:  { "action": "subscribe", "channel": "detections" }
  Client sends:  { "action": "unsubscribe", "channel": "incidents" }
  Client sends:  { "action": "ping" }
  Server sends:  { "channel": "detections", "data": [...] }
  Server sends:  { "action": "pong" }

Supported channels:
  - detections: Speed/position detections at 10 Hz (Redis pub/sub)
  - incidents: Incident creation/resolution events (Channels layer)
  - shm_readings: Structural Health Monitoring frequency data at 1 Hz (Redis pub/sub)
  - fibers: Initial fiber configuration, sent once on subscribe (Channels layer)

Transport split:
  - High-frequency ephemeral data (detections, SHM) → Redis pub/sub
  - Low-frequency reliable data (incidents, fibers) → Django Channels layer

Org-scoped: each client subscribes to org-specific channels/groups.
Superusers join the __all__ channel to receive all data.
"""

import asyncio
import contextlib
import json
import logging
import time
from typing import Any

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError

from apps.shared.exceptions import ClickHouseUnavailableError

logger = logging.getLogger("sequoia.realtime.consumers")

# Whitelist of channels clients can subscribe to
ALLOWED_CHANNELS = frozenset(
    {
        "detections",
        "incidents",
        "shm_readings",
        "fibers",
        "config_updated",
    }
)

# High-frequency channels use Redis pub/sub (fire-and-forget)
PUBSUB_CHANNELS = frozenset({"detections", "shm_readings"})

# Low-frequency channels use Django Channels layer (reliable delivery)
LAYER_CHANNELS = frozenset({"incidents", "fibers", "config_updated"})

# Rate limiting: max messages per window
RATE_LIMIT_MESSAGES = 100
RATE_LIMIT_WINDOW_SECONDS = 10

# Seconds to wait for auth message before closing connection
AUTH_TIMEOUT_SECONDS = 15


def _org_group_name(channel: str, org_id: str | None, flow: str) -> str:
    """Build the flow-prefixed, org-scoped Channels group name."""
    return f"realtime_{flow}_{channel}_org_{org_id}"


class RealtimeConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer that manages per-client channel subscriptions.
    Clients subscribe to named data channels and receive broadcasts
    via the Channels layer group system. Groups are org-scoped.

    Authentication: connect then send {"action": "authenticate", "token": "<jwt>"}
    """

    async def connect(self) -> None:
        # Origin check — reject cross-origin WebSocket connections (CSRF mitigation)
        headers = dict(self.scope.get("headers", []))
        origin = headers.get(b"origin", b"").decode("utf-8", errors="ignore")
        host = headers.get(b"host", b"").decode("utf-8", errors="ignore")
        if origin and host:
            from urllib.parse import urlparse

            origin_host = urlparse(origin).hostname
            request_host = host.split(":")[0]
            if origin_host and request_host and origin_host != request_host:
                logger.warning("WebSocket rejected: origin=%s does not match host=%s", origin, host)
                await self.close(code=4003)
                return

        # All connections start unauthenticated — require message-based auth
        self.subscriptions: set[str] = set()
        self._user: Any | None = None
        self._org_id: str | None = None
        self._authenticated = False
        self._auth_timeout_task: asyncio.Task[None] | None = None
        await self.accept()
        # Start auth timeout — close connection if client doesn't authenticate in time
        self._auth_timeout_task = asyncio.ensure_future(self._auth_timeout())
        logger.debug(
            "WebSocket client connected (pending authentication, %ds timeout)", AUTH_TIMEOUT_SECONDS
        )

    async def _auth_timeout(self) -> None:
        """Close connection if authentication is not completed within timeout."""
        try:
            await asyncio.sleep(AUTH_TIMEOUT_SECONDS)
            if not getattr(self, "_authenticated", False):
                logger.warning(
                    "WebSocket auth timeout after %ds — closing connection", AUTH_TIMEOUT_SECONDS
                )
                await self.send_json(
                    {
                        "action": "error",
                        "message": "Authentication timeout",
                    }
                )
                await self.close(code=4001)
        except asyncio.CancelledError:
            pass  # Auth succeeded or connection closed before timeout

    def _setup_user(self, user: Any) -> None:
        """Initialize user state after authentication."""
        self.subscriptions = set()
        self._user = user
        self._authenticated = True
        self._flow: str = "live"  # Overwritten in _handle_authenticate based on availability
        # Rate limiting state
        self._message_times: list[float] = []
        # Pub/sub state (lazily initialized on first high-frequency subscribe)
        self._redis_client: Any | None = None
        self._pubsub: Any | None = None
        self._pubsub_task: asyncio.Task[None] | None = None
        self._pubsub_subscriptions: dict[str, str] = {}  # channel -> redis pubsub channel name
        # Superusers see all data; regular users scoped to their org
        if user.is_superuser:
            self._org_id = "__all__"
            self._org: Any | None = None
        else:
            self._org_id = str(user.organization_id)
            self._org = user.organization

    async def disconnect(self, close_code: int) -> None:
        # Cancel auth timeout if still pending
        task = getattr(self, "_auth_timeout_task", None)
        if task is not None and not task.done():
            task.cancel()

        # Clean up pub/sub resources
        await self._cleanup_pubsub()

        # Leave channel layer groups (incidents, fibers)
        flow = getattr(self, "_flow", "sim")
        for channel in list(self.subscriptions):
            if channel in LAYER_CHANNELS:
                await self.channel_layer.group_discard(
                    _org_group_name(channel, self._org_id, flow=flow), self.channel_name
                )
        self.subscriptions.clear()
        if getattr(self, "_authenticated", False):
            from apps.shared.metrics import WEBSOCKET_CONNECTIONS

            WEBSOCKET_CONNECTIONS.add(-1)
        logger.debug("WebSocket client disconnected (code=%s)", close_code)

    def _is_rate_limited(self) -> bool:
        """Check if client has exceeded rate limit."""
        now = time.time()
        cutoff = now - RATE_LIMIT_WINDOW_SECONDS

        # Remove old timestamps
        self._message_times = [t for t in self._message_times if t > cutoff]

        if len(self._message_times) >= RATE_LIMIT_MESSAGES:
            return True

        self._message_times.append(now)
        return False

    async def receive_json(self, content: dict[str, Any]) -> None:
        action = content.get("action")

        if action == "ping":
            await self.send_json({"action": "pong"})
            return

        # Handle message-based authentication
        if action == "authenticate":
            await self._handle_authenticate(content.get("token"))
            return

        # Require authentication for all other actions
        if not getattr(self, "_authenticated", False):
            logger.warning("Unauthenticated client attempted action: %s", action)
            await self.send_json({"action": "error", "message": "Authentication required"})
            return

        # Handle flow switching
        if action == "set_flow":
            new_flow = content.get("flow")
            if new_flow not in ("sim", "live"):
                await self.send_json({"action": "error", "message": "Invalid flow"})
                return
            await self._switch_flow(new_flow)
            return

        # Rate limit check
        if self._is_rate_limited():
            logger.warning(
                "Client rate limited: user=%s", self._user.username if self._user else "unknown"
            )
            await self.send_json({"action": "error", "message": "Rate limit exceeded"})
            return

        channel = content.get("channel")
        if not action or not channel:
            return

        # Reject subscriptions to unknown channels
        if channel not in ALLOWED_CHANNELS:
            logger.warning("Client tried to subscribe to unknown channel: %s", channel)
            return

        if action == "subscribe":
            if channel not in self.subscriptions:
                self.subscriptions.add(channel)
                if channel in PUBSUB_CHANNELS:
                    await self._subscribe_pubsub(channel)
                else:
                    await self.channel_layer.group_add(
                        _org_group_name(channel, self._org_id, flow=self._flow),
                        self.channel_name,
                    )
                logger.debug(
                    "Client subscribed to: %s (org=%s, flow=%s)", channel, self._org_id, self._flow
                )

                # Send initial data for certain channels
                if channel == "incidents":
                    await self._send_initial_incidents()
                elif channel == "fibers":
                    await self._send_initial_fibers()

        elif action == "unsubscribe" and channel in self.subscriptions:
            self.subscriptions.discard(channel)
            if channel in PUBSUB_CHANNELS:
                await self._unsubscribe_pubsub(channel)
            else:
                await self.channel_layer.group_discard(
                    _org_group_name(channel, self._org_id, flow=self._flow),
                    self.channel_name,
                )
            logger.debug("Client unsubscribed from: %s", channel)

    async def _handle_authenticate(self, token: str | None) -> None:
        """Handle message-based authentication with rate limiting."""
        # Rate limit auth attempts (max 5 per connection)
        self._auth_attempts = getattr(self, "_auth_attempts", 0) + 1
        if self._auth_attempts > 5:
            logger.warning("WebSocket auth rate limit exceeded")
            await self.send_json(
                {"action": "authenticated", "success": False, "message": "Too many attempts"}
            )
            await self.close(code=4029)
            return

        if not token:
            await self.send_json(
                {"action": "authenticated", "success": False, "message": "Token required"}
            )
            return

        from apps.realtime.middleware import get_user_from_token

        user = await get_user_from_token(token)

        if user is None or not user.is_authenticated:
            from apps.shared.metrics import WEBSOCKET_AUTH_FAILURES

            WEBSOCKET_AUTH_FAILURES.add(1)
            logger.warning("WebSocket authentication failed: invalid token")
            await self.send_json(
                {"action": "authenticated", "success": False, "message": "Invalid token"}
            )
            await self.close()
            return

        self._setup_user(user)
        # Cancel auth timeout — client authenticated successfully
        auth_task = getattr(self, "_auth_timeout_task", None)
        if auth_task is not None and not auth_task.done():
            auth_task.cancel()
        from apps.shared.metrics import WEBSOCKET_CONNECTIONS

        WEBSOCKET_CONNECTIONS.add(1)

        available_flows = ["sim"]
        if cache.get("kafka_available", False):
            available_flows.append("live")

        # Default to live if available, otherwise fall back to sim
        if "live" in available_flows:
            self._flow = "live"
        else:
            self._flow = "sim"

        logger.debug("WebSocket client authenticated: %s (org=%s)", user.username, self._org_id)
        await self.send_json(
            {
                "action": "authenticated",
                "success": True,
                "available_flows": available_flows,
                "flow": self._flow,
            }
        )

    async def _switch_flow(self, new_flow: str) -> None:
        """Switch client from current flow to new_flow, re-joining all groups."""
        old_flow = self._flow
        if old_flow == new_flow:
            await self.send_json({"action": "flow_changed", "flow": new_flow})
            return

        # Leave all old flow groups/channels
        for channel in self.subscriptions:
            if channel in PUBSUB_CHANNELS:
                await self._unsubscribe_pubsub(channel)
            else:
                await self.channel_layer.group_discard(
                    _org_group_name(channel, self._org_id, flow=old_flow), self.channel_name
                )

        self._flow = new_flow

        # Join all new flow groups/channels
        for channel in self.subscriptions:
            if channel in PUBSUB_CHANNELS:
                await self._subscribe_pubsub(channel)
            else:
                await self.channel_layer.group_add(
                    _org_group_name(channel, self._org_id, flow=new_flow), self.channel_name
                )

        await self.send_json({"action": "flow_changed", "flow": new_flow})
        logger.debug("Client switched flow: %s -> %s (org=%s)", old_flow, new_flow, self._org_id)

        # Re-send initial data for subscribed channels
        if "incidents" in self.subscriptions:
            await self._send_initial_incidents()
        if "fibers" in self.subscriptions:
            await self._send_initial_fibers()

    # ----- Redis pub/sub helpers (detections, SHM) -----

    async def _ensure_pubsub(self) -> None:
        """Lazily create Redis pub/sub connection on first high-frequency subscribe."""
        if self._redis_client is None:
            from apps.realtime.redis_pubsub import create_subscriber

            self._redis_client = create_subscriber()
            self._pubsub = self._redis_client.pubsub()

    def _ensure_pubsub_listener(self) -> None:
        """Start the pub/sub listener task if not already running."""
        if self._pubsub_task is None or self._pubsub_task.done():
            self._pubsub_task = asyncio.create_task(self._pubsub_listener())

    async def _pubsub_listener(self) -> None:
        """Read pub/sub messages and forward to WebSocket."""
        from apps.shared.metrics import WEBSOCKET_MESSAGES_SENT, WEBSOCKET_SEND_TIMEOUTS

        assert self._pubsub is not None
        try:
            async for message in self._pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    payload = json.loads(message["data"])
                    await asyncio.wait_for(self.send_json(payload), timeout=15.0)
                    WEBSOCKET_MESSAGES_SENT.add(1, {"channel": payload.get("channel", "")})
                except asyncio.TimeoutError:
                    WEBSOCKET_SEND_TIMEOUTS.add(1)
                    logger.warning("WebSocket send timeout (pub/sub) for user=%s", self._user)
                    await self.close(code=4008)
                    return
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.warning("Pub/sub listener error for user=%s", self._user, exc_info=True)
            # Restart listener after a brief delay if we still have subscriptions
            if self._pubsub_subscriptions:
                await asyncio.sleep(1)
                self._pubsub_task = None
                self._ensure_pubsub_listener()

    async def _subscribe_pubsub(self, channel: str) -> None:
        """Subscribe to a Redis pub/sub channel."""
        from apps.realtime.redis_pubsub import pubsub_channel_name

        await self._ensure_pubsub()
        assert self._pubsub is not None
        redis_channel = pubsub_channel_name(self._flow, channel, self._org_id)
        await self._pubsub.subscribe(redis_channel)
        self._pubsub_subscriptions[channel] = redis_channel
        # Start listener after first subscription (listen() exits if no subs)
        self._ensure_pubsub_listener()

    async def _unsubscribe_pubsub(self, channel: str) -> None:
        """Unsubscribe from a Redis pub/sub channel."""
        redis_channel = self._pubsub_subscriptions.pop(channel, None)
        if redis_channel and self._pubsub:
            await self._pubsub.unsubscribe(redis_channel)

    async def _cleanup_pubsub(self) -> None:
        """Clean up all pub/sub resources."""
        ps_task = getattr(self, "_pubsub_task", None)
        if ps_task is not None and not ps_task.done():
            ps_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ps_task
        ps = getattr(self, "_pubsub", None)
        if ps is not None:
            await ps.close()
        rc = getattr(self, "_redis_client", None)
        if rc is not None:
            await rc.aclose()

    # ----- Group message handlers (Channels layer: incidents, fibers) -----
    # These are called when the Channels layer routes a group_send to this consumer

    async def broadcast_message(self, event: dict[str, Any]) -> None:
        """Handle broadcast from channel layer group. Timeout prevents slow clients from blocking."""
        try:
            await asyncio.wait_for(
                self.send_json(
                    {
                        "channel": event["channel"],
                        "data": event["data"],
                    }
                ),
                timeout=15.0,
            )
            from apps.shared.metrics import WEBSOCKET_MESSAGES_SENT

            WEBSOCKET_MESSAGES_SENT.add(1, {"channel": event["channel"]})
        except asyncio.TimeoutError:
            from apps.shared.metrics import WEBSOCKET_SEND_TIMEOUTS

            WEBSOCKET_SEND_TIMEOUTS.add(1)
            logger.warning(
                "WebSocket send timeout for user=%s, channel=%s", self._user, event.get("channel")
            )
            await self.close(code=4008)

    # ----- Initial data senders -----

    async def _send_initial_incidents(self) -> None:
        """Send current incidents snapshot on subscribe."""
        try:
            incidents = await sync_to_async(self._query_initial_incidents)()
            await self.send_json({"channel": "incidents", "data": incidents})
        except ObjectDoesNotExist as e:
            # Organization not found - should not happen for authenticated users
            logger.error(
                "Organization not found for user %s: %s",
                getattr(self._user, "username", None),
                e,
            )
            await self.send_json({"channel": "incidents", "data": []})
        except (DatabaseError, OSError) as e:
            # Unexpected error - log at error level with stack trace
            logger.exception("Unexpected error sending initial incidents: %s", e)
            await self.send_json({"channel": "incidents", "data": []})

    def _query_initial_incidents(self) -> list[dict[str, Any]]:
        """Synchronous query for initial incidents (org-scoped, flow-aware).

        In 'sim' flow: returns simulation cache (org-filtered).
        In 'live' flow: queries ClickHouse only (no sim fallback).
        """
        if self._flow == "sim":
            from apps.realtime.simulation_manager import SimulationManager

            if SimulationManager.instance().is_running:
                from apps.realtime.simulation import get_simulation_incidents

                incidents = get_simulation_incidents()
                # Org-scope: filter sim incidents to user's fibers
                if self._org_id != "__all__":
                    from apps.fibers.utils import filter_by_org, get_org_fiber_ids

                    fiber_ids = get_org_fiber_ids(self._org)
                    if not fiber_ids:
                        return []
                    incidents = filter_by_org(incidents, fiber_ids)
                return incidents
            return []

        # 'live' flow — ClickHouse only
        from apps.monitoring.incident_service import query_active

        try:
            if self._org_id == "__all__":
                incidents = query_active(fiber_ids=None, limit=100)
            else:
                from apps.fibers.utils import get_org_fiber_ids

                fiber_ids = get_org_fiber_ids(self._org)
                if not fiber_ids:
                    return []
                incidents = query_active(fiber_ids=fiber_ids, limit=100)
            return incidents or []
        except ClickHouseUnavailableError:
            return []

    async def _send_initial_fibers(self) -> None:
        """Send fiber configuration on subscribe (reads from PostgreSQL)."""
        try:
            fibers = await sync_to_async(self._query_initial_fibers)()
            await self.send_json({"channel": "fibers", "data": fibers})
        except (DatabaseError, OSError) as e:
            logger.exception("Failed to load fibers: %s", e)
            await self.send_json({"channel": "fibers", "data": []})

    def _query_initial_fibers(self) -> list[dict[str, Any]]:
        """Load fiber configuration from PostgreSQL (org-scoped)."""
        from apps.fibers.models import FiberCable
        from apps.fibers.utils import cable_to_physical_dict, expand_to_directional

        if self._org_id == "__all__":
            queryset = FiberCable.objects.all()
        else:
            from apps.fibers.utils import get_org_fiber_ids

            fiber_ids = get_org_fiber_ids(self._org)
            if not fiber_ids:
                return []
            queryset = FiberCable.objects.filter(id__in=fiber_ids)

        fibers = []
        for cable in queryset:
            fibers.extend(expand_to_directional(cable_to_physical_dict(cable)))
        return fibers
