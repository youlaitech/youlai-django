"""公共验证器。"""

import re

# 手机号放宽为 5~20 位数字，兼容测试数据和国际化场景
MOBILE_PATTERN = re.compile(r'^\d{5,20}$')
MOBILE_PATTERN_ALLOW_EMPTY = re.compile(r'^$|^\d{5,20}$')
EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


def validate_mobile(value: str, allow_empty: bool = False) -> bool:
    """验证手机号格式。"""
    if not value:
        return allow_empty
    pattern = MOBILE_PATTERN_ALLOW_EMPTY if allow_empty else MOBILE_PATTERN
    return bool(pattern.match(value))


def validate_email(value: str) -> bool:
    """验证邮箱格式。"""
    if not value:
        return True
    return bool(EMAIL_PATTERN.match(value))
