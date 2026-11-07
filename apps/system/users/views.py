"""用户视图。"""

import re

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.auth.utils.session_utils import invalidate_user_sessions
from apps.system.users.models import User
from apps.system.logs.models import ActionType, LogModule
from apps.system.utils.decorators import operation_log
from apps.utils.email_utils import generate_and_send_email_code
from apps.utils.mobile_utils import send_mobile_code
from apps.system.utils.rate_limit import ip_rate_limit
from core.openapi import page_resp, resp
from core.permissions.data_scope import DataPermission, data_permission_required
from core.permissions.decorators import permission_required
from core.permissions.perms import HasPerm
from core.response import error, success
from core.viewsets import BaseModelViewSet
from .filters import UserFilter
from .serializers import (
    DepartmentOptionSerializer,
    PasswordVerifySerializer,
    UserCreateSerializer,
    UserEmailUpdateSerializer,
    UserFormSerializer,
    UserInfoSerializer,
    UserMobileUpdateSerializer,
    UserPageSerializer,
    UserPasswordChangeSerializer,
    UserPasswordResetSerializer,
    UserProfileUpdateSerializer,
    UserStatusSerializer,
    UserUpdateSerializer,
)
from .services import (
    build_import_template_excel_bytes,
    check_data_permission,
    delete_users,
    export_to_excel_bytes,
    import_from_excel,
)


