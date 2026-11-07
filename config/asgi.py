"""Django ASGI 应用入口。

同时承载 HTTP 与实时 WebSocket 连接。
"""

import os
import sys
from pathlib import Path

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from dotenv import load_dotenv


def _assert_supported_python():
    version = sys.version_info[:2]
    if version < (3, 10) or version >= (3, 15):
        raise RuntimeError(
            f"当前 Python 版本为 {sys.version.split()[0]}，本项目仅支持 Python 3.10-3.14。"
        )


_assert_supported_python()

env_path = Path(__file__).resolve().parent.parent / ".env"
settings_module = os.getenv("DJANGO_SETTINGS_MODULE", "config.settings.dev")
if settings_module == "config.settings.dev" and env_path.exists():
    load_dotenv(env_path)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)

# 先初始化 Django，之后才能安全导入 Consumer
django_asgi_app = get_asgi_application()

from apps.message.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": URLRouter(websocket_urlpatterns),
    }
)
