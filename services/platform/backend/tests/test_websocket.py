"""
Tests for the RealtimeConsumer WebSocket consumer.

Uses channels.testing.WebsocketCommunicator to test subscribe,
unsubscribe, ping/pong, and channel validation behavior.
"""

import pytest
from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from django.urls import path

from apps.realtime.consumers import RealtimeConsumer
from tests.factories import OrganizationFactory, UserFactory


pytestmark = pytest.mark.django_db(transaction=True)


def _make_application():
    """Build a minimal ASGI application with just the RealtimeConsumer."""
    return URLRouter([
        path('ws/', RealtimeConsumer.as_asgi()),
    ])


def _make_authenticated_communicator(user):
    """
    Create a WebsocketCommunicator with an authenticated user in scope.

    Bypasses JWTAuthMiddleware by injecting the user directly into scope,
    which is the standard Channels testing pattern.
    """
    application = _make_application()
    communicator = WebsocketCommunicator(application, '/ws/')
    communicator.scope['user'] = user
    return communicator


@pytest.fixture
def ws_user():
    """Create a regular authenticated user for WebSocket tests."""
    org = OrganizationFactory()
    return UserFactory(organization=org, username='ws_user')


class TestWebSocketConnect:
    """Test WebSocket connection behavior."""

    @pytest.mark.asyncio
    async def test_authenticated_user_can_connect(self, ws_user):
        communicator = _make_authenticated_communicator(ws_user)
        connected, _ = await communicator.connect()
        assert connected is True
        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_unauthenticated_user_rejected(self):
        """Anonymous users should have the connection closed."""
        from django.contrib.auth.models import AnonymousUser

        application = _make_application()
        communicator = WebsocketCommunicator(application, '/ws/')
        communicator.scope['user'] = AnonymousUser()
        connected, code = await communicator.connect()
        # Consumer calls self.close() for unauthenticated users
        assert connected is False


class TestSubscribe:
    """Test channel subscription."""

    @pytest.mark.asyncio
    async def test_subscribe_allowed_channel(self, ws_user):
        """Subscribing to an allowed channel should succeed silently."""
        communicator = _make_authenticated_communicator(ws_user)
        connected, _ = await communicator.connect()
        assert connected

        await communicator.send_json_to({
            'action': 'subscribe',
            'channel': 'detections',
        })

        # The subscribe action does not send a confirmation message back
        # (only broadcasts are sent). Verify no error by checking nothing
        # is sent within a short timeout.
        nothing = await communicator.receive_nothing(timeout=0.5)
        assert nothing is True

        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_subscribe_multiple_channels(self, ws_user):
        """Subscribing to multiple allowed channels should all succeed."""
        communicator = _make_authenticated_communicator(ws_user)
        connected, _ = await communicator.connect()
        assert connected

        for channel in ('detections', 'counts', 'shm_readings'):
            await communicator.send_json_to({
                'action': 'subscribe',
                'channel': channel,
            })

        # No error messages expected
        nothing = await communicator.receive_nothing(timeout=0.5)
        assert nothing is True

        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_subscribe_disallowed_channel(self, ws_user):
        """Subscribing to a channel not in ALLOWED_CHANNELS should be ignored."""
        communicator = _make_authenticated_communicator(ws_user)
        connected, _ = await communicator.connect()
        assert connected

        await communicator.send_json_to({
            'action': 'subscribe',
            'channel': 'secret_admin_channel',
        })

        # No response is sent for disallowed channels (just logged + ignored)
        nothing = await communicator.receive_nothing(timeout=0.5)
        assert nothing is True

        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_subscribe_empty_channel(self, ws_user):
        """A subscribe action without a channel field should be ignored."""
        communicator = _make_authenticated_communicator(ws_user)
        connected, _ = await communicator.connect()
        assert connected

        await communicator.send_json_to({
            'action': 'subscribe',
        })

        nothing = await communicator.receive_nothing(timeout=0.5)
        assert nothing is True

        await communicator.disconnect()


