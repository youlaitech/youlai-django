"""系统管理-日志路由。

"""

from core.routers import AppRouter

from .views import LogViewSet


router = AppRouter(trailing_slash=False)
router.register(r"", LogViewSet, basename="logs")

urlpatterns = router.urls
