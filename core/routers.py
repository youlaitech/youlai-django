"""路由工具类。"""

from __future__ import annotations

from rest_framework.mixins import UpdateModelMixin
from rest_framework.routers import SimpleRouter


class AppRouter(SimpleRouter):
    """不生成默认的详情 GET 路由与 PATCH 路由，视图集重写 partial_update 时保留。"""

    def get_method_map(self, viewset, method_map):
        bound = super().get_method_map(viewset, method_map)
        result = {}
        for method, action in bound.items():
            if method == "get" and action == "retrieve":
                continue
            if method == "patch" and action == "partial_update":
                if getattr(type(viewset), "partial_update", None) is UpdateModelMixin.partial_update:
                    continue
            result[method] = action
        return result
