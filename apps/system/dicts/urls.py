"""系统管理-字典路由。

"""

from core.routers import AppRouter

from .views import DictItemViewSet, DictViewSet


router = AppRouter(trailing_slash=False)
router.register(r"", DictViewSet, basename="dicts")
router.register(r"(?P<dict_code>[^/.]+)/items", DictItemViewSet, basename="dict-items")

urlpatterns = router.urls
