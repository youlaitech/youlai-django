"""消息视图层。

提供实时连接票据与在线状态查询接口。
"""

import logging
from typing import Optional

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.message import RealtimeTopics
from apps.message.service import get_realtime_service
from apps.message.ticket_service import create_ticket
from core.response import success, error

logger = logging.getLogger(__name__)

# 票据接口地址与 WebSocket 地址保持一致的前缀
BEARER_PREFIX = "Bearer "


class RealtimeTicketView(APIView):
    """实时连接票据接口。"""
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["13. 消息服务"], description="签发一次性握手票据，30 秒内有效且只能使用一次")
    def post(self, request):
        """校验访问凭证与订阅主题后签发票据。"""
        topics = request.data.get("topics")
        if not isinstance(topics, list) or RealtimeTopics.NOTICE not in topics:
            return error("订阅主题须包含 notice")

        unsupported = [t for t in topics if t not in RealtimeTopics.SUPPORTED]
        if unsupported:
            return error(f"不支持的订阅主题：{', '.join(unsupported)}")

        access_token = self._read_access_token(request)
        if not access_token:
            return error("缺少 Bearer 访问凭证")

        ticket = create_ticket(request.user.id, access_token, topics)
        return success({"ticket": ticket})

    @staticmethod
    def _read_access_token(request) -> Optional[str]:
        """从 Authorization 头读取访问令牌。"""
        header = request.META.get("HTTP_AUTHORIZATION", "")
        if not header.startswith(BEARER_PREFIX):
            return None
        token = header[len(BEARER_PREFIX):].strip()
        return token or None


class RealtimePresenceView(APIView):
    """在线状态接口。"""
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["13. 消息服务"], description="获取当前在线状态")
    def get(self, request):
        """返回当前节点的在线状态快照。"""
        return success(get_realtime_service().presence_snapshot())
