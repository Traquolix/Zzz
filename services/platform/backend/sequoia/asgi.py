"""
ASGI config for the SequoIA platform.

Supports both HTTP and WebSocket protocols via Django Channels.
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sequoia.settings.prod')

# Initialize Django ASGI application early to populate the app registry
django_asgi_app = get_asgi_application()

# Import routing after Django setup
from apps.realtime.middleware import JWTAuthMiddleware  # noqa: E402
from apps.realtime.routing import websocket_urlpatterns  # noqa: E402

_base_application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': JWTAuthMiddleware(URLRouter(websocket_urlpatterns)),
})


class SimulationLifespanWrapper:
    """
    ASGI wrapper that starts the simulation as a background task
    within Daphne's event loop. This ensures InMemoryChannelLayer works
    correctly since both simulation and WebSocket consumers share
    the same asyncio event loop.
    """

    def __init__(self, app):
        self.app = app
        self.simulation_task = None
        self.simulation_started = False

    async def __call__(self, scope, receive, send):
        # Start simulation on first WebSocket connection
        if scope['type'] == 'websocket' and not self.simulation_started:
            await self._maybe_start_simulation()

        return await self.app(scope, receive, send)

    async def _maybe_start_simulation(self):
        """Start simulation if configured and not already running."""
        import asyncio
        from asgiref.sync import sync_to_async
        from django.conf import settings

        if self.simulation_started:
            return

        # Check if simulation should auto-start
        if not getattr(settings, 'REALTIME_AUTO_START_SIMULATION', False):
            return

        self.simulation_started = True

        # Import here to avoid circular imports
        from apps.realtime.simulation import run_simulation_loop
        from apps.realtime.management.commands.run_realtime import Command

        # Load fiber and infrastructure data (use sync_to_async for ORM calls)
        cmd = Command()
        fibers = cmd._load_fibers()  # File-based, no ORM
        infrastructure = await sync_to_async(cmd._load_infrastructure)()

        if fibers:
            # Start simulation as a background task in this event loop
            self.simulation_task = asyncio.create_task(
                run_simulation_loop(fibers, infrastructure)
            )


# Export wrapped application
application = SimulationLifespanWrapper(_base_application)
