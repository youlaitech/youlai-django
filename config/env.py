"""环境变量加载工具。

这个模块专门用来读取项目根目录下的 .env 文件，把里面的配置项加载到环境变量里。
它提供了一系列工具函数（比如 `env.bool`, `env.str`），方便在 `settings.py`
里安全地获取各种类型的配置，同时还能设置默认值。

"""

from __future__ import annotations

import os
from typing import Optional


_TRUE_VALUES = {"1", "true", "t", "yes", "y", "on"}
_FALSE_VALUES = {"0", "false", "f", "no", "n", "off"}


def _get_env(key: str) -> Optional[str]:
    value = os.getenv(key)
    if value is None:
        return None
    return value.strip()


def require_env(key: str) -> str:
    value = _get_env(key)
    if not value:
        raise RuntimeError(f"{key} is required")
    return value


def env_str(key: str, default: Optional[str] = None) -> Optional[str]:
    value = _get_env(key)
    if value:
        return value
    return default


def env_int(key: str, default: Optional[int] = None) -> Optional[int]:
    value = _get_env(key)
    if value:
        return int(value)
    return default


def env_float(key: str, default: Optional[float] = None) -> Optional[float]:
    value = _get_env(key)
    if value:
        return float(value)
    return default


def env_bool(key: str, default: bool = False) -> bool:
    value = _get_env(key)
    if value is None or value == "":
        return default
    lowered = value.lower()
    if lowered in _TRUE_VALUES:
        return True
    if lowered in _FALSE_VALUES:
        return False
    raise ValueError(f"Invalid boolean for {key}: {value}")


# 数据库引擎：DB_ENGINE=mysql（默认）/ postgresql，对应 SQL 脚本 sql/mysql、sql/postgresql
_DB_ENGINE_BACKENDS = {
    "mysql": "django.db.backends.mysql",
    "postgresql": "django.db.backends.postgresql",
    "postgres": "django.db.backends.postgresql",
}
_DB_DEFAULT_PORTS = {"mysql": 3306, "postgresql": 5432}


def database_config(*, require_credentials: bool = False) -> dict:
    """按 DB_ENGINE 组装 DATABASES['default']，同一套代码支持 MySQL 与 PostgreSQL。

    MySQL/PostgreSQL 两方言的初始化脚本分别在 sql/mysql、sql/postgresql 目录下。
    """
    engine_key = (env_str("DB_ENGINE", "mysql") or "mysql").lower()
    if engine_key not in _DB_ENGINE_BACKENDS:
        raise ValueError(
            f"Invalid DB_ENGINE: {engine_key} (expected one of: {', '.join(sorted(_DB_ENGINE_BACKENDS))})"
        )
    backend = _DB_ENGINE_BACKENDS[engine_key]
    is_postgres = backend.endswith("postgresql")

    def credential(key: str, default: Optional[str] = None) -> Optional[str]:
        return require_env(key) if require_credentials else env_str(key, default)

    config: dict = {
        "ENGINE": backend,
        "NAME": credential("DB_NAME"),
        "USER": credential("DB_USER"),
        "PASSWORD": credential("DB_PASSWORD", ""),
        "HOST": credential("DB_HOST", "127.0.0.1"),
        "PORT": env_int("DB_PORT", 5432 if is_postgres else 3306),
    }
    if not is_postgres:
        config["OPTIONS"] = {"charset": "utf8mb4"}
    return config
