"""扫码登录视图。

generate/status/login 三个端点公开（permission_classes = [AllowAny]），scan/confirm/cancel
需要 APP 端登录态：从 request.user 取当前用户 ID，未带令牌时 request.user 为匿名用户，直接拒绝。
"""

import json
import uuid

from django_redis import get_redis_connection
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.viewsets import ViewSet

from core.response import error, success
from django.contrib.auth import get_user_model

from apps.system.users.serializers import UserInfoSerializer
from .utils.auth_utils import build_token_response

User = get_user_model()

# 扫码登录状态
STATUS_WAITING = "WAITING"
STATUS_SCANNED = "SCANNED"
STATUS_CONFIRMED = "CONFIRMED"
STATUS_LOGGED_IN = "LOGGED_IN"
STATUS_CANCELED = "CANCELED"
STATUS_EXPIRED = "EXPIRED"

# 扫码登录业务错误码
QR_CODE_NOT_FOUND = "A0250"
QR_CODE_STATUS_ILLEGAL = "A0251"
QR_CODE_USER_MISMATCH = "A0252"
QR_CODE_ALREADY_USED = "A0253"

# 票据默认有效期（秒），二维码在此时间内未走完流程即由 Redis TTL 自动清理
QR_CODE_TTL = 300
# 状态流转时若 Redis 剩余 TTL 小于该值，补足到此值，避免临界点票据在下一步操作前被清掉
QR_CODE_MIN_REMAIN = 30
# 扫码登录票据 Redis Key 模板：auth:qr_code:{ticket}
QR_CODE_KEY = "auth:qr_code:{}"


def _client_ip(request):
    """从请求头提取客户端 IP，兼容反向代理：X-Forwarded-For → X-Real-IP → REMOTE_ADDR。"""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    xrip = request.META.get("HTTP_X_REAL_IP", "")
    if xrip:
        return xrip.strip()
    return request.META.get("REMOTE_ADDR", "")


def _current_user_id(request):
    """返回当前登录用户 ID；未登录（匿名）返回 None。"""
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return user.id


def _mask_nickname(nickname):
    """昵称脱敏：保留首尾字符，中间以 * 填充。"""
    if not nickname:
        return ""
    chars = list(nickname)
    n = len(chars)
    if n <= 1:
        return nickname
    if n == 2:
        return chars[0] + "*"
    return chars[0] + "*" * (n - 2) + chars[-1]


def get_auth_info_by_user_id(user_id):
    """按用户 ID 取认证信息（含 username/nickname/avatar/roles/perms）。"""
    user = User.objects.get(id=user_id, is_deleted=0)
    return UserInfoSerializer(user).data


def _qr_key(ticket):
    return QR_CODE_KEY.format(ticket)


def _load_context(redis_conn, ticket):
    """读取票据上下文；票据为空、不存在或已过期都视为 QR_CODE_NOT_FOUND。"""
    if not ticket:
        return None
    raw = redis_conn.get(_qr_key(ticket))
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def _save_context(redis_conn, ctx, ttl):
    redis_conn.setex(_qr_key(ctx["ticket"]), ttl, json.dumps(ctx, ensure_ascii=False))


def _remain_seconds(redis_conn, ticket):
    ttl = redis_conn.ttl(_qr_key(ticket))
    return ttl if isinstance(ttl, int) and ttl > 0 else 0


def _refresh_ttl(redis_conn, ticket):
    remain = _remain_seconds(redis_conn, ticket)
    return QR_CODE_MIN_REMAIN if remain < QR_CODE_MIN_REMAIN else remain


def _to_status_vo(ctx, expire_seconds):
    vo = {
        "ticket": ctx["ticket"],
        "status": ctx["status"],
        "nickname": None,
        "avatar": None,
        "expireSeconds": expire_seconds,
    }
    # WAITING 阶段谁都能查状态，此时不能泄露用户信息；扫码/确认后才回传脱敏昵称与头像
    if ctx["status"] in (STATUS_SCANNED, STATUS_CONFIRMED):
        vo["nickname"] = _mask_nickname(ctx.get("nickname") or "")
        vo["avatar"] = ctx.get("avatar")
    return vo


