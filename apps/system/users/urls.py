"""系统管理-用户路由。

"""

from core.routers import AppRouter

from .views import UserViewSet


router = AppRouter(trailing_slash=False)
router.register(r"", UserViewSet, basename="users")

urlpatterns = router.urls