class TestUnsubscribe:
    """Test channel unsubscription."""

    @pytest.mark.asyncio
    async def test_unsubscribe_from_subscribed_channel(self, ws_user):
        """Unsubscribing from a previously subscribed channel should work."""
        communicator = _make_authenticated_communicator(ws_user)
        connected, _ = await communicator.connect()
        assert connected

        # Subscribe first
        await communicator.send_json_to({
            'action': 'subscribe',
            'channel': 'detections',
        })

        # Then unsubscribe
        await communicator.send_json_to({
            'action': 'unsubscribe',
            'channel': 'detections',
        })

        # No error
        nothing = await communicator.receive_nothing(timeout=0.5)
        assert nothing is True

        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_unsubscribe_from_unsubscribed_channel(self, ws_user):
        """Unsubscribing from a channel you never subscribed to should be harmless."""
        communicator = _make_authenticated_communicator(ws_user)
        connected, _ = await communicator.connect()
        assert connected

        await communicator.send_json_to({
            'action': 'unsubscribe',
            'channel': 'counts',
        })

        nothing = await communicator.receive_nothing(timeout=0.5)
        assert nothing is True

        await communicator.disconnect()


class TestPingPong:
    """Test the ping/pong heartbeat protocol."""

    @pytest.mark.asyncio
    async def test_ping_returns_pong(self, ws_user):
        """Sending a ping action should immediately return a pong response."""
        communicator = _make_authenticated_communicator(ws_user)
        connected, _ = await communicator.connect()
        assert connected

        await communicator.send_json_to({'action': 'ping'})

        response = await communicator.receive_json_from(timeout=2)
        assert response == {'action': 'pong'}

        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_multiple_pings(self, ws_user):
        """Multiple pings should each return a pong."""
        communicator = _make_authenticated_communicator(ws_user)
        connected, _ = await communicator.connect()
        assert connected

        for _ in range(3):
            await communicator.send_json_to({'action': 'ping'})
            response = await communicator.receive_json_from(timeout=2)
            assert response == {'action': 'pong'}

        await communicator.disconnect()


class TestUnknownAction:
    """Test behavior with unknown or missing actions."""

    @pytest.mark.asyncio
    async def test_unknown_action_ignored(self, ws_user):
        """An unknown action should be silently ignored."""
        communicator = _make_authenticated_communicator(ws_user)
        connected, _ = await communicator.connect()
        assert connected

        await communicator.send_json_to({
            'action': 'unknown_action',
            'channel': 'detections',
        })

        nothing = await communicator.receive_nothing(timeout=0.5)
        assert nothing is True

        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_empty_message_ignored(self, ws_user):
        """An empty JSON object should be silently ignored."""
        communicator = _make_authenticated_communicator(ws_user)
        connected, _ = await communicator.connect()
        assert connected

        await communicator.send_json_to({})

        nothing = await communicator.receive_nothing(timeout=0.5)
        assert nothing is True

        await communicator.disconnect()


class TestBroadcastMessage:
    """Test that broadcast messages are delivered to subscribed consumers."""

    @pytest.mark.asyncio
    async def test_broadcast_received_after_subscribe(self, ws_user):
        """
        After subscribing to a channel, broadcasts to that channel's group
        should be delivered to the consumer.
        """
        communicator = _make_authenticated_communicator(ws_user)
        connected, _ = await communicator.connect()
        assert connected

        # Subscribe to detections
        await communicator.send_json_to({
            'action': 'subscribe',
            'channel': 'detections',
        })

        # Wait a moment for the subscription to be processed
        await communicator.receive_nothing(timeout=0.2)

        # Send a broadcast via the channel layer (org-scoped group name)
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        org_id = str(ws_user.organization_id)
        await channel_layer.group_send(f'realtime_detections_org_{org_id}', {
            'type': 'broadcast.message',
            'channel': 'detections',
            'data': [{'speed': 60, 'channel': 5}],
        })

        response = await communicator.receive_json_from(timeout=2)
        assert response['channel'] == 'detections'
        assert response['data'] == [{'speed': 60, 'channel': 5}]

        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_broadcast_not_received_after_unsubscribe(self, ws_user):
        """
        After unsubscribing from a channel, broadcasts to that channel
        should NOT be delivered.
        """
        communicator = _make_authenticated_communicator(ws_user)
        connected, _ = await communicator.connect()
        assert connected

        # Subscribe then unsubscribe
        await communicator.send_json_to({
            'action': 'subscribe',
            'channel': 'counts',
        })
        await communicator.receive_nothing(timeout=0.2)

        await communicator.send_json_to({
            'action': 'unsubscribe',
            'channel': 'counts',
        })
        await communicator.receive_nothing(timeout=0.2)

        # Send a broadcast (org-scoped group name)
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        org_id = str(ws_user.organization_id)
        await channel_layer.group_send(f'realtime_counts_org_{org_id}', {
            'type': 'broadcast.message',
            'channel': 'counts',
            'data': [{'count': 10}],
        })

        # Should not receive anything
        nothing = await communicator.receive_nothing(timeout=1)
        assert nothing is True

        await communicator.disconnect()
