"""系统管理-部门路由。

"""

from core.routers import AppRouter

from .views import DeptViewSet


router = AppRouter(trailing_slash=False)
router.register(r"", DeptViewSet, basename="depts")

urlpatterns = router.urls
