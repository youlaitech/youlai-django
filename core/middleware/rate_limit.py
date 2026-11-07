import logging
import time
import uuid

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django_redis import get_redis_connection

logger = logging.getLogger(__name__)

LUA_SLIDING_WINDOW = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local member = ARGV[3]
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
redis.call('ZADD', key, now, member)
redis.call('PEXPIRE', key, window + 1000)
return redis.call('ZCARD', key)
"""


class RateLimitMiddleware:
    """IP 滑动窗口限流中间件"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        if request.method == "OPTIONS":
            return self.get_response(request)

        if not getattr(settings, "RATE_LIMIT_IP_ENABLED", True):
            return self.get_response(request)

        ip = self._get_client_ip(request)
        if ip:
            limit, window_sec, count = self._sliding_window(ip)
            if count is not None and count > limit:
                # 滑动窗口内请求数已超过上限
                response = JsonResponse(
                    {"code": "A0502", "msg": "请求并发数超出限制", "data": None},
                    status=429,
                )
                response["X-RateLimit-Limit"] = str(limit)
                response["X-RateLimit-Remaining"] = "0"
                response["X-RateLimit-Reset"] = str(int(time.time()) + window_sec)
                response["Retry-After"] = str(window_sec)
                return response

            response = self.get_response(request)
            # 正常放行时回写限流状态头；Redis 异常（count 为 None）时不写头
            if count is not None:
                remaining = max(0, limit - count)
                response["X-RateLimit-Limit"] = str(limit)
                response["X-RateLimit-Remaining"] = str(remaining)
                response["X-RateLimit-Reset"] = str(int(time.time()) + window_sec)
            return response

        return self.get_response(request)

    @staticmethod
    def _get_client_ip(request: HttpRequest) -> str:
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "")

    def _sliding_window(self, ip: str):
        """基于 Redis ZSet 的滑动窗口计数。

        返回 (窗口内允许的最大请求数, 滑动窗口大小（秒）, 窗口内当前请求数)。
        Redis 异常时返回 (limit, window_sec, None)，表示无法计数、放行且不写头。
        """
        limit = getattr(settings, "RATE_LIMIT_IP_LIMIT", 1000)
        window_sec = getattr(settings, "RATE_LIMIT_IP_WINDOW", 60)
        try:
            redis_conn = get_redis_connection("default")
            key = f"rate_limit:ip:{ip}"
            now_ms = int(time.time() * 1000)
            count = redis_conn.eval(
                LUA_SLIDING_WINDOW, 1, key,
                now_ms, window_sec * 1000, str(uuid.uuid4())
            )
            return limit, window_sec, int(count)
        except Exception:
            logger.warning("限流检查异常，跳过")
            return limit, window_sec, None
