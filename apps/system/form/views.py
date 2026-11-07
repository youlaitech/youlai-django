"""动态表单接口层（表单定义、渲染、数据、访问菜单、AI 生成）。"""
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from apps.system.form import serializers, services
from apps.system.logs.models import ActionType, LogModule
from apps.system.utils.decorators import operation_log
from core.permissions.decorators import permission_required
from core.response import error, success


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


class FormDefinitionListApi(APIView):
    """表单定义分页列表 / 新增"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = services.definition_page(
            keywords=request.query_params.get("keywords"),
            status=request.query_params.get("status"),
            category=request.query_params.get("category"),
            page_num=int(request.query_params.get("pageNum") or 1),
            page_size=int(request.query_params.get("pageSize") or 10),
        )
        return success(data, msg="获取表单分页成功")

    @operation_log('新增表单', module=LogModule.FORM, action_type=ActionType.INSERT)
    @permission_required(["form:definition:create"])
    def post(self, request):
        serializer = serializers.FormDefinitionSaveSerializer(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        item = services.create_definition(serializer.validated_data)
        return success({"id": str(item.id)}, msg="新增成功")


class FormDefinitionApi(APIView):
    """表单定义回显（GET /{id}/form）/ 修改（PUT /{id}）/ 删除（DELETE /{ids}）"""
    permission_classes = [IsAuthenticated]

    def get(self, request, form_id=None, ids=None):
        return success(services.definition_form(int(form_id)), msg="获取成功")

    @operation_log('修改表单', module=LogModule.FORM, action_type=ActionType.UPDATE)
    @permission_required(["form:definition:update"])
    def put(self, request, form_id=None, ids=None):
        serializer = serializers.FormDefinitionSaveSerializer(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        services.update_definition(int(form_id), serializer.validated_data)
        return success({}, msg="修改成功")

    @operation_log('删除表单', module=LogModule.FORM, action_type=ActionType.DELETE)
    @permission_required(["form:definition:delete"])
    def delete(self, request, form_id=None, ids=None):
        services.delete_definitions(form_id or ids)
        return success({}, msg="删除成功")


class FormStatusApi(APIView):
    """发布 / 停用表单"""
    permission_classes = [IsAuthenticated]

    @operation_log('表单启停', module=LogModule.FORM, action_type=ActionType.UPDATE)
    @permission_required(["form:definition:update"])
    def put(self, request, form_id, action):
        if action == "publish":
            services.publish_definition(int(form_id))
            return success({}, msg="发布成功")
        services.disable_definition(int(form_id))
        return success({}, msg="停用成功")


class FormRenderApi(APIView):
    """已发布表单渲染规则"""
    permission_classes = [IsAuthenticated]

    def get(self, request, form_key):
        return success(services.render(form_key), msg="获取成功")


class FormMenuApi(APIView):
    """表单访问菜单配置（向导回显 / 生成）"""
    permission_classes = [IsAuthenticated]

    def get(self, request, form_id):
        return success(services.get_menu(int(form_id)), msg="获取成功")

    @operation_log('生成表单菜单', module=LogModule.FORM, action_type=ActionType.INSERT)
    @permission_required(["form:definition:update"])
    def post(self, request, form_id):
        serializer = serializers.FormMenuSaveSerializer(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        services.save_menu(int(form_id), serializer.validated_data)
        return success({}, msg="菜单生成成功")


class FormOptionsApi(APIView):
    """审批表单下拉选项"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return success(services.workflow_options(), msg="获取成功")


class FormAiGenerateApi(APIView):
    """AI 生成表单规则"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = serializers.FormAiGenerateSerializer(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        rule = services.ai_generate_rule(serializer.validated_data["description"])
        return success(rule, msg="生成成功")


class FormPublicRenderApi(APIView):
    """公开表单渲染规则（匿名）"""
    permission_classes = [AllowAny]

    def get(self, request, form_key):
        return success(services.public_render(form_key), msg="获取成功")


class FormPublicDataApi(APIView):
    """匿名提交公开表单数据"""
    permission_classes = [AllowAny]

    def post(self, request, form_key):
        services.save_public_data(form_key, request.data, _client_ip(request))
        return success({}, msg="提交成功")


class FormDataApi(APIView):
    """表单数据分页 / 提交"""
    permission_classes = [IsAuthenticated]

    @permission_required(["form:data:list"])
    def get(self, request, form_key):
        data = services.data_page(
            form_key,
            int(request.query_params.get("pageNum") or 1),
            int(request.query_params.get("pageSize") or 10),
        )
        return success(data, msg="获取表单数据成功")

    @operation_log('提交表单数据', module=LogModule.FORM, action_type=ActionType.INSERT)
    def post(self, request, form_key):
        services.save_data(form_key, request.data, getattr(request.user, "id", None))
        return success({}, msg="提交成功")


class FormDataItemApi(APIView):
    """表单数据详情（GET）/ 删除（DELETE）"""
    permission_classes = [IsAuthenticated]

    @permission_required(["form:data:list"])
    def get(self, request, form_key, ids):
        return success(services.data_detail(int(ids)), msg="获取成功")

    @operation_log('删除表单数据', module=LogModule.FORM, action_type=ActionType.DELETE)
    @permission_required(["form:data:delete"])
    def delete(self, request, form_key, ids):
        services.delete_data(ids)
        return success({}, msg="删除成功")
