"""DRF 全局异常处理入口。"""

import logging
from typing import Any

from django.http import Http404
from django.db.utils import OperationalError, ProgrammingError, IntegrityError
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    NotAuthenticated,
    PermissionDenied,
    Throttled,
    ValidationError,
)
from rest_framework.views import exception_handler as drf_exception_handler

from core.exceptions.business import BusinessException

logger = logging.getLogger(__name__)


def _stringify_error_detail(detail: Any) -> str:
    """从 DRF 的 detail 中提取错误消息字符串。"""
    if detail is None:
        return ""
    if isinstance(detail, str):
        return detail
    if isinstance(detail, (list, tuple)):
        return _stringify_error_detail(detail[0]) if detail else ""
    if isinstance(detail, dict):
        return _stringify_error_detail(detail.get("detail", ""))
    return str(detail)


def global_exception_handler(exc: Exception, context: dict) -> Any:
    """DRF 全局异常处理，统一转成 {code, msg, data} 格式返回。"""
    from core.response import error
    if isinstance(exc, BusinessException):
        return error(exc.msg, code=exc.code, status=exc.status, data=exc.data)

    resp = drf_exception_handler(exc, context)

    if resp is None:
        # DRF 没处理，检查是不是数据库只读之类的错误
        request = context.get("request")
        method = getattr(request, "method", "") if request is not None else ""

        if method and method.upper() not in {"GET", "HEAD", "OPTIONS"}:
            err_str = str(exc)
            demo_markers = (
                "read-only",
                "read only",
                "readonly",
                "command denied",
                "access denied",
                "permission denied",
                "denied",
            )
            if isinstance(exc, (OperationalError, ProgrammingError, IntegrityError)) and any(
                marker in err_str.lower() for marker in demo_markers
            ):
                return error(
                    "演示系统，请本地部署后关闭演示功能使用",
                    code="A0402",
                    status=403,
                )

        if isinstance(exc, (OperationalError, ProgrammingError)):
            err_str = str(exc)
            if "Unknown column" in err_str or "unknown column" in err_str:
                logger.exception("表字段缺失 (Unknown column)", exc_info=exc)
                return error(
                    "数据库表结构与模型不一致，请重新导入最新 SQL 文件",
                    status=500,
                )
        logger.exception("未处理的异常", exc_info=exc)
        return error("系统执行出错", status=500)

    status_code = getattr(resp, "status_code", 500)
    detail = getattr(resp, "data", None)

    # 业务层会抛 ValidationError({"code": "xxx", "msg": "xxx"})，直接透传
    if isinstance(exc, ValidationError):
        if isinstance(detail, dict) and "code" in detail and "msg" in detail:
            code_value = detail.get("code")
            if isinstance(code_value, list):
                code_value = code_value[0] if code_value else "A0400"
            status = 401 if code_value == "A0231" else 200
            return error(detail.get("msg"), code=code_value, status=status)
        msg = _stringify_error_detail(detail) or "用户请求参数错误"
        return error(msg, status=200)

    if isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        msg = _stringify_error_detail(detail) or "访问未授权"
        if msg in {
            "Not authenticated",
            "Authentication credentials were not provided.",
            "Authentication credentials were not provided",
        }:
            msg = "未认证，请先登录"
        if msg in {"Invalid token.", "Invalid token", "Token is invalid or expired"}:
            msg = "无效的访问令牌"
        return error(msg, status=401)

    if isinstance(exc, PermissionDenied):
        msg = _stringify_error_detail(detail) or "权限不足"
        if msg in {"Permission denied", "Permission denied."}:
            msg = "权限不足"
        return error(msg, status=403)

    if isinstance(exc, Http404):
        msg = _stringify_error_detail(detail) or "接口不存在"
        return error(msg, status=404)

    if isinstance(exc, Throttled):
        msg = _stringify_error_detail(detail) or "请求次数超出限制"
        return error(msg, status=429)

    if isinstance(exc, APIException):
        msg = _stringify_error_detail(detail) or "请求处理失败"
        return error(msg, status=200)

    msg = _stringify_error_detail(detail) or str(exc) or "请求处理失败"
    return error(msg, status=200)
