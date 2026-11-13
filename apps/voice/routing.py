"""
WebSocket routing for Voice streaming.
"""
from django.urls import re_path
from apps.voice import consumers

websocket_urlpatterns = [
    re_path(r'^ws/voice/$', consumers.VoiceAssistantConsumer.as_asgi()),
]

