"""
WebSocket consumer for real-time data channels.

Implements the subscribe/unsubscribe JSON protocol that the frontend expects:
  Client sends:  { "action": "subscribe", "channel": "detections" }
  Client sends:  { "action": "unsubscribe", "channel": "incidents" }
  Client sends:  { "action": "ping" }
  Server sends:  { "channel": "detections", "data": [...] }
  Server sends:  { "action": "pong" }

Supported channels:
  - detections: Speed/position detections at 10 Hz
  - counts: AI-derived vehicle flow counts per fiber section
  - incidents: Incident creation/resolution events
  - shm_readings: Structural Health Monitoring frequency data at 1 Hz
  - fibers: Initial fiber configuration (sent once on subscribe)

Org-scoped: each client joins org-specific groups (realtime_{channel}_org_{org_id}).
Superusers join the __all__ group to receive all data.
"""

import asyncio
import logging
import time

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.exceptions import ObjectDoesNotExist

from apps.shared.exceptions import ClickHouseUnavailableError

logger = logging.getLogger('sequoia.realtime')

# Whitelist of channels clients can subscribe to
ALLOWED_CHANNELS = frozenset({
    'detections', 'counts', 'incidents', 'shm_readings', 'fibers',
})

# Rate limiting: max messages per window
RATE_LIMIT_MESSAGES = 100
RATE_LIMIT_WINDOW_SECONDS = 10

# Seconds to wait for auth message before closing connection
AUTH_TIMEOUT_SECONDS = 5


def _org_group_name(channel: str, org_id: str) -> str:
    """Build the org-scoped Channels group name."""
    return f'realtime_{channel}_org_{org_id}'


class RealtimeConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer that manages per-client channel subscriptions.
    Clients subscribe to named data channels and receive broadcasts
    via the Channels layer group system. Groups are org-scoped.

    Authentication: connect then send {"action": "authenticate", "token": "<jwt>"}
    """

    async def connect(self):
        # Origin check — reject cross-origin WebSocket connections (CSRF mitigation)
        headers = dict(self.scope.get('headers', []))
        origin = headers.get(b'origin', b'').decode('utf-8', errors='ignore')
        host = headers.get(b'host', b'').decode('utf-8', errors='ignore')
        if origin and host:
            from urllib.parse import urlparse
            origin_host = urlparse(origin).hostname
            request_host = host.split(':')[0]
            if origin_host and request_host and origin_host != request_host:
                logger.warning('WebSocket rejected: origin=%s does not match host=%s', origin, host)
                await self.close(code=4003)
                return

        # All connections start unauthenticated — require message-based auth
        self.subscriptions = set()
        self._user = None
        self._org_id = None
        self._authenticated = False
        self._auth_timeout_task = None
        await self.accept()
        # Start auth timeout — close connection if client doesn't authenticate in time
        self._auth_timeout_task = asyncio.ensure_future(self._auth_timeout())
        logger.debug('WebSocket client connected (pending authentication, %ds timeout)', AUTH_TIMEOUT_SECONDS)

    async def _auth_timeout(self):
        """Close connection if authentication is not completed within timeout."""
        try:
            await asyncio.sleep(AUTH_TIMEOUT_SECONDS)
            if not getattr(self, '_authenticated', False):
                logger.warning('WebSocket auth timeout after %ds — closing connection', AUTH_TIMEOUT_SECONDS)
                await self.send_json({
                    'action': 'error',
                    'message': 'Authentication timeout',
                })
                await self.close(code=4001)
        except asyncio.CancelledError:
            pass  # Auth succeeded or connection closed before timeout

    def _setup_user(self, user):
        """Initialize user state after authentication."""
        self.subscriptions = set()
        self._user = user
        self._authenticated = True
        # Rate limiting state
        self._message_times = []
        # Superusers see all data; regular users scoped to their org
        if user.is_superuser:
            self._org_id = '__all__'
        else:
            self._org_id = str(user.organization_id)

    async def disconnect(self, close_code):
        # Cancel auth timeout if still pending
        if getattr(self, '_auth_timeout_task', None) and not self._auth_timeout_task.done():
            self._auth_timeout_task.cancel()

        # Leave all channel groups
        for channel in list(self.subscriptions):
            await self.channel_layer.group_discard(
                _org_group_name(channel, self._org_id), self.channel_name
            )
        self.subscriptions.clear()
        if getattr(self, '_authenticated', False):
            from apps.shared.metrics import WEBSOCKET_CONNECTIONS
            WEBSOCKET_CONNECTIONS.dec()
        logger.debug('WebSocket client disconnected (code=%s)', close_code)

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

    async def receive_json(self, content):
        action = content.get('action')

        if action == 'ping':
            await self.send_json({'action': 'pong'})
            return

        # Handle message-based authentication
        if action == 'authenticate':
            await self._handle_authenticate(content.get('token'))
            return

        # Require authentication for all other actions
        if not getattr(self, '_authenticated', False):
            logger.warning('Unauthenticated client attempted action: %s', action)
            await self.send_json({'action': 'error', 'message': 'Authentication required'})
            return

        # Rate limit check
        if self._is_rate_limited():
            logger.warning('Client rate limited: user=%s', self._user.username if self._user else 'unknown')
            await self.send_json({'action': 'error', 'message': 'Rate limit exceeded'})
            return

        channel = content.get('channel')
        if not action or not channel:
            return

        # Reject subscriptions to unknown channels
        if channel not in ALLOWED_CHANNELS:
            logger.warning('Client tried to subscribe to unknown channel: %s', channel)
            return

        if action == 'subscribe':
            if channel not in self.subscriptions:
                self.subscriptions.add(channel)
                await self.channel_layer.group_add(
                    _org_group_name(channel, self._org_id), self.channel_name
                )
                logger.debug('Client subscribed to: %s (org=%s)', channel, self._org_id)

                # Send initial data for certain channels
                if channel == 'incidents':
                    await self._send_initial_incidents()
                elif channel == 'fibers':
                    await self._send_initial_fibers()

        elif action == 'unsubscribe':
            if channel in self.subscriptions:
                self.subscriptions.discard(channel)
                await self.channel_layer.group_discard(
                    _org_group_name(channel, self._org_id), self.channel_name
                )
                logger.debug('Client unsubscribed from: %s', channel)

    async def _handle_authenticate(self, token: str | None):
        """Handle message-based authentication with rate limiting."""
        # Rate limit auth attempts (max 5 per connection)
        self._auth_attempts = getattr(self, '_auth_attempts', 0) + 1
        if self._auth_attempts > 5:
            logger.warning('WebSocket auth rate limit exceeded')
            await self.send_json({'action': 'authenticated', 'success': False, 'message': 'Too many attempts'})
            await self.close(code=4029)
            return

        if not token:
            await self.send_json({'action': 'authenticated', 'success': False, 'message': 'Token required'})
            return

        from apps.realtime.middleware import get_user_from_token
        user = await get_user_from_token(token)

        if user is None or not user.is_authenticated:
            from apps.shared.metrics import WEBSOCKET_AUTH_FAILURES
            WEBSOCKET_AUTH_FAILURES.inc()
            logger.warning('WebSocket authentication failed: invalid token')
            await self.send_json({'action': 'authenticated', 'success': False, 'message': 'Invalid token'})
            await self.close()
            return

        self._setup_user(user)
        # Cancel auth timeout — client authenticated successfully
        if getattr(self, '_auth_timeout_task', None) and not self._auth_timeout_task.done():
            self._auth_timeout_task.cancel()
        from apps.shared.metrics import WEBSOCKET_CONNECTIONS
        WEBSOCKET_CONNECTIONS.inc()
        logger.debug('WebSocket client authenticated: %s (org=%s)', user.username, self._org_id)
        await self.send_json({'action': 'authenticated', 'success': True})

    # ----- Group message handlers -----
    # These are called when the Channels layer routes a group_send to this consumer

    async def broadcast_message(self, event):
        """Handle broadcast from channel layer group. Timeout prevents slow clients from blocking."""
        try:
            await asyncio.wait_for(
                self.send_json({
                    'channel': event['channel'],
                    'data': event['data'],
                }),
                timeout=5.0,
            )
            from apps.shared.metrics import WEBSOCKET_MESSAGES_SENT
            WEBSOCKET_MESSAGES_SENT.labels(channel=event['channel']).inc()
        except asyncio.TimeoutError:
            from apps.shared.metrics import WEBSOCKET_SEND_TIMEOUTS
            WEBSOCKET_SEND_TIMEOUTS.inc()
            logger.warning('WebSocket send timeout for user=%s, channel=%s', self._user, event.get('channel'))
            await self.close(code=4008)

    # ----- Initial data senders -----

    async def _send_initial_incidents(self):
        """Send current incidents snapshot on subscribe."""
        try:
            incidents = await sync_to_async(self._query_initial_incidents)()
            await self.send_json({'channel': 'incidents', 'data': incidents})
        except ClickHouseUnavailableError as e:
            # Expected when ClickHouse is down - log at info level and send empty data
            logger.info('ClickHouse unavailable for initial incidents: %s', e)
            await self.send_json({'channel': 'incidents', 'data': []})
        except ObjectDoesNotExist as e:
            # Organization not found - should not happen for authenticated users
            logger.error('Organization not found for user %s: %s', self._user.username, e)
            await self.send_json({'channel': 'incidents', 'data': []})
        except Exception as e:
            # Unexpected error - log at error level with stack trace
            logger.exception('Unexpected error sending initial incidents: %s', e)
            await self.send_json({'channel': 'incidents', 'data': []})

    def _query_initial_incidents(self):
        """Synchronous ClickHouse query for initial incidents (org-scoped)."""
        from apps.monitoring.incident_service import query_active

        if self._org_id == '__all__':
            return query_active(fiber_ids=None, limit=100)
        else:
            from apps.fibers.utils import get_org_fiber_ids
            from apps.organizations.models import Organization
            org = Organization.objects.get(pk=self._org_id)
            fiber_ids = get_org_fiber_ids(org)
            if not fiber_ids:
                return []
            return query_active(fiber_ids=fiber_ids, limit=100)

    async def _send_initial_fibers(self):
        """Send fiber configuration on subscribe.

        Falls back to JSON cable files when ClickHouse is unavailable
        (same fallback as FiberListView).
        """
        try:
            fibers = await sync_to_async(self._query_initial_fibers)()
            await self.send_json({'channel': 'fibers', 'data': fibers})
        except ClickHouseUnavailableError as e:
            # Expected when ClickHouse is down - fall back to JSON files
            logger.info('ClickHouse unavailable, falling back to JSON for fibers: %s', e)
            await self._send_fibers_from_json_fallback()
        except ObjectDoesNotExist as e:
            logger.error('Organization not found for user %s: %s', self._user.username, e)
            await self.send_json({'channel': 'fibers', 'data': []})
        except Exception as e:
            # Unexpected error - log and try fallback
            logger.exception('Unexpected error querying fibers from ClickHouse: %s', e)
            await self._send_fibers_from_json_fallback()

    async def _send_fibers_from_json_fallback(self):
        """Load fibers from JSON cable files as fallback."""
        try:
            from apps.fibers.views import _load_fibers_from_json
            fiber_ids = None
            if self._org_id != '__all__':
                from apps.fibers.utils import get_org_fiber_ids
                from apps.organizations.models import Organization
                org = Organization.objects.get(pk=self._org_id)
                fiber_ids = get_org_fiber_ids(org)
            fibers = await sync_to_async(_load_fibers_from_json)(fiber_ids)
            await self.send_json({'channel': 'fibers', 'data': fibers})
        except FileNotFoundError as e:
            logger.error('Fiber JSON files not found: %s', e)
            await self.send_json({'channel': 'fibers', 'data': []})
        except ObjectDoesNotExist as e:
            logger.error('Organization not found in JSON fallback: %s', e)
            await self.send_json({'channel': 'fibers', 'data': []})
        except Exception as e:
            logger.exception('Failed to load fibers from JSON fallback: %s', e)
            await self.send_json({'channel': 'fibers', 'data': []})

    def _query_initial_fibers(self):
        """Synchronous ClickHouse query for fiber configuration (org-scoped)."""
        from apps.shared.clickhouse import get_client

        client = get_client()

        if self._org_id == '__all__':
            result = client.query("""
                SELECT fiber_id, fiber_name, channel_coordinates, color, landmark_labels
                FROM sequoia.fiber_cables
                ORDER BY fiber_id
            """)
        else:
            from apps.fibers.utils import get_org_fiber_ids
            from apps.organizations.models import Organization
            org = Organization.objects.get(pk=self._org_id)
            fiber_ids = get_org_fiber_ids(org)
            if not fiber_ids:
                return []
            result = client.query(
                """
                SELECT fiber_id, fiber_name, channel_coordinates, color, landmark_labels
                FROM sequoia.fiber_cables
                WHERE fiber_id IN {fids:Array(String)}
                ORDER BY fiber_id
                """,
                parameters={'fids': fiber_ids},
            )

        from apps.fibers.views import _expand_to_directional

        fibers = []
        for row in result.named_results():
            coords = []
            for coord in row['channel_coordinates']:
                lng, lat = coord
                coords.append([lng, lat] if lng is not None and lat is not None else [None, None])
            landmarks = []
            for idx, label in enumerate(row['landmark_labels'] or []):
                if label:
                    landmarks.append({'channel': idx, 'name': label})
            physical = {
                'id': row['fiber_id'],
                'name': row['fiber_name'],
                'color': row['color'],
                'coordinates': coords,
                'landmarks': landmarks or None,
                'directional_paths': {},  # ClickHouse doesn't store precomputed paths
            }
            fibers.extend(_expand_to_directional(physical))
        return fibers
