"""开发环境覆盖配置。"""

from .base import *

from config.env import database_config, env_bool, env_int, env_str

# 开发环境调试开关
DEBUG = True
ALLOWED_HOSTS = ['*']

# 开发环境数据库设置（使用环境变量；DB_ENGINE=mysql（默认）| postgresql）
DATABASES = {'default': database_config()}

# 开发环境 Redis 设置
REDIS_PASSWORD = env_str('REDIS_PASSWORD', '')
_redis_auth = f":{REDIS_PASSWORD}@" if REDIS_PASSWORD else ""
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': (
            f"redis://{_redis_auth}{env_str('REDIS_HOST', '127.0.0.1')}:"
            f"{env_int('REDIS_PORT', 6379)}/{env_int('REDIS_DB', 0)}"
        ),
        'OPTIONS': {'CLIENT_CLASS': 'django_redis.client.DefaultClient'},
    }
}

# 邮件配置
EMAIL_BACKEND = env_str('EMAIL_BACKEND', "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env_str('EMAIL_HOST')
EMAIL_PORT = env_int('EMAIL_PORT', 587)
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', True)
EMAIL_USE_SSL = env_bool('EMAIL_USE_SSL', False)
EMAIL_HOST_USER = env_str('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = env_str('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = env_str('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER or '')

# 会话类型覆盖（开发环境）
SESSION_TYPE = env_str('SESSION_TYPE', 'jwt')
default_auth_classes: tuple[str, ...]
if SESSION_TYPE == "redis-token":
    default_auth_classes = (
        "apps.auth.utils.redis_token_authentication.RedisTokenAuthentication",
    )
else:
    default_auth_classes = (
        "apps.auth.utils.jwt_authentication.VersionedJWTAuthentication",
    )
REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES'] = default_auth_classes  # pyright: ignore[reportArgumentType]

# ================================
# 开发环境特定配置
# ================================

# 禁用验证码（开发环境）
CAPTCHA_ENABLED = False

# ================================
# 限流配置
# ================================
RATE_LIMIT_IP_LIMIT = env_int('RATE_LIMIT_IP_LIMIT', 1000)
RATE_LIMIT_IP_WINDOW = env_int('RATE_LIMIT_IP_WINDOW', 60)
RATE_LIMIT_IP_ENABLED = env_bool('RATE_LIMIT_IP_ENABLED', True)
