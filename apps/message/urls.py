"""消息模块路由配置。"""

from django.urls import path

from apps.message.views import RealtimeTicketView, RealtimePresenceView

urlpatterns = [
    path("tickets", RealtimeTicketView.as_view(), name="realtime-tickets"),
    path("presence", RealtimePresenceView.as_view(), name="realtime-presence"),
]
