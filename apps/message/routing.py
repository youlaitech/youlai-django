"""实时连接的 WebSocket 路由。"""

from django.urls import re_path

from apps.message.consumers import RealtimeConsumer

websocket_urlpatterns = [
    re_path(r"^api/v1/realtime/ws$", RealtimeConsumer.as_asgi()),
]
