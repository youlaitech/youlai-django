"""实时消息服务。

通过 channel layer 向订阅主题的连接广播，或向指定用户的连接推送。
"""

import logging
from datetime import datetime, timezone as dt_timezone
from typing import Any, List

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.message import DictChangeEvent, OnlineUserDTO, RealtimeEvents, RealtimeMessage, RealtimeTopics
from apps.message.registry import get_realtime_registry

logger = logging.getLogger(__name__)


class RealtimeService:
    """实时消息服务。"""

    def __init__(self):
        self.registry = get_realtime_registry()

    def send_dict_change(self, dict_code: str) -> None:
        """广播字典变更，前端据此刷新缓存。"""
        if not dict_code:
            return
        self.broadcast(RealtimeTopics.DICT, RealtimeEvents.DICT_CHANGED, {"dictCode": dict_code})

    def send_to_user(self, user_id, event_name: str, data: Any) -> None:
        """向指定用户的全部连接推送消息。"""
        self._group_send(f"user_{user_id}", RealtimeMessage.create(event_name, data))

    def broadcast(self, topic: str, event_name: str, data: Any) -> None:
        """向订阅了该主题的全部连接广播消息。"""
        self._group_send(f"topic_{topic}", RealtimeMessage.create(event_name, data))

    def get_online_users(self) -> List[OnlineUserDTO]:
        """获取在线用户列表。"""
        return self.registry.get_online_users()

    def get_online_user_count(self) -> int:
        """获取在线用户数。"""
        return self.registry.get_online_user_count()

    def presence_snapshot(self) -> dict:
        """生成在线状态快照。"""
        now = datetime.now(dt_timezone.utc)
        return {
            "onlineUsers": self.registry.get_online_user_count(),
            "onlineConnections": self.registry.get_total_connection_count(),
            "nodeId": self.registry.get_node_id(),
            "observedAt": now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z",
        }

    def broadcast_presence(self) -> None:
        """广播在线状态快照。"""
        self.broadcast(
            RealtimeTopics.PRESENCE,
            RealtimeEvents.PRESENCE_SNAPSHOT,
            self.presence_snapshot(),
        )

    def _group_send(self, group: str, message: dict) -> None:
        """向 channel layer 的分组发送消息。"""
        layer = get_channel_layer()
        if layer is None:
            logger.warning("[Realtime] 未配置 channel layer，消息丢弃")
            return
        try:
            async_to_sync(layer.group_send)(group, {"type": "realtime.message", "message": message})
        except Exception as e:
            logger.warning(f"[Realtime] 广播失败: {e}")


# 全局单例
_realtime_service = None


def get_realtime_service() -> RealtimeService:
    """获取全局实时消息服务实例。"""
    global _realtime_service
    if _realtime_service is None:
        _realtime_service = RealtimeService()
    return _realtime_service