@extend_schema(tags=["01.认证中心"])
class QrCodeViewSet(ViewSet):
    """扫码登录视图。"""

    permission_classes = [AllowAny]

    @extend_schema(summary="生成扫码登录票据")
    def generate(self, request, *args, **kwargs):
        redis_conn = get_redis_connection("default")
        ticket = uuid.uuid4().hex
        ctx = {
            "ticket": ticket,
            "status": STATUS_WAITING,
            "userId": None,
            "nickname": None,
            "avatar": None,
            "createdAt": None,
            "scannedAt": None,
            "confirmedAt": None,
            "ip": _client_ip(request),
        }
        _save_context(redis_conn, ctx, QR_CODE_TTL)
        return success({"ticket": ticket, "expireSeconds": QR_CODE_TTL})

    @extend_schema(summary="查询扫码状态")
    def status(self, request, *args, **kwargs):
        ticket = request.query_params.get("ticket") or ""
        redis_conn = get_redis_connection("default")
        ctx = _load_context(redis_conn, ticket)
        if ctx is None:
            return error("扫码登录票据不存在或已过期", code=QR_CODE_NOT_FOUND, status=400)
        return success(_to_status_vo(ctx, _remain_seconds(redis_conn, ticket)))

    @extend_schema(summary="APP 标记已扫码")
    def scan(self, request, *args, **kwargs):
        user_id = _current_user_id(request)
        if user_id is None:
            return error("未登录或登录态已失效", code="A0230", status=401)
        ticket = (request.data or {}).get("ticket") or ""
        redis_conn = get_redis_connection("default")
        ctx = _load_context(redis_conn, ticket)
        if ctx is None:
            return error("扫码登录票据不存在或已过期", code=QR_CODE_NOT_FOUND, status=400)
        if ctx["status"] != STATUS_WAITING:
            return error("扫码登录状态非法", code=QR_CODE_STATUS_ILLEGAL, status=400)
        info = get_auth_info_by_user_id(user_id)
        ctx["userId"] = user_id
        ctx["nickname"] = info.get("nickname")
        ctx["avatar"] = info.get("avatar")
        ctx["status"] = STATUS_SCANNED
        _save_context(redis_conn, ctx, _refresh_ttl(redis_conn, ticket))
        return success(_to_status_vo(ctx, _remain_seconds(redis_conn, ticket)))

    @extend_schema(summary="APP 确认登录")
    def confirm(self, request, *args, **kwargs):
        user_id = _current_user_id(request)
        if user_id is None:
            return error("未登录或登录态已失效", code="A0230", status=401)
        ticket = (request.data or {}).get("ticket") or ""
        redis_conn = get_redis_connection("default")
        ctx = _load_context(redis_conn, ticket)
        if ctx is None:
            return error("扫码登录票据不存在或已过期", code=QR_CODE_NOT_FOUND, status=400)
        if ctx["status"] != STATUS_SCANNED:
            return error("扫码登录状态非法", code=QR_CODE_STATUS_ILLEGAL, status=400)
        if ctx.get("userId") != user_id:
            return error("扫码用户与确认用户不一致", code=QR_CODE_USER_MISMATCH, status=400)
        ctx["status"] = STATUS_CONFIRMED
        _save_context(redis_conn, ctx, _refresh_ttl(redis_conn, ticket))
        return success(_to_status_vo(ctx, _remain_seconds(redis_conn, ticket)))

    @extend_schema(summary="APP 取消登录")
    def cancel(self, request, *args, **kwargs):
        user_id = _current_user_id(request)
        if user_id is None:
            return error("未登录或登录态已失效", code="A0230", status=401)
        ticket = (request.data or {}).get("ticket") or ""
        redis_conn = get_redis_connection("default")
        ctx = _load_context(redis_conn, ticket)
        if ctx is None:
            return error("扫码登录票据不存在或已过期", code=QR_CODE_NOT_FOUND, status=400)
        if ctx["status"] not in (STATUS_WAITING, STATUS_SCANNED, STATUS_CONFIRMED):
            return error("扫码登录状态非法", code=QR_CODE_STATUS_ILLEGAL, status=400)
        if ctx["status"] != STATUS_WAITING and ctx.get("userId") is not None:
            if ctx.get("userId") != user_id:
                return error("扫码用户与取消用户不一致", code=QR_CODE_USER_MISMATCH, status=400)
        ctx["status"] = STATUS_CANCELED
        _save_context(redis_conn, ctx, _refresh_ttl(redis_conn, ticket))
        return success(_to_status_vo(ctx, _remain_seconds(redis_conn, ticket)))

    @extend_schema(summary="PC 端换取会话令牌")
    def login(self, request, *args, **kwargs):
        ticket = (request.data or {}).get("ticket") or ""
        redis_conn = get_redis_connection("default")
        ctx = _load_context(redis_conn, ticket)
        if ctx is None:
            return error("扫码登录票据不存在或已过期", code=QR_CODE_NOT_FOUND, status=400)
        if ctx["status"] != STATUS_CONFIRMED:
            return error("扫码登录状态非法", code=QR_CODE_STATUS_ILLEGAL, status=400)
        user_id = ctx.get("userId")
        try:
            user = User.objects.get(id=user_id, is_deleted=0)
        except User.DoesNotExist:
            return error("用户账户不存在", code="A0201", status=400)
        if getattr(user, "status", 1) == 0:
            return error("用户账户被冻结", code="A0202", status=400)
        token_data = build_token_response(user)
        # 换取令牌成功后立即把票据置为已使用（一次性），再次 login 会在状态校验处被拒，杜绝重放
        ctx["status"] = STATUS_LOGGED_IN
        remain = _remain_seconds(redis_conn, ticket)
        _save_context(redis_conn, ctx, remain if remain > QR_CODE_MIN_REMAIN else QR_CODE_MIN_REMAIN)
        return success(token_data)


__all__ = [
    "QrCodeViewSet",
]
