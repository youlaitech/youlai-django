"""通用视图集基类。"""

from __future__ import annotations

from rest_framework import status, viewsets

from core.response import error, success
from core.permissions.data_scope import apply_data_permission


class BaseViewSet(viewsets.ModelViewSet):
    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)

        request = getattr(self, "request", None)
        if request is None:
            return queryset

        # 数据权限通过 @DataPermission 装饰器把配置注入到 request 上
        if getattr(request, "_skip_data_permission", False):
            return queryset

        config = getattr(request, "_data_permission_config", None)
        if not config:
            return queryset

        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return queryset

        dept_field = config.get("dept_field", "dept_id")
        user_field = config.get("user_field", "create_by")
        return apply_data_permission(queryset, user, dept_field=dept_field, user_field=user_field)

    def success_response(self, data=None, msg: str = "成功", code: str = "00000", status_code: int = 200):
        return success(data=data, msg=msg, code=code, status=status_code)

    def error_response(self, msg, code: str | None = None, status_code: int = 400, data=None):
        return error(msg=msg, code=code, status=status_code, data=data)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return self.success_response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return self.success_response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return self.success_response(serializer.data, status_code=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return self.success_response(serializer.data, status_code=status.HTTP_200_OK)

    def perform_update(self, serializer):
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        lookup = self.kwargs.get(self.lookup_url_kwarg or self.lookup_field or 'pk')
        ids = [i for i in str(lookup).split(',') if i] if lookup else []
        if len(ids) > 1:
            for instance in qs.filter(pk__in=ids):
                self.perform_destroy(instance)
            return self.success_response(None, status_code=status.HTTP_200_OK)
        # 查不到就算删除成功，幂等处理，避免前端报错
        if lookup and not qs.filter(pk=lookup).exists():
            return self.success_response(None, status_code=status.HTTP_200_OK)
        instance = self.get_object()
        self.perform_destroy(instance)
        return self.success_response(None, status_code=status.HTTP_200_OK)

    def perform_destroy(self, instance):
        instance.delete()

    def handle_exception(self, exc):
        """把 DRF 标准异常里的 detail 取出来拼到错误响应里。"""
        resp = super().handle_exception(exc)
        try:
            detail = getattr(resp.data, "get", lambda k, d=None: None)("detail")
        except Exception:
            detail = None
        if detail is not None:
            return self.error_response(str(detail), status_code=resp.status_code)
        return resp


class BaseModelViewSet(BaseViewSet):
    """带审计字段的视图集基类。

    自动填充 create_by/update_by 字段，支持软删除。
    """

    def _get_user_id(self):
        request = getattr(self, "request", None)
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return None
        return getattr(user, "id", None)

    def perform_create(self, serializer):
        user_id = self._get_user_id()
        model = getattr(getattr(serializer, "Meta", None), "model", None)
        if user_id is not None and model is not None:
            field_names = {f.name for f in model._meta.get_fields()}
            extra = {}
            if "create_by" in field_names:
                extra["create_by"] = user_id
            if "update_by" in field_names:
                extra["update_by"] = user_id
            if extra:
                serializer.save(**extra)
                return
        serializer.save()

    def perform_update(self, serializer):
        user_id = self._get_user_id()
        model = getattr(getattr(serializer, "Meta", None), "model", None)
        if user_id is not None and model is not None:
            field_names = {f.name for f in model._meta.get_fields()}
            if "update_by" in field_names:
                serializer.save(update_by=user_id)
                return
        serializer.save()

    def perform_destroy(self, instance):
        if hasattr(instance, "is_deleted"):
            setattr(instance, "is_deleted", 1)

            user_id = self._get_user_id()
            if user_id is not None and hasattr(instance, "update_by"):
                setattr(instance, "update_by", user_id)

            instance.save()
            return
        instance.delete()
