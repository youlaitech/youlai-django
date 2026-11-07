"""消息模块应用配置。"""

import logging
from django.apps import AppConfig

logger = logging.getLogger(__name__)


class MessageConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.message"
    verbose_name = "消息服务"

    def ready(self):
        import atexit
        from apps.message.registry import get_realtime_registry

        @atexit.register
        def cleanup_connections():
            try:
                get_realtime_registry().clear()
                logger.info("所有实时连接记录已清空")
            except Exception:
                pass
