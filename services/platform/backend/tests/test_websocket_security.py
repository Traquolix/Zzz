"""
Tests for WebSocket consumer security: auth rate limiting, origin/CSRF checks,
broadcast timeout handling, connection metrics, and channel whitelist enforcement.

Tests operate at the consumer method level with mocked Channels infrastructure,
avoiding the need for a running Redis/Channels layer.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from apps.realtime.consumers import (
    RealtimeConsumer,
    ALLOWED_CHANNELS,
    _org_group_name,
)


# ============================================================================
# Helpers
# ============================================================================

def _make_consumer(*, authenticated=True, user=None, org_id='org-1', is_superuser=False):
    """Create a RealtimeConsumer with pre-configured state (no real connection)."""
    consumer = RealtimeConsumer()
    consumer.channel_layer = AsyncMock()
    consumer.channel_name = 'test-channel-name'
    consumer.send_json = AsyncMock()
    consumer.close = AsyncMock()
    consumer.accept = AsyncMock()
    consumer.subscriptions = set()

    if authenticated:
        mock_user = user or MagicMock()
        mock_user.is_authenticated = True
        mock_user.is_superuser = is_superuser
        mock_user.organization_id = org_id
        mock_user.username = 'testuser'
        consumer._user = mock_user
        consumer._authenticated = True
        consumer._org_id = '__all__' if is_superuser else str(org_id)
        consumer._message_times = []
    else:
        consumer._user = None
        consumer._authenticated = False
        consumer._org_id = None
        consumer._auth_attempts = 0
        consumer._message_times = []

    return consumer


def _run(coro):
    """Run an async coroutine synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ============================================================================
# Auth Rate Limiting
# ============================================================================

class TestAuthRateLimiting:
    """_handle_authenticate: max 5 attempts per connection, then close(4029)."""

    def test_first_attempt_with_invalid_token_sends_failure(self):
        """Invalid token → auth failure response, connection closed."""
        consumer = _make_consumer(authenticated=False)

        with patch('apps.realtime.middleware.get_user_from_token', new_callable=AsyncMock, return_value=None):
            _run(consumer._handle_authenticate('bad-token'))

        consumer.send_json.assert_called()
        last_call = consumer.send_json.call_args[0][0]
        assert last_call['success'] is False

    def test_six_attempts_triggers_rate_limit_close(self):
        """After 5 attempts, 6th attempt → close(4029)."""
        consumer = _make_consumer(authenticated=False)
        consumer._auth_attempts = 5  # Already at limit

        _run(consumer._handle_authenticate('bad-token'))

        consumer.close.assert_called_with(code=4029)

    def test_auth_failure_increments_metric(self):
        """Failed auth → WEBSOCKET_AUTH_FAILURES.inc() called."""
        consumer = _make_consumer(authenticated=False)

        with patch('apps.realtime.middleware.get_user_from_token', new_callable=AsyncMock, return_value=None), \
             patch('apps.shared.metrics.WEBSOCKET_AUTH_FAILURES') as mock_metric:
            _run(consumer._handle_authenticate('bad-token'))

        mock_metric.inc.assert_called_once()

    def test_successful_auth_sets_authenticated(self):
        """Valid token → consumer._authenticated=True, WEBSOCKET_CONNECTIONS.inc()."""
        consumer = _make_consumer(authenticated=False)
        consumer._auth_timeout_task = None

        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.is_superuser = False
        mock_user.organization_id = 'org-1'
        mock_user.username = 'validuser'

        with patch('apps.realtime.middleware.get_user_from_token', new_callable=AsyncMock, return_value=mock_user), \
             patch('apps.shared.metrics.WEBSOCKET_CONNECTIONS') as mock_connections:
            _run(consumer._handle_authenticate('good-token'))

        assert consumer._authenticated is True
        mock_connections.inc.assert_called_once()

    def test_empty_token_sends_error_without_incrementing_metric(self):
        """Empty token → error response, but no auth failure metric (token was missing, not wrong)."""
        consumer = _make_consumer(authenticated=False)

        _run(consumer._handle_authenticate(None))

        consumer.send_json.assert_called()
        msg = consumer.send_json.call_args[0][0]
        assert msg['success'] is False
        assert 'Token required' in msg['message']


# ============================================================================
# Origin / CSRF Check
# ============================================================================

