"""消息模块相关类型定义。"""

import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict


class RealtimeEvents:
    """实时消息类型，与 vue3-element-admin 的协议保持一致"""

    CONNECTION_READY = "connection.ready"
    HEARTBEAT_PING = "heartbeat.ping"
    NOTICE_CHANGED = "notice.changed"
    DICT_CHANGED = "dict.changed"
    PRESENCE_SNAPSHOT = "presence.snapshot"

    # 心跳超时时间（毫秒），与前端协议保持一致
    HEARTBEAT_TIMEOUT_MS = 60000


class RealtimeTopics:
    """实时订阅主题。"""
    NOTICE = "notice"
    DICT = "dict"
    PRESENCE = "presence"

    # 当前支持的全部主题，订阅须包含 notice
    SUPPORTED = frozenset({NOTICE, DICT, PRESENCE})


class RealtimeMessage:
    @staticmethod
    def create(type_: str, payload: Any = None) -> Dict[str, Any]:
        """生成带协议版本和唯一标识的服务端消息。"""
        return {
            "version": 1,
            "id": uuid.uuid4().hex,
            "type": type_,
            "payload": payload,
        }


@dataclass
class DictChangeEvent:
    """字典变更事件DTO。"""
    dict_code: str
    timestamp: int

    def __init__(self, dict_code: str):
        self.dict_code = dict_code
        self.timestamp = int(time.time() * 1000)

    def to_dict(self):
        return {
            "dictCode": self.dict_code,
            "timestamp": self.timestamp,
        }


@dataclass
class OnlineUserDTO:
    """在线用户信息DTO。"""
    username: str
    session_count: int
    login_time: float

    def to_dict(self):
        return {
            "username": self.username,
            "sessionCount": self.session_count,
            "loginTime": self.login_time,
        }
