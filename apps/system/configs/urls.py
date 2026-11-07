"""系统管理-系统配置路由。

"""

from core.routers import AppRouter

from .views import ConfigViewSet


router = AppRouter(trailing_slash=False)
router.register(r"", ConfigViewSet, basename="configs")

urlpatterns = router.urls
