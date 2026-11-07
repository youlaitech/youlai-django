"""实时会话注册表。

维护连接所属的用户与连接时间，支持多设备同时登录。跨进程广播由 channel layer 负责，
本表仅用于在线状态统计，统计范围为当前进程。
"""

from __future__ import annotations

import time
from threading import Lock
from typing import Dict, List, Optional

import uuid

from apps.message import OnlineUserDTO


class RealtimeSessionRegistry:
    """实时会话注册表。"""

    def __init__(self):
        # 节点标识，进程内固定，用于前端区分多节点部署
        self._node_id = uuid.uuid4().hex
        # 用户连接映射表：用户ID -> 连接名集合
        self._user_connections: Dict[str, set] = {}
        # 连接时间映射表：连接名 -> 建立时间
        self._connection_time: Dict[str, float] = {}
        # 线程锁
        self._lock = Lock()

    def user_connected(self, user_id: str, channel_name: str) -> None:
        """用户上线（连接建立）。"""
        with self._lock:
            self._user_connections.setdefault(user_id, set()).add(channel_name)
            self._connection_time[channel_name] = time.time()

    def remove_connection(self, channel_name: str) -> None:
        """移除指定连接。"""
        with self._lock:
            self._connection_time.pop(channel_name, None)
            for user_id, connections in list(self._user_connections.items()):
                if channel_name in connections:
                    connections.discard(channel_name)
                    if not connections:
                        self._user_connections.pop(user_id, None)
                    break

    def get_online_user_count(self) -> int:
        """获取在线用户数量。"""
        return len(self._user_connections)

    def get_total_connection_count(self) -> int:
        """获取在线连接总数，多标签页会重复计数。"""
        return len(self._connection_time)

    def get_node_id(self) -> str:
        """获取节点标识。"""
        return self._node_id

    def get_online_users(self) -> List[OnlineUserDTO]:
        """获取在线用户列表，登录时间取该用户最早的连接时间。"""
        result = []
        with self._lock:
            for user_id, connections in self._user_connections.items():
                connect_times = [t for t in (self._connection_time.get(c) for c in connections) if t]
                result.append(OnlineUserDTO(
                    username=user_id,
                    session_count=len(connections),
                    login_time=min(connect_times) if connect_times else time.time(),
                ))
        return result

    def clear(self) -> None:
        """清空全部连接记录。"""
        with self._lock:
            self._user_connections.clear()
            self._connection_time.clear()


# 全局单例
_realtime_registry: Optional[RealtimeSessionRegistry] = None


def get_realtime_registry() -> RealtimeSessionRegistry:
    """获取全局实时会话注册表实例。"""
    global _realtime_registry
    if _realtime_registry is None:
        _realtime_registry = RealtimeSessionRegistry()
    return _realtime_registry
