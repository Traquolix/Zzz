"""
ASGI config for the SequoIA platform.

Supports both HTTP and WebSocket protocols via Django Channels.

Simulation lifecycle is managed by SimulationManager, which starts
the simulation as a background task on the first ASGI scope. If the
simulation fails to start or crashes, WebSocket connections still work
— they just won't receive simulation data.
"""

import asyncio
import concurrent.futures
import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sequoia.settings.prod")

# Explicit thread pool for Django's sync-to-async operations.
# Default (~36 on 4-core) is too small when many concurrent requests
# hit synchronous views or ORM calls. Configurable via env var.
_THREAD_POOL_SIZE = int(os.environ.get("DJANGO_THREAD_POOL_SIZE", "40"))
asyncio.get_event_loop().set_default_executor(
    concurrent.futures.ThreadPoolExecutor(
        max_workers=_THREAD_POOL_SIZE,
        thread_name_prefix="django-asgi",
    )
)

# Initialize Django ASGI application early to populate the app registry
django_asgi_app = get_asgi_application()

# Initialize OpenTelemetry after Django setup (needs app registry for DjangoInstrumentor)
from apps.shared.otel_setup import init_otel  # noqa: E402

init_otel()

# Import routing after Django setup
from apps.realtime.middleware import JWTAuthMiddleware  # noqa: E402
from apps.realtime.routing import websocket_urlpatterns  # noqa: E402

_base_application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JWTAuthMiddleware(URLRouter(websocket_urlpatterns)),
    }
)


class SimulationLifespanWrapper:
    """
    ASGI wrapper that starts the simulation via SimulationManager
    on the first incoming scope.

    Unlike the previous implementation:
    - Simulation failure does NOT block connections
    - Start is attempted once and supervised (restarts not automatic)
    - Status is observable via SimulationManager.instance().health()
    """

    def __init__(self, app):
        self.app = app
        self._init_attempted = False

    async def __call__(self, scope, receive, send):
        if not self._init_attempted:
            self._init_attempted = True
            from apps.realtime.simulation_manager import SimulationManager

            await SimulationManager.instance().start_if_configured()

        return await self.app(scope, receive, send)


# Export wrapped application
application = SimulationLifespanWrapper(_base_application)
