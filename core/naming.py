"""命名转换，供代码生成的目录、路由与权限标识使用"""

from __future__ import annotations

import inflection


def to_kebab_case(value: str) -> str:
    """驼峰或下划线命名转短横线小写，如 MenuDemo → menu-demo"""
    if not value:
        return value
    return inflection.dasherize(inflection.underscore(value))


def to_plural_kebab(value: str) -> str:
    """短横线命名转英文复数，如 dict-item → dict-items、category → categories"""
    if not value:
        return value
    return inflection.dasherize(inflection.pluralize(inflection.underscore(value)))


def to_camel_case(value: str) -> str:
    """下划线或短横线命名转小驼峰，如 sys_user → sysUser"""
    if not value:
        return value
    return inflection.camelize(inflection.underscore(value), False)


def to_pascal_case(value: str) -> str:
    """下划线或短横线命名转大驼峰，如 sys_user → SysUser"""
    if not value:
        return value
    return inflection.camelize(inflection.underscore(value))


def to_upper_snake(value: str) -> str:
    """驼峰命名转大写下划线，如 SysUser → SYS_USER"""
    if not value:
        return value
    return inflection.underscore(value).upper()
