"""系统管理-菜单视图。

"""

from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.db.models import Q
from django.shortcuts import get_object_or_404
from apps.system.menus.models import Menu
from apps.system.roles.models import RoleMenu
from apps.system.users.models import UserRole
from core.permissions.decorators import permission_required
from core.permissions.perms import HasPerm
from core.response import error, success
from core.openapi import resp
from core.viewsets import BaseModelViewSet
from apps.system.logs.models import ActionType, LogModule
from apps.system.utils.decorators import operation_log
from .filters import MenuFilter
from .serializers import (
    MenuSerializer, MenuOptionSerializer, MenuCreateSerializer,
    MenuUpdateSerializer, MenuRouteSerializer, MenuFormSerializer,
    MenuAiFillSerializer, MenuAiFillResultSerializer
)
from .services import ai_fill_menu


@extend_schema(tags=["04.菜单接口"])
class MenuViewSet(BaseModelViewSet):
    """系统管理-菜单ViewSet。"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, HasPerm]
    queryset = Menu.objects.all().order_by('sort', 'id')
    filterset_class = MenuFilter

    def get_serializer_class(self):
        if self.action == 'create':
            return MenuCreateSerializer
        if self.action in ['update', 'partial_update']:
            return MenuUpdateSerializer
        if self.action == 'options':
            return MenuOptionSerializer
        if self.action == 'routes':
            return MenuRouteSerializer
        if self.action == 'form':
            return MenuFormSerializer
        return MenuSerializer

    @permission_required(["sys:menu:list"])
    @extend_schema(
        summary="菜单树形列表",
        parameters=[
            OpenApiParameter(
                name="keywords",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="关键词（菜单名称）",
            ),
            OpenApiParameter(
                name="status",
                location=OpenApiParameter.QUERY,
                required=False,
                type=int,
                description="菜单状态：1 启用 / 0 禁用",
            ),
        ],
        responses=resp("MenuTreeResult", MenuSerializer(many=True)),
    )
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        keywords = request.query_params.get('keywords', '')
        if not keywords:
            queryset = queryset.filter(parent_id=0)

        status = request.query_params.get('status')
        visible = None
        if status is not None and status != "":
            try:
                visible = int(status)
            except ValueError:
                visible = None

        serializer = MenuSerializer(queryset.order_by('sort', 'id'), many=True, context={'visible': visible})
        return success(serializer.data, msg="获取菜单列表成功")

    @permission_required(["sys:menu:create"])
    @operation_log('新增菜单', module=LogModule.MENU, action_type=ActionType.INSERT)
    @extend_schema(
        summary="新增菜单",
        request=MenuCreateSerializer,
        responses=resp("MenuCreateResult", MenuSerializer()),
    )
    def create(self, request, *args, **kwargs):
        serializer = MenuCreateSerializer(data=request.data)
        if serializer.is_valid():
            menu = serializer.save()
            response_serializer = MenuSerializer(menu)
            return success(response_serializer.data, msg="菜单创建成功")
        return error(serializer.errors)

    @permission_required(["sys:menu:update"])
    @operation_log('修改菜单', module=LogModule.MENU, action_type=ActionType.UPDATE)
    @extend_schema(
        summary="更新菜单",
        request=MenuUpdateSerializer,
        responses=resp("MenuUpdateResult", MenuSerializer()),
    )
    def update(self, request, *args, **kwargs):
        menu = self.get_object()
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        # clearable 字段：前端丢 key = 清空，补 None 让 DRF 写入而非跳过
        for field in ['component', 'icon', 'redirect', 'routeName', 'perm', 'externalUrl']:
            if field not in data:
                data[field] = None
        serializer = MenuUpdateSerializer(menu, data=data, partial=True)
        if serializer.is_valid():
            updated_menu = serializer.save()
            response_serializer = MenuSerializer(updated_menu)
            return success(response_serializer.data, msg="菜单更新成功")
        return error(serializer.errors)

    @permission_required(["sys:menu:update"])
    @operation_log('修改菜单显示状态', module=LogModule.MENU, action_type=ActionType.UPDATE)
    @extend_schema(
        summary="修改菜单显示状态",
        parameters=[
            OpenApiParameter(
                name="visible",
                location=OpenApiParameter.QUERY,
                required=True,
                type=int,
                description="显示状态：1 显示 / 0 隐藏",
            ),
        ],
        responses=resp("MenuVisibleResult", serializers.DictField(required=False)),
    )
    def partial_update(self, request, *args, **kwargs):
        menu = self.get_object()
        raw_visible = request.query_params.get("visible")
        if raw_visible is None or raw_visible == "":
            return error("显示状态不能为空")
        try:
            visible = int(raw_visible)
        except ValueError:
            return error("显示状态格式不正确")

        menu.visible = visible
        menu.save(update_fields=["visible"])
        return success({}, msg="菜单显示状态更新成功")

    @permission_required(["sys:menu:delete"])
    @operation_log('删除菜单', module=LogModule.MENU, action_type=ActionType.DELETE)
    @extend_schema(
        summary="删除菜单",
        parameters=[
            OpenApiParameter(
                name="ids",
                location=OpenApiParameter.PATH,
                required=True,
                type=str,
                description="菜单ID，多个以英文逗号(,)分割",
            ),
        ],
        responses=resp("MenuDeleteResult", serializers.DictField(required=False)),
    )
    def destroy(self, request, *args, **kwargs):
        ids = kwargs.get(self.lookup_url_kwarg or self.lookup_field)

        if not ids:
            return error("请指定要删除的菜单ID")

        menu_ids = str(ids).split(',')
        try:
            menu_ids = [int(mid) for mid in menu_ids if mid]
        except ValueError:
            return error("菜单ID格式不正确")

        if not menu_ids:
            return error("请指定要删除的菜单ID")

        # 级联删除子菜单：tree_path 记录祖先链，后代菜单的路径里必然带上被删菜单ID
        menus_to_delete = Menu.objects.none()
        for menu_id in menu_ids:
            menus_to_delete = menus_to_delete | Menu.objects.filter(
                Q(id=menu_id) | Q(tree_path__regex=rf"(^|,){menu_id}(,|$)")
            )

        delete_ids = list(menus_to_delete.values_list("id", flat=True))
        if not delete_ids:
            return error("菜单不存在")

        # 先解绑角色菜单：PostgreSQL 下 sys_role_menu 外键引用 sys_menu
        RoleMenu.objects.filter(menu_id__in=delete_ids).delete()
        count = len(delete_ids)
        Menu.objects.filter(id__in=delete_ids).delete()
        return success({}, msg=f"成功删除{count}个菜单")

    @permission_required(["sys:menu:list"])
    @extend_schema(
        summary="菜单下拉选项",
        parameters=[
            OpenApiParameter(
                name="types",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="菜单类型过滤（逗号分隔，如 C,M；不传返回全部）",
            ),
        ],
        responses=resp("MenuOptionsResult", MenuOptionSerializer(many=True)),
    )
    @action(methods=["get"], detail=False, url_path="options")
    def options(self, request, *args, **kwargs):
        # 前端可传 types=C,M 或重复键 types=C&types=M，均按逗号拆分解析
        raw_types = request.query_params.getlist('types')
        types = [t.strip() for raw in raw_types for t in raw.split(',') if t.strip()]

        root_menus = Menu.objects.filter(parent_id=0).order_by('sort', 'id')
        if types:
            root_menus = root_menus.filter(type__in=types)

        serializer = MenuOptionSerializer(root_menus, many=True, context={'types': types})
        return success(serializer.data)

    @extend_schema(
        summary="菜单路由",
        responses=resp("MenuRoutesResult", MenuRouteSerializer(many=True)),
    )
    @action(methods=["get"], detail=False, url_path="routes")
    def routes(self, request, *args, **kwargs):
        user_id = request.user.id
        user_roles = UserRole.objects.filter(
            user_id=user_id,
            role__status=1,
            role__is_deleted=0,
        )
        # ROOT(超级管理员) 直接放行全部菜单，不依赖 sys_role_menu 授权数据
        is_root = bool(getattr(request.user, 'is_superuser', False)) or 'ROOT' in set(
            user_roles.values_list('role__code', flat=True)
        )

        if is_root:
            include_ids = set(Menu.objects.exclude(type='B').values_list('id', flat=True))
        else:
            assigned_menu_ids = list(
                RoleMenu.objects.filter(role_id__in=user_roles.values_list('role_id', flat=True))
                .values_list('menu_id', flat=True)
                .distinct()
            )

            include_ids = set()
            assigned_menus = Menu.objects.filter(id__in=assigned_menu_ids).exclude(type='B').only('id', 'parent_id', 'tree_path')
            for menu in assigned_menus:
                include_ids.add(menu.id)
                if menu.parent_id is not None:
                    include_ids.add(menu.parent_id)
                if menu.tree_path:
                    for pid in str(menu.tree_path).split(','):
                        pid = pid.strip()
                        if not pid:
                            continue
                        try:
                            include_ids.add(int(pid))
                        except ValueError:
                            continue

        root_menus = (
            Menu.objects.filter(Q(parent_id=0) & Q(id__in=include_ids))
            .exclude(type='B')
            .order_by('sort', 'id')
        )
        serializer = MenuRouteSerializer(root_menus, many=True, context={'menu_ids': list(include_ids)})
        return success(serializer.data, msg="获取菜单路由成功")

    @permission_required(["sys:menu:update"])
    @extend_schema(
        summary="菜单表单数据",
        responses=resp("MenuFormResult", MenuFormSerializer()),
    )
    @action(methods=["get"], detail=True, url_path="form")
    def form(self, request, pk=None, *args, **kwargs):
        menu = get_object_or_404(Menu, id=pk)
        serializer = MenuFormSerializer(menu)
        return success(serializer.data)

    @extend_schema(
        summary="AI 推断菜单的访问路径与权限标识",
        request=MenuAiFillSerializer,
        responses=resp("MenuAiFillResult", MenuAiFillResultSerializer()),
    )
    @action(methods=["post"], detail=False, url_path="ai-fill")
    def ai_fill(self, request, *args, **kwargs):
        # AI 未开启时由服务层抛出业务异常
        serializer = MenuAiFillSerializer(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)

        data = serializer.validated_data
        result = ai_fill_menu(data.get('name'), data.get('type'), data.get('parentId'))
        return success(result)
