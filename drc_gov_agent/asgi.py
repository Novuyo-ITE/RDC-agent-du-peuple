"""
ASGI config for drc_gov_agent project.
Exposes the ASGI callable as a module-level variable named ``application``.
Supports HTTP and WebSockets for real-time streaming and voice interactions.
"""

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'drc_gov_agent.settings')
django_asgi_app = get_asgi_application()

try:
    from apps.voice.routing import websocket_urlpatterns
except ImportError:
    websocket_urlpatterns = []

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})

