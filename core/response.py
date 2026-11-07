"""response 模块。

统一响应封装。
"""

from typing import Any, Optional

from rest_framework.response import Response


def _stringify_error_detail(detail: Any) -> str:
    """把 DRF 校验错误（可能是 str / list / dict）转成一个能直接返回的字符串。"""
    if detail is None:
        return ""

    if isinstance(detail, str):
        return detail

    if isinstance(detail, list):
        return "；".join(filter(None, [_stringify_error_detail(x) for x in detail]))

    if isinstance(detail, dict):
        # 兼容业务层抛出的 {"code": "xxx", "msg": "xxx"} 格式
        if "msg" in detail and isinstance(detail.get("msg"), str):
            return detail["msg"]
        parts: list[str] = []
        for k, v in detail.items():
            v_str = _stringify_error_detail(v)
            if not v_str:
                continue
            parts.append(f"{k}: {v_str}")
        return "；".join(parts)

    return str(detail)


def success(data: Any = None, msg: str = "成功", code: str = "00000", status: int = 200) -> Response:
    """返回标准成功响应。"""
    return Response({"code": code, "msg": msg, "data": data}, status=status)


def page_success(
    items,
    total: int,
    page_num: int,
    page_size: int,
    msg: str = "成功",
    code: str = "00000",
    status: int = 200,
) -> Response:
    """返回标准分页成功响应。"""
    return Response(
        {
            "code": code,
            "msg": msg,
            "data": {"list": items, "total": total},
        },
        status=status,
    )


def error(msg: Any, code: Optional[str] = None, status: int = 200, data: Any = None) -> Response:
    """返回标准错误响应。不传 code 时根据 HTTP status 自动匹配业务码。

    业务码前缀：A=客户端错误 C=资源/接口 B=服务端错误
    """
    if not isinstance(msg, str):
        if data is None:
            data = msg
        msg = _stringify_error_detail(msg) or "请求处理失败"

    if code is None:
        if status == 400:
            code = "A0400"
        elif status == 401:
            code = "A0230"
        elif status == 403:
            code = "A0300"
        elif status == 404:
            code = "C0113"
        elif status == 429:
            code = "A0502"
        elif status >= 500:
            code = "B0001"
        else:
            code = "B0001"

    return Response({"code": code, "msg": msg, "data": data}, status=status)
