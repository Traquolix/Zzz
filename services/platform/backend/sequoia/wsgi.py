"""
WSGI config for the SequoIA platform.

Used for production HTTP-only deployments (without WebSocket support).
For WebSocket support, use the ASGI configuration instead.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sequoia.settings.prod")

application = get_wsgi_application()
