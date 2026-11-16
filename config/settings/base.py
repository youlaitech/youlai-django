"""所有环境共享的配置。"""

from datetime import timedelta
from pathlib import Path

from config.env import (
    env_bool,
    env_float,
    env_int,
    env_str,
    require_env,
)

# 构建项目内部路径，如：BASE_DIR / 'subdir'
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# 安全警告：生产环境中请妥善保管密钥！
SECRET_KEY = require_env('DJANGO_SECRET_KEY')

# 应用定义
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'channels',
    'apps.system.apps.SystemConfig',
    'apps.auth.apps.AuthConfig',
    'apps.codegen',
    'apps.file',
    'apps.message',
    'rest_framework',
    'django_filters',
    'rest_framework_simplejwt',
    'drf_spectacular',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'core.middleware.RequestContextMiddleware',
    'core.middleware.RateLimitMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# 密码验证
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# 国际化
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True

# 静态文件 (CSS, JavaScript, Images)
STATIC_URL = 'static/'

# 默认主键字段类型
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# 自定义用户模型
AUTH_USER_MODEL = 'system.User'

# 默认认证方式 (JWT)
DEFAULT_AUTH_CLASSES = (
    "apps.auth.utils.jwt_authentication.VersionedJWTAuthentication",
)

# AI 对话配置（OpenAI 兼容协议，默认关闭；动态表单/菜单的 AI 辅助接口依赖它）
AI_ENABLED = env_bool("AI_ENABLED", False)
AI_BASE_URL = env_str("AI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
AI_API_KEY = env_str("AI_API_KEY", "")
AI_MODEL = env_str("AI_MODEL", "qwen-plus")

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': DEFAULT_AUTH_CLASSES,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'EXCEPTION_HANDLER': 'core.exceptions.handler.global_exception_handler',
    'DEFAULT_PAGINATION_CLASS': 'core.pagination.StandardResultsPagination',
    'PAGE_SIZE': 10,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
    ],
    'DATE_FORMAT': '%Y-%m-%d',
    'TIME_FORMAT': '%H:%M:%S',
    'DATETIME_FORMAT': '%Y-%m-%d %H:%M:%S',
    'DATE_INPUT_FORMATS': ['%Y-%m-%d', 'iso-8601'],
    'TIME_INPUT_FORMATS': ['%H:%M:%S', 'iso-8601'],
    'DATETIME_INPUT_FORMATS': ['%Y-%m-%d %H:%M:%S', 'iso-8601'],
}

# JWT 设置（只定义一次）
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(seconds=env_int('JWT_ACCESS_TOKEN_LIFETIME', 7200)),
    'REFRESH_TOKEN_LIFETIME': timedelta(seconds=env_int('JWT_REFRESH_TOKEN_LIFETIME', 604800)),
    'SIGNING_KEY': env_str('JWT_SECRET_KEY', SECRET_KEY),
}

JWT_SECRET_KEY = env_str('JWT_SECRET_KEY', '')

# Redis 连接信息（Channel layer 与实时票据共用）
REDIS_HOST = env_str('REDIS_HOST', '127.0.0.1')
REDIS_PORT = env_int('REDIS_PORT', 6379)
REDIS_DB = env_int('REDIS_DB', 0)
REDIS_PASSWORD = env_str('REDIS_PASSWORD', '')

# Channel layer：实时消息跨进程广播
_redis_auth = f":{REDIS_PASSWORD}@" if REDIS_PASSWORD else ""
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [
                f"redis://{_redis_auth}{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
            ],
        },
    },
}

# 日志
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'request_context': {
            '()': 'core.middleware.RequestContextFilter',
        }
    },
    'formatters': {
        'request': {
            'format': '%(asctime)s %(levelname)s %(request_id)s %(user_id)s %(method)s %(path)s %(status)s %(cost_ms)sms %(name)s %(message)s',
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'filters': ['request_context'],
            'formatter': 'request',
        }
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}

# Spectacular 设置
from config.schema import SPECTACULAR_SETTINGS as _SPECTACULAR_SETTINGS
SPECTACULAR_SETTINGS = _SPECTACULAR_SETTINGS

# 自定义设置 - 可在特定环境文件中覆盖
APPEND_SLASH = False

