"""
ASGI config for the SequoIA platform.

Supports both HTTP and WebSocket protocols via Django Channels.
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sequoia.settings.prod")

# Initialize Django ASGI application early to populate the app registry
django_asgi_app = get_asgi_application()

# Import routing after Django setup
from apps.realtime.middleware import JWTAuthMiddleware  # noqa: E402
from apps.realtime.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JWTAuthMiddleware(URLRouter(websocket_urlpatterns)),
    }
)