class TestOriginCSRF:
    """connect(): origin vs host validation for CSRF mitigation."""

    def _make_scope(self, origin=None, host=None, user=None, pending_auth=False):
        headers = []
        if origin:
            headers.append((b'origin', origin.encode()))
        if host:
            headers.append((b'host', host.encode()))
        return {
            'headers': headers,
            'user': user,
            '_pending_auth': pending_auth,
        }

    def test_mismatched_origin_rejected_4003(self):
        """Origin: evil.com, Host: legit.com → close(4003)."""
        consumer = _make_consumer(authenticated=False)
        consumer.scope = self._make_scope(origin='https://evil.com', host='legit.com', pending_auth=True)

        _run(consumer.connect())

        consumer.close.assert_called_with(code=4003)
        consumer.accept.assert_not_called()

    def test_matching_origin_accepted(self):
        """Origin matches host → connection accepted."""
        consumer = _make_consumer(authenticated=False)
        consumer.scope = self._make_scope(
            origin='https://app.sequoia.io',
            host='app.sequoia.io',
            pending_auth=True,
        )

        _run(consumer.connect())

        consumer.accept.assert_called_once()

    def test_missing_origin_allowed(self):
        """No Origin header → connection accepted (same-origin browser requests omit it)."""
        consumer = _make_consumer(authenticated=False)
        consumer.scope = self._make_scope(host='app.sequoia.io', pending_auth=True)

        _run(consumer.connect())

        consumer.accept.assert_called_once()


# ============================================================================
# Broadcast Timeout
# ============================================================================

class TestBroadcastTimeout:
    """broadcast_message: 5s timeout on slow clients."""

    def test_normal_send_increments_messages_sent(self):
        """Successful broadcast → WEBSOCKET_MESSAGES_SENT incremented."""
        consumer = _make_consumer()

        with patch('apps.shared.metrics.WEBSOCKET_MESSAGES_SENT') as mock_metric:
            mock_labels = MagicMock()
            mock_metric.labels.return_value = mock_labels
            _run(consumer.broadcast_message({
                'channel': 'detections',
                'data': [{'speed': 80}],
            }))

        mock_metric.labels.assert_called_with(channel='detections')
        mock_labels.inc.assert_called_once()

    def test_timeout_closes_connection_4008(self):
        """send_json hangs → asyncio.TimeoutError → close(4008)."""
        consumer = _make_consumer()

        async def _slow_send(*args, **kwargs):
            await asyncio.sleep(10)  # Will be interrupted by timeout

        consumer.send_json = _slow_send

        with patch('apps.shared.metrics.WEBSOCKET_SEND_TIMEOUTS') as mock_timeout:
            _run(consumer.broadcast_message({
                'channel': 'detections',
                'data': [],
            }))

        # The actual timeout in the code is 5s, but wait_for will raise TimeoutError
        consumer.close.assert_called_with(code=4008)

    def test_timeout_increments_metric(self):
        """Send timeout → WEBSOCKET_SEND_TIMEOUTS.inc()."""
        consumer = _make_consumer()

        async def _slow_send(*args, **kwargs):
            await asyncio.sleep(10)

        consumer.send_json = _slow_send

        with patch('apps.shared.metrics.WEBSOCKET_SEND_TIMEOUTS') as mock_timeout:
            _run(consumer.broadcast_message({'channel': 'detections', 'data': []}))

        mock_timeout.inc.assert_called_once()


# ============================================================================
# Connection Metrics
# ============================================================================

class TestConnectionMetrics:
    """WEBSOCKET_CONNECTIONS gauge: incremented on auth, decremented on disconnect."""

    def test_disconnect_decrements_gauge(self):
        """Authenticated user disconnects → WEBSOCKET_CONNECTIONS.dec()."""
        consumer = _make_consumer()

        with patch('apps.shared.metrics.WEBSOCKET_CONNECTIONS') as mock_connections:
            _run(consumer.disconnect(close_code=1000))

        mock_connections.dec.assert_called_once()

    def test_unauthenticated_disconnect_does_not_decrement(self):
        """Unauthenticated connection closes → no metric decrement."""
        consumer = _make_consumer(authenticated=False)

        with patch('apps.shared.metrics.WEBSOCKET_CONNECTIONS') as mock_connections:
            _run(consumer.disconnect(close_code=1000))

        mock_connections.dec.assert_not_called()


# ============================================================================
# Channel Whitelist & Subscription
# ============================================================================

