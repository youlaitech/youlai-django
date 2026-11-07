"""系统管理-日志序列化器。

"""

from rest_framework import serializers
from core.serializers import BigIntAsStringField, StandardModelSerializer

from apps.system.logs.models import Log, LogModule, ActionType


class LogPageSerializer(StandardModelSerializer):
    """日志分页列表序列化器"""

    module = serializers.SerializerMethodField()
    actionType = serializers.SerializerMethodField(source='action_type')
    title = serializers.CharField()
    content = serializers.CharField()
    operatorId = BigIntAsStringField(source='operator_id')
    operatorName = serializers.CharField(source='operator_name')
    status = serializers.IntegerField()
    requestUri = serializers.CharField(source='request_uri')
    requestMethod = serializers.CharField(source='request_method')
    region = serializers.SerializerMethodField()
    executionTime = serializers.IntegerField(source='execution_time')
    errorMsg = serializers.CharField(source='error_msg')
    createTime = serializers.DateTimeField(source='create_time', format='%Y-%m-%d %H:%M:%S')

    class Meta:
        model = Log
        fields = ['id', 'module', 'actionType', 'title', 'content', 'operatorId', 'operatorName',
                  'status', 'requestUri', 'requestMethod', 'ip', 'region', 'device', 'browser', 'os',
                  'executionTime', 'errorMsg', 'createTime']

    def get_module(self, obj):
        if obj.module is None:
            return None
        return LogModule(obj.module).label if obj.module in dict(LogModule.choices).keys() else "其他"

    def get_actionType(self, obj):
        if obj.action_type is None:
            return None
        return ActionType(obj.action_type).label if obj.action_type in dict(ActionType.choices).keys() else "其他"

    def get_region(self, obj):
        if obj.province and obj.city:
            return f"{obj.province} {obj.city}"
        elif obj.province:
            return obj.province
        elif obj.city:
            return obj.city
        return None
