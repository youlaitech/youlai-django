"""系统管理-通知公告路由。

"""

from core.routers import AppRouter

from .views import NoticeViewSet


router = AppRouter(trailing_slash=False)
router.register(r"", NoticeViewSet, basename="notices")

urlpatterns = router.urls