# ================================
# 文件存储配置
# ================================

OSS_TYPE = env_str('OSS_TYPE', 's3')

S3_ENDPOINT = env_str('S3_ENDPOINT', 'http://127.0.0.1:9000')
S3_ACCESS_KEY = env_str('S3_ACCESS_KEY', 'rustfs-admin')
S3_SECRET_KEY = env_str('S3_SECRET_KEY', 'rustfs-admin')
S3_BUCKET_NAME = env_str('S3_BUCKET_NAME', 'public')
S3_SSL = env_bool('S3_SSL', False)

# 文件上传限制
FILE_MAX_SIZE_MB = 50
FILE_ALLOWED_EXTENSIONS = "jpg,jpeg,png,gif"

# ================================
# 短信配置
# ================================

ALIYUN_SMS_ACCESS_KEY_ID = env_str('ALIYUN_SMS_ACCESS_KEY_ID', '')
ALIYUN_SMS_ACCESS_KEY_SECRET = env_str('ALIYUN_SMS_ACCESS_KEY_SECRET', '')
ALIYUN_SMS_DOMAIN = env_str('ALIYUN_SMS_DOMAIN', 'dysmsapi.aliyuncs.com')
ALIYUN_SMS_REGION_ID = env_str('ALIYUN_SMS_REGION_ID', 'cn-shanghai')
ALIYUN_SMS_SIGN_NAME = env_str('ALIYUN_SMS_SIGN_NAME', '有来技术')

SMS_TEMPLATES = {
    'register': env_str('SMS_REGISTER_TEMPLATE', 'SMS_22xxx771'),
    'login': env_str('SMS_LOGIN_TEMPLATE', 'SMS_22xxx772'),
    'change_mobile': env_str('SMS_CHANGE_MOBILE_TEMPLATE', 'SMS_22xxx773'),
}
# 短信发送模板（默认取登录模板）
ALIYUN_SMS_TEMPLATE_CODE = env_str('ALIYUN_SMS_TEMPLATE_CODE', SMS_TEMPLATES['login'])
MOBILE_CODE_LENGTH = env_int('MOBILE_CODE_LENGTH', 6)
MOBILE_CODE_TIMEOUT = env_int('MOBILE_CODE_TIMEOUT', 300)
MOBILE_CODE_FIXED_ENABLED = env_bool('MOBILE_CODE_FIXED_ENABLED', True)
MOBILE_CODE_FIXED_VALUE = env_str('MOBILE_CODE_FIXED_VALUE', '123456')

# ================================
# 验证码配置
# ================================

CAPTCHA_TYPE = env_str('CAPTCHA_TYPE', 'circle')
CAPTCHA_WIDTH = env_int('CAPTCHA_WIDTH', 140)
CAPTCHA_HEIGHT = env_int('CAPTCHA_HEIGHT', 44)
CAPTCHA_INTERFERE_COUNT = env_int('CAPTCHA_INTERFERE_COUNT', 1)
CAPTCHA_TEXT_ALPHA = env_float('CAPTCHA_TEXT_ALPHA', 1.0)
CAPTCHA_CODE_TYPE = env_str('CAPTCHA_CODE_TYPE', 'math')
CAPTCHA_CODE_LENGTH = env_int('CAPTCHA_CODE_LENGTH', 4)
CAPTCHA_FONT_NAME = env_str('CAPTCHA_FONT_NAME', 'SansSerif')
CAPTCHA_FONT_WEIGHT = env_int('CAPTCHA_FONT_WEIGHT', 1)
CAPTCHA_FONT_SIZE = env_int('CAPTCHA_FONT_SIZE', 28)
CAPTCHA_EXPIRE_SECONDS = env_int('CAPTCHA_EXPIRE_SECONDS', 120)

# ================================
# 微信小程序配置
# ================================

WX_MINIAPP_APP_ID = env_str('WX_MINIAPP_APP_ID', '')
WX_MINIAPP_APP_SECRET = env_str('WX_MINIAPP_APP_SECRET', '')

# 必填配置校验（启动即失败）
require_env('DB_HOST')
require_env('DB_NAME')
require_env('DB_USER')
require_env('REDIS_HOST')
