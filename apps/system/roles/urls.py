"""系统管理-角色路由。

"""

from core.routers import AppRouter

from .views import RoleViewSet


router = AppRouter(trailing_slash=False)
router.register(r"", RoleViewSet, basename="roles")

urlpatterns = router.urls
