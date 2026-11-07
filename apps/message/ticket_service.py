"""实时连接一次性票据。

票据用访问令牌换取，握手时取出即删除，避免访问令牌出现在连接地址中。
"""

import hashlib
import json
import logging
import secrets
import string
from typing import Any, Dict, Optional

from django_redis import get_redis_connection
from django.utils import timezone

logger = logging.getLogger(__name__)

# 票据有效期较短，取到后需尽快完成握手
TICKET_TTL_SECONDS = 30
TICKET_LENGTH = 43
_TICKET_ALPHABET = string.ascii_letters + string.digits + "-_"
_TICKET_KEY_PREFIX = "realtime:ticket:"


def create_ticket(user_id: int, access_token: str, topics: list) -> str:
    """保存票据并返回，仅通过摘要构造 Redis 键。"""
    ticket = "".join(secrets.choice(_TICKET_ALPHABET) for _ in range(TICKET_LENGTH))
    grant = {
        "user_id": user_id,
        "access_token": access_token,
        "topics": list(topics),
        "expires_at": timezone.now().timestamp() + TICKET_TTL_SECONDS,
    }
    get_redis_connection("default").setex(
        _key(ticket),
        TICKET_TTL_SECONDS,
        json.dumps(grant),
    )
    return ticket


def consume_ticket(ticket: Optional[str]) -> Optional[Dict[str, Any]]:
    """原子取出并删除票据，票据无效、已使用或已过期返回 None。"""
    if not ticket or not (43 <= len(ticket) <= 256):
        return None
    if any(c not in _TICKET_ALPHABET for c in ticket):
        return None

    redis = get_redis_connection("default")
    raw = redis.getdel(_key(ticket))
    if not raw:
        return None

    try:
        grant = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning("[Realtime] 票据内容解析失败，按无效处理")
        return None

    if grant.get("expires_at", 0) <= timezone.now().timestamp():
        return None
    return grant


def _key(ticket: str) -> str:
    """Redis 键只保存票据摘要，不暴露可用于握手的票据。"""
    digest = hashlib.sha256(ticket.encode("utf-8")).hexdigest()
    return f"{_TICKET_KEY_PREFIX}{digest}"
