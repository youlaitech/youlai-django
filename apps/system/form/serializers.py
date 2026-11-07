"""动态表单序列化器：入参校验与出参结构。"""
from rest_framework import serializers

from apps.system.form.models import FormData, FormDefinition


class FormDefinitionSerializer(serializers.ModelSerializer):
    """表单定义出参（键名由视图层统一转驼峰）"""

    class Meta:
        model = FormDefinition
        fields = [
            "id",
            "form_key",
            "form_name",
            "description",
            "form_json",
            "options_json",
            "status",
            "is_public",
            "category",
            "menu_id",
            "version",
            "create_time",
        ]


class FormDefinitionSaveSerializer(serializers.Serializer):
    """表单定义入参"""

    formKey = serializers.CharField(max_length=64)
    formName = serializers.CharField(max_length=100)
    description = serializers.CharField(max_length=255, required=False, allow_null=True, allow_blank=True)
    formJson = serializers.JSONField(required=False, allow_null=True)
    optionsJson = serializers.JSONField(required=False, allow_null=True)
    isPublic = serializers.IntegerField(required=False, allow_null=True)
    category = serializers.CharField(max_length=16, required=False, allow_null=True, allow_blank=True)


class FormDataSerializer(serializers.ModelSerializer):
    """表单数据出参"""

    class Meta:
        model = FormData
        fields = ["id", "form_version", "data_json", "create_by", "create_time"]


class FormMenuSaveSerializer(serializers.Serializer):
    """表单访问菜单生成入参"""

    menuName = serializers.CharField(max_length=50)
    parentId = serializers.IntegerField(required=False, allow_null=True)
    roleIds = serializers.ListField(child=serializers.IntegerField(), required=False, allow_null=True)


class FormAiGenerateSerializer(serializers.Serializer):
    """AI 生成表单规则入参"""

    description = serializers.CharField()