@extend_schema(tags=["02.用户接口"])
class UserViewSet(BaseModelViewSet):
    """用户ViewSet。"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, HasPerm]
    queryset = User.objects.filter(is_deleted=0)
    filterset_class = UserFilter

    def get_queryset(self):
        """按 action 动态构造 queryset。"""
        qs = User.objects.filter(is_deleted=0)

        if getattr(self, "action", None) in ["list"]:
            field = self.request.query_params.get("field", "id")
            direction = self.request.query_params.get("direction", "DESC")

            viewable_users = data_permission_required(getattr(self.request, "user", None), "select")

            query = Q(is_deleted=0)
            if viewable_users != "all":
                query &= Q(id__in=viewable_users)

            order_field = field if (direction or "DESC").upper() == "ASC" else f"-{field}"
            return qs.filter(query).distinct().order_by(order_field)

        return qs

    def get_serializer_class(self):
        """根据 action 返回对应序列化器。"""
        if self.action in ["list"]:
            return UserPageSerializer
        if self.action == "create":
            return UserCreateSerializer
        if self.action in ["update", "partial_update"]:
            return UserUpdateSerializer
        if self.action == "form":
            return UserFormSerializer
        return UserFormSerializer

    @permission_required(["sys:user:list"])
    @extend_schema(
        summary="用户分页列表",
        parameters=[
            OpenApiParameter(name="keywords", location=OpenApiParameter.QUERY, required=False, type=str, description="关键词（用户名/昵称/手机号）"),
            OpenApiParameter(name="status", location=OpenApiParameter.QUERY, required=False, type=int, description="用户状态：1 启用 / 0 禁用"),
            OpenApiParameter(name="deptId", location=OpenApiParameter.QUERY, required=False, type=int, description="部门ID"),
            OpenApiParameter(name="roleIds", location=OpenApiParameter.QUERY, required=False, type=str, description="角色ID列表，多个以英文逗号(,)分割"),
            OpenApiParameter(name="createTime", location=OpenApiParameter.QUERY, required=False, type=str, description="创建时间范围：start,end"),
            OpenApiParameter(name="field", location=OpenApiParameter.QUERY, required=False, type=str, description="排序字段（默认 id）"),
            OpenApiParameter(name="direction", location=OpenApiParameter.QUERY, required=False, type=str, description="排序方向：ASC / DESC（默认 DESC）"),
            OpenApiParameter(name="pageNum", location=OpenApiParameter.QUERY, required=False, type=int, description="页码（默认 1）"),
            OpenApiParameter(name="pageSize", location=OpenApiParameter.QUERY, required=False, type=int, description="每页记录数（默认 10）"),
        ],
        responses=page_resp("UserPageResult", UserPageSerializer(many=True)),
    )
    @operation_log('用户列表', module=LogModule.USER, action_type=ActionType.LIST)
    @DataPermission(dept_field="dept_id", user_field="create_by")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @permission_required(["sys:user:create"])
    @operation_log('新增用户', module=LogModule.USER, action_type=ActionType.INSERT)
    @extend_schema(summary="新增用户", request=UserCreateSerializer, responses=resp("UserCreateResult", UserCreateSerializer()))
    def create(self, request, *args, **kwargs):
        serializer = UserCreateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return success(serializer.data, msg="用户创建成功")
        return error(serializer.errors)

    @permission_required(["sys:user:update"])
    @operation_log('更新用户', module=LogModule.USER, action_type=ActionType.UPDATE)
    @extend_schema(summary="更新用户信息", request=UserUpdateSerializer, responses=resp("UserUpdateResult", UserUpdateSerializer()))
    def update(self, request, *args, **kwargs):
        user = self.get_object()
        if not check_data_permission(request=request, operation="update", target_user_id=user.id):
            raise PermissionDenied("您没有权限更新该用户信息")

        serializer = UserUpdateSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return success(serializer.data, msg="更新用户信息成功")
        return error(serializer.errors)

    @permission_required(["sys:user:delete"])
    @operation_log('删除用户', module=LogModule.USER, action_type=ActionType.DELETE)
    @extend_schema(
        summary="删除用户",
        parameters=[OpenApiParameter(name="ids", location=OpenApiParameter.PATH, required=True, type=str, description="用户ID，多个以英文逗号(,)分割")],
        responses=resp("UserDeleteResult", serializers.DictField(required=False)),
    )
    def destroy(self, request, *args, **kwargs):
        ids = kwargs.get(self.lookup_url_kwarg or self.lookup_field)
        result = delete_users(ids=str(ids), current_user_id=request.user.id, current_user=request.user)
        return success({}, msg=f"成功删除 {result['deleted_count']} 个用户")

    @operation_log('获取当前用户信息', module=LogModule.USER, action_type=ActionType.OTHER)
    @extend_schema(summary="获取当前用户信息", responses=resp("UserInfoResult", UserInfoSerializer()))
    @action(methods=["get"], detail=False, url_path="me")
    def me(self, request, *args, **kwargs):
        serializer = UserInfoSerializer(request.user)
        return success(serializer.data)

    @permission_required(["sys:user:update"])
    @extend_schema(summary="获取用户信息", responses=resp("UserFormResult", UserFormSerializer()))
    @action(methods=["get"], detail=True, url_path="form")
    def form(self, request, pk=None, *args, **kwargs):
        user = self.get_object()
        serializer = UserFormSerializer(user)
        return success(serializer.data, msg="获取用户信息成功")

    @permission_required(["sys:user:reset-password"])
    @extend_schema(
        summary="重置用户密码",
        parameters=[OpenApiParameter(name="password", location=OpenApiParameter.QUERY, required=True, type=str, description="新密码")],
        responses=resp("UserPasswordResetResult", serializers.DictField(required=False)),
    )
    @action(methods=["put"], detail=True, url_path=r"password/reset")
    def password_reset(self, request, pk=None, *args, **kwargs):
        user = self.get_object()

        if not check_data_permission(request=request, operation="update", target_user_id=user.id):
            raise PermissionDenied("您没有权限重置该用户密码")

        password = request.query_params.get('password')
        if not password:
            return error("密码不能为空")

        if user.username == 'root' and request.user.username != 'root':
            raise PermissionDenied("root 用户不允许重置密码")

        serializer = UserPasswordResetSerializer(user, data={'password': password})
        if serializer.is_valid():
            serializer.save()
            invalidate_user_sessions(user.id)
            return success({}, msg="密码重置成功")
        return error(serializer.errors)

    @permission_required(["sys:user:update"])
    @extend_schema(
        summary="更新用户状态",
        parameters=[OpenApiParameter(name="status", location=OpenApiParameter.QUERY, required=True, type=int, description="用户状态：1 启用 / 0 禁用")],
        responses=resp("UserStatusUpdateResult", serializers.DictField(required=False)),
    )
    @action(methods=["patch"], detail=True, url_path="status")
    def status(self, request, pk=None, *args, **kwargs):
        # 用 get_queryset 直接查，绕开 filter_backend。self.get_object() 会把 ?status=0 当作 UserFilter 的筛选条件，导致查不到用户
        user = get_object_or_404(self.get_queryset(), pk=pk)
        try:
            status_value = int(request.query_params.get('status', ''))
        except (ValueError, TypeError):
            return error("状态值格式不正确")

        if not check_data_permission(request=request, operation="update", target_user_id=user.id):
            raise PermissionDenied("您没有权限更新该用户状态")

        if user.id == request.user.id and status_value == 0:
            return error("您不能禁用自己")
        if user.username == 'root' and status_value == 0:
            return error("您不能禁用 root 用户")

        serializer = UserStatusSerializer(user, data={'status': status_value})
        if serializer.is_valid():
            serializer.save()
            if status_value == 0:
                invalidate_user_sessions(user.id)
            status_text = "启用" if status_value == 1 else "禁用"
            return success({}, msg=f"用户 {status_text} 成功")
        return error(serializer.errors)

    @operation_log('获取用户个人信息', module=LogModule.USER, action_type=ActionType.OTHER)
    @extend_schema(
        summary="获取用户个人信息",
        responses=resp(
            "UserProfileResult",
            inline_serializer(
                name="UserProfileData",
                fields={
                    "id": serializers.CharField(),
                    "username": serializers.CharField(),
                    "nickname": serializers.CharField(allow_blank=True, required=False),
                    "avatar": serializers.CharField(allow_blank=True, required=False),
                    "gender": serializers.IntegerField(),
                    "mobile": serializers.CharField(allow_blank=True, required=False),
                    "email": serializers.CharField(allow_blank=True, required=False),
                    "deptName": serializers.CharField(allow_blank=True, required=False),
                    "roleNames": serializers.CharField(allow_blank=True, required=False),
                    "createTime": serializers.DateTimeField(),
                },
            ),
        ),
    )
    @action(methods=["get"], detail=False, url_path="profile")
    def profile(self, request, *args, **kwargs):
        user = request.user
        dept_name = user.dept.name if user.dept else ""
        roles = user.roles.all()
        role_names = ", ".join([role.name for role in roles]) if roles else ""
        data = {
            "id": str(user.id),
            "username": user.username,
            "nickname": user.nickname,
            "avatar": user.avatar,
            "gender": user.gender,
            "mobile": user.mobile,
            "email": user.email,
            "deptName": dept_name,
            "roleNames": role_names,
            "createTime": user.date_joined,
        }
        return success(data)

    @operation_log('更新用户个人信息', module=LogModule.USER, action_type=ActionType.UPDATE)
    @extend_schema(summary="更新用户个人信息", request=UserProfileUpdateSerializer, responses=resp("UserProfileUpdateResult", serializers.BooleanField()))
    @profile.mapping.put
    def profile_update(self, request, *args, **kwargs):
        user = request.user
        serializer = UserProfileUpdateSerializer(user, data=request.data, partial=True)
        if not serializer.is_valid():
            return error(serializer.errors)

        if not serializer.validated_data:
            return error("请至少修改一项")

        serializer.save()
        return success(True, msg="更新用户个人信息成功")

    @operation_log('修改用户密码', module=LogModule.USER, action_type=ActionType.CHANGE_PASSWORD)
    @extend_schema(summary="修改用户密码", request=UserPasswordChangeSerializer, responses=resp("UserPasswordChangeResult", serializers.BooleanField()))
    @action(methods=["put"], detail=False, url_path="password")
    def password_change(self, request, *args, **kwargs):
        serializer = UserPasswordChangeSerializer(request.user, data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            invalidate_user_sessions(request.user.id)
            return success(True, msg="修改密码成功")
        return error(serializer.errors)

    @extend_schema(
        summary="发送邮箱验证码",
        parameters=[OpenApiParameter(name="email", location=OpenApiParameter.QUERY, required=True, type=str, description="邮箱地址")],
        responses=resp("UserEmailCodeResult", serializers.BooleanField()),
    )
    @action(methods=["post"], detail=False, url_path=r"email/code")
    def email_code(self, request, *args, **kwargs):
        email = request.query_params.get('email')
        if not email:
            return error('邮箱不能为空')
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return error('邮箱格式不正确')

        result = generate_and_send_email_code(email=email, subject='邮箱验证码', user_id=request.user.id)
        if result.get('success'):
            return success(True, msg='验证码发送成功')
        return error('验证码发送失败', status=500)

    @extend_schema(summary="更新用户邮箱", request=UserEmailUpdateSerializer, responses=resp("UserEmailUpdateResult", serializers.BooleanField()))
    @action(methods=["put"], detail=False, url_path="email")
    def email_update(self, request, *args, **kwargs):
        serializer = UserEmailUpdateSerializer(request.user, data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return success(True, msg='更新邮箱成功')
        return error(serializer.errors)

    @extend_schema(summary="解绑邮箱", request=PasswordVerifySerializer, responses=resp("UserEmailUnbindResult", serializers.BooleanField()))
    @email_update.mapping.delete
    def email_unbind(self, request, *args, **kwargs):
        serializer = PasswordVerifySerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return error(serializer.errors)

        user = request.user
        if not user.email:
            return error("当前账号未绑定邮箱")

        if not user.check_password(serializer.validated_data.get("password")):
            return error({"password": "当前密码错误"})

        user.email = None
        user.save(update_fields=["email"])
        return success(True, msg="解绑邮箱成功")

    @ip_rate_limit(60)
    @extend_schema(
        summary="发送手机验证码",
        parameters=[OpenApiParameter(name="mobile", location=OpenApiParameter.QUERY, required=True, type=str, description="手机号")],
        responses=resp("UserMobileCodeResult", serializers.BooleanField()),
    )
    @action(methods=["post"], detail=False, url_path=r"mobile/code")
    def mobile_code(self, request, *args, **kwargs):
        mobile = request.query_params.get('mobile')
        if not mobile:
            return error('手机号不能为空')
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return error('手机号格式不正确')

        result = send_mobile_code(mobile, request.user.id)
        if result.get('success'):
            return success(True, msg='验证码发送成功')
        return error(result.get('message') or '验证码发送失败', status=500)

    @extend_schema(summary="绑定或更换手机号", request=UserMobileUpdateSerializer, responses=resp("UserMobileUpdateResult", serializers.BooleanField()))
    @action(methods=["put"], detail=False, url_path="mobile")
    def mobile_update(self, request, *args, **kwargs):
        serializer = UserMobileUpdateSerializer(request.user, data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return success(True, msg='更新手机号成功')
        return error(serializer.errors)

    @extend_schema(summary="解绑手机号", request=PasswordVerifySerializer, responses=resp("UserMobileUnbindResult", serializers.BooleanField()))
    @mobile_update.mapping.delete
    def mobile_unbind(self, request, *args, **kwargs):
        serializer = PasswordVerifySerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return error(serializer.errors)

        user = request.user
        if not user.mobile:
            return error("当前账号未绑定手机号")

        if not user.check_password(serializer.validated_data.get("password")):
            return error({"password": "当前密码错误"})

        user.mobile = None
        user.save(update_fields=["mobile"])
        return success(True, msg="解绑手机号成功")

    @permission_required(["sys:user:import"])
    @extend_schema(summary="下载用户导入模板", responses={200: OpenApiTypes.BINARY})
    @action(methods=["get"], detail=False, url_path="template")
    def template(self, request, *args, **kwargs):
        from urllib.parse import quote

        excel_bytes = build_import_template_excel_bytes()
        response = HttpResponse(excel_bytes, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        filename = quote("用户导入.xlsx")
        response['Content-Disposition'] = f"attachment; filename={filename}"
        return response

    @permission_required(["sys:user:import"])
    @extend_schema(
        summary="导入用户",
        request=inline_serializer(name="UserImportRequest", fields={"file": serializers.FileField()}),
        responses=resp(
            "UserImportResult",
            inline_serializer(
                name="UserImportData",
                fields={
                    "validCount": serializers.IntegerField(),
                    "invalidCount": serializers.IntegerField(),
                    "messageList": serializers.ListField(child=serializers.CharField()),
                },
            ),
        ),
    )
    @action(methods=["post"], detail=False, url_path="import")
    def import_users(self, request, *args, **kwargs):
        if 'file' not in request.FILES:
            return error('请上传文件')
        file = request.FILES['file']
        if not file.name.endswith(('.xlsx', '.xls')):
            return error('只支持 .xlsx/.xls 文件')

        result = import_from_excel(file=file)
        return success(result["data"], msg=result["msg"])

    @permission_required(["sys:user:export"])
    @extend_schema(
        summary="导出用户",
        parameters=[
            OpenApiParameter(name="keywords", location=OpenApiParameter.QUERY, required=False, type=str, description="关键词"),
            OpenApiParameter(name="status", location=OpenApiParameter.QUERY, required=False, type=int, description="用户状态"),
            OpenApiParameter(name="deptId", location=OpenApiParameter.QUERY, required=False, type=int, description="部门ID"),
            OpenApiParameter(name="roleIds", location=OpenApiParameter.QUERY, required=False, type=str, description="角色ID列表"),
            OpenApiParameter(name="createTime", location=OpenApiParameter.QUERY, required=False, type=str, description="创建时间范围"),
            OpenApiParameter(name="field", location=OpenApiParameter.QUERY, required=False, type=str, description="排序字段"),
            OpenApiParameter(name="direction", location=OpenApiParameter.QUERY, required=False, type=str, description="排序方向"),
        ],
        responses={200: OpenApiTypes.BINARY},
    )
    @action(methods=["get"], detail=False, url_path="export")
    def export(self, request, *args, **kwargs):
        keywords = request.query_params.get('keywords', '')
        status = request.query_params.get('status')
        dept_id = request.query_params.get('deptId')
        role_ids = request.query_params.get('roleIds', '')
        create_time = request.query_params.get('createTime', '')
        field = request.query_params.get('field', 'id')
        direction = request.query_params.get('direction', 'DESC')

        excel_bytes = export_to_excel_bytes(
            keywords=keywords, status=status, dept_id=dept_id, role_ids=role_ids,
            create_time=create_time, field=field, direction=direction,
        )

        from urllib.parse import quote

        response = HttpResponse(excel_bytes, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        filename = quote("用户列表.xlsx")
        response['Content-Disposition'] = f"attachment; filename={filename}"
        return response

    @permission_required(["sys:user:list"])
    @extend_schema(summary="用户下拉选项", responses=resp("UserOptionsResult", serializers.ListField(child=serializers.DictField())))
    @action(methods=["get"], detail=False, url_path="options")
    def options(self, request, *args, **kwargs):
        data_permission = data_permission_required(request.user, "select")

        query = Q(is_deleted=0, status=1)
        if isinstance(data_permission, list) and data_permission:
            query &= Q(id__in=data_permission)

        users = User.objects.filter(query).order_by("id")
        result = [{"value": str(u.id), "label": (u.nickname or u.username)} for u in users]
        return success(result)