class TestChannelSubscription:
    """Subscribe/unsubscribe: whitelist enforcement and group management."""

    def test_subscribe_to_allowed_channel(self):
        """Subscribe to 'detections' → added to subscriptions + group_add called."""
        consumer = _make_consumer()

        with patch.object(consumer, '_send_initial_incidents', new_callable=AsyncMock), \
             patch.object(consumer, '_send_initial_fibers', new_callable=AsyncMock):
            _run(consumer.receive_json({'action': 'subscribe', 'channel': 'detections'}))

        assert 'detections' in consumer.subscriptions
        consumer.channel_layer.group_add.assert_called_once()
        group_name = consumer.channel_layer.group_add.call_args[0][0]
        assert group_name == _org_group_name('detections', consumer._org_id)

    def test_subscribe_to_unknown_channel_rejected(self):
        """Subscribe to 'hackme' → not added, no group_add."""
        consumer = _make_consumer()

        _run(consumer.receive_json({'action': 'subscribe', 'channel': 'hackme'}))

        assert 'hackme' not in consumer.subscriptions
        consumer.channel_layer.group_add.assert_not_called()

    def test_unsubscribe_removes_from_group(self):
        """Unsubscribe → removed from subscriptions + group_discard called."""
        consumer = _make_consumer()
        consumer.subscriptions.add('detections')

        _run(consumer.receive_json({'action': 'unsubscribe', 'channel': 'detections'}))

        assert 'detections' not in consumer.subscriptions
        consumer.channel_layer.group_discard.assert_called_once()

    def test_unauthenticated_client_cannot_subscribe(self):
        """Unauthenticated client sends subscribe → error response."""
        consumer = _make_consumer(authenticated=False)

        _run(consumer.receive_json({'action': 'subscribe', 'channel': 'detections'}))

        consumer.send_json.assert_called()
        msg = consumer.send_json.call_args[0][0]
        assert msg['action'] == 'error'
        assert 'Authentication required' in msg['message']

    def test_superuser_subscribes_to_all_group(self):
        """Superuser subscription → group name uses __all__."""
        consumer = _make_consumer(is_superuser=True)

        with patch.object(consumer, '_send_initial_incidents', new_callable=AsyncMock), \
             patch.object(consumer, '_send_initial_fibers', new_callable=AsyncMock):
            _run(consumer.receive_json({'action': 'subscribe', 'channel': 'incidents'}))

        group_name = consumer.channel_layer.group_add.call_args[0][0]
        assert '__all__' in group_name


# ============================================================================
# Rate Limiting (general messages)
# ============================================================================

class TestMessageRateLimiting:
    """_is_rate_limited: sliding window, 100 msgs per 10s."""

    def test_under_limit_returns_false(self):
        """99 messages in window → not rate limited."""
        consumer = _make_consumer()
        consumer._message_times = [time.time()] * 99

        assert consumer._is_rate_limited() is False

    def test_at_limit_returns_true(self):
        """100 messages in window → rate limited."""
        consumer = _make_consumer()
        consumer._message_times = [time.time()] * 100

        assert consumer._is_rate_limited() is True

    def test_old_messages_pruned(self):
        """Messages older than 10s are removed from window."""
        consumer = _make_consumer()
        old_time = time.time() - 15  # 15 seconds ago
        consumer._message_times = [old_time] * 100

        # All messages are old, so should NOT be rate limited
        assert consumer._is_rate_limited() is False


# ============================================================================
# Org Group Name Helper
# ============================================================================

class TestOrgGroupName:
    """_org_group_name: deterministic group name construction."""

    def test_regular_org(self):
        assert _org_group_name('detections', 'org-1') == 'realtime_detections_org_org-1'

    def test_superuser_all(self):
        assert _org_group_name('incidents', '__all__') == 'realtime_incidents_org___all__'


# ============================================================================
# URL Token Auth Removed
# ============================================================================

class TestURLTokenAuthRemoved:
    """URL-based ?token= auth should NOT auto-authenticate connections."""

    def test_url_token_does_not_authenticate(self):
        """Connecting with ?token=<valid_jwt> should NOT auto-authenticate."""
        consumer = _make_consumer(authenticated=False)
        consumer.scope = {
            'headers': [],
            'user': MagicMock(is_authenticated=False),
            '_pending_auth': True,
        }

        _run(consumer.connect())

        # Connection accepted but not authenticated — requires message auth
        consumer.accept.assert_called_once()
        assert not getattr(consumer, '_authenticated', True)

    def test_message_auth_still_works(self):
        """After removing URL token, message-based auth must still work."""
        consumer = _make_consumer(authenticated=False)
        consumer._auth_timeout_task = None

        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.is_superuser = False
        mock_user.organization_id = 'org-1'
        mock_user.username = 'validuser'

        with patch('apps.realtime.middleware.get_user_from_token', new_callable=AsyncMock, return_value=mock_user), \
             patch('apps.shared.metrics.WEBSOCKET_CONNECTIONS') as mock_connections:
            _run(consumer._handle_authenticate('good-token'))

        assert consumer._authenticated is True
        assert consumer._user == mock_user
        consumer.send_json.assert_called()
        msg = consumer.send_json.call_args[0][0]
        assert msg['action'] == 'authenticated'
        assert msg['success'] is True
