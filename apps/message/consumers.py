"""实时连接消费者。

握手只接受一次性票据，不在连接地址中传递访问令牌。
"""

import asyncio
import json
import logging
import uuid
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from apps.auth.utils.redis_token_authentication import RedisTokenManager
from apps.message import RealtimeEvents, RealtimeMessage, RealtimeTopics
from apps.message.registry import get_realtime_registry
from apps.message.service import get_realtime_service
from apps.message.ticket_service import consume_ticket

logger = logging.getLogger(__name__)

# 心跳间隔与超时
PING_INTERVAL_SECONDS = 25
PONG_TIMEOUT_SECONDS = 60

MAX_MESSAGE_BYTES = 16 * 1024


class RealtimeConsumer(AsyncWebsocketConsumer):
    """实时连接。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_id = None
        self.topics = frozenset()
        self._pending_ping_id = None
        self._last_pong_at = 0.0
        self._heartbeat_task = None

    async def connect(self):
        """消费票据后接受连接，加入主题分组与用户分组。"""
        grant = await self._resolve_grant()
        if grant is None:
            logger.info("[Realtime] 握手票据无效或已使用")
            await self.close(code=4001)
            return

        self.user_id = str(grant["user_id"])
        self.topics = frozenset(t for t in grant.get("topics", []) if t in RealtimeTopics.SUPPORTED)

        await self.accept()

        for topic in self.topics:
            await self.channel_layer.group_add(f"topic_{topic}", self.channel_name)
        await self.channel_layer.group_add(f"user_{self.user_id}", self.channel_name)

        await database_sync_to_async(get_realtime_registry().user_connected)(self.user_id, self.channel_name)

        await self._send(
            RealtimeEvents.CONNECTION_READY,
            {"heartbeatTimeoutMs": RealtimeEvents.HEARTBEAT_TIMEOUT_MS},
        )

        # 连接数变化后广播在线状态快照
        await database_sync_to_async(get_realtime_service().broadcast_presence)()

        self._last_pong_at = asyncio.get_event_loop().time()
        self._heartbeat_task = asyncio.create_task(self._heartbeat())

    async def disconnect(self, close_code):
        """退出分组并注销连接。"""
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

        if self.user_id is None:
            return

        for topic in self.topics:
            await self.channel_layer.group_discard(f"topic_{topic}", self.channel_name)
        await self.channel_layer.group_discard(f"user_{self.user_id}", self.channel_name)
        await database_sync_to_async(get_realtime_registry().remove_connection)(self.channel_name)
        await database_sync_to_async(get_realtime_service().broadcast_presence)()

    async def receive(self, text_data=None, bytes_data=None):
        """只处理心跳响应，其余消息忽略。"""
        if not text_data:
            return
        if len(text_data.encode("utf-8")) > MAX_MESSAGE_BYTES:
            await self.close(code=4009)
            return
        try:
            payload = json.loads(text_data)
        except ValueError:
            await self.close(code=4007)
            return

        if not isinstance(payload, dict) or payload.get("version") != 1:
            return
        if payload.get("type") != "heartbeat.pong":
            return

        ping_id = (payload.get("payload") or {}).get("pingId")
        if ping_id and ping_id == self._pending_ping_id:
            self._pending_ping_id = None
            self._last_pong_at = asyncio.get_event_loop().time()

    async def realtime_message(self, event):
        """转发 channel layer 投递的消息。"""
        await self.send(json.dumps(event["message"]))

    async def _send(self, type_: str, payload=None):
        """按协议封装后发送。"""
        await self.send(json.dumps(RealtimeMessage.create(type_, payload)))

    async def _heartbeat(self):
        """定时发送心跳，超时未响应则断开。"""
        loop = asyncio.get_event_loop()
        try:
            while True:
                await asyncio.sleep(1)
                now = loop.time()

                if now - self._last_pong_at >= PONG_TIMEOUT_SECONDS:
                    logger.info("[Realtime] 用户 %s 的连接心跳超时", self.user_id)
                    await self.close(code=4011)
                    return

                if self._pending_ping_id is None and now - self._last_pong_at >= PING_INTERVAL_SECONDS:
                    self._pending_ping_id = uuid.uuid4().hex
                    await self.send(json.dumps({
                        "version": 1,
                        "id": self._pending_ping_id,
                        "type": "heartbeat.ping",
                        "payload": {},
                    }))
        except asyncio.CancelledError:
            return

    async def _resolve_grant(self):
        """取出并消费查询参数中的票据，只允许 ticket 一个参数。"""
        query = parse_qs(self.scope.get("query_string", b"").decode("utf-8"))
        tickets = query.get("ticket")
        if len(query) != 1 or not tickets:
            return None

        grant = await database_sync_to_async(consume_ticket)(tickets[0])
        if grant is None:
            return None

        # 复核访问凭证，避免票据签发后令牌失效仍能建立连接
        valid = await database_sync_to_async(_validate_access_token)(grant.get("access_token", ""))
        if not valid:
            logger.warning("[Realtime] 握手票据对应的访问凭证已失效")
            return None

        return grant


def _validate_access_token(access_token: str) -> bool:
    """校验访问令牌是否仍然有效"""
    if not access_token:
        return False
    try:
        return RedisTokenManager().validate_token(access_token)
    except Exception:
        logger.warning("[Realtime] 访问凭证复核异常")
        return False
