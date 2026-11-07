"""系统管理-菜单路由。

"""

from core.routers import AppRouter

from .views import MenuViewSet


router = AppRouter(trailing_slash=False)
router.register(r"", MenuViewSet, basename="menus")

urlpatterns = router.urls
