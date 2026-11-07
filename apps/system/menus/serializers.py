"""系统管理-菜单序列化器。

"""

from rest_framework import serializers
from core.serializers import BigIntAsStringField, StandardModelSerializer

from apps.system.menus.models import Menu
from apps.system.menus.services import (
    create_crud_buttons,
    menu_tree_path_of,
    resolve_next_sort,
    validate_menu_parent,
)
from apps.system.roles.models import RoleMenu
from apps.system.users.models import UserRole
from django.db.models import Q
from django.utils import timezone
import json


class MenuSerializer(StandardModelSerializer):
    """菜单序列化器，支持递归序列化子菜单"""
    id = BigIntAsStringField(read_only=True)
    parentId = BigIntAsStringField(source='parent_id', read_only=True)
    routeName = serializers.CharField(source='route_name', read_only=True, allow_null=True)
    routePath = serializers.CharField(source='route_path', read_only=True, allow_null=True)
    externalUrl = serializers.CharField(source='external_url', read_only=True, allow_null=True)
    children = serializers.SerializerMethodField()

    class Meta:
        model = Menu
        fields = ['id', 'parentId', 'name', 'type', 'routeName', 'routePath', 'component',
                  'sort', 'visible', 'icon', 'redirect', 'perm', 'externalUrl', 'children']

    def get_children(self, obj):
        """获取子菜单"""
        # 获取上下文中的visible参数，用于过滤菜单状态
        visible = self.context.get('visible')

        # 构建查询条件
        query = Q(parent_id=obj.id)

        # 如果指定了visible参数，则添加状态过滤
        if visible is not None:
            query &= Q(visible=visible)

        # 查询子菜单并按排序字段和ID排序
        children = Menu.objects.filter(query).order_by('sort', 'id')

        # 递归序列化子菜单
        return MenuSerializer(children, many=True, context=self.context).data

    def to_representation(self, instance):
        """重写to_representation方法，将id和parentId转换为字符串类型"""
        ret = super().to_representation(instance)
        # 将id和parentId转换为字符串类型
        ret['id'] = str(ret['id'])
        ret['parentId'] = str(ret['parentId'])

        # 如果children为空列表，则删除该字段
        if 'children' in ret and not ret['children']:
            del ret['children']

        return ret


class MenuOptionSerializer(StandardModelSerializer):
    """菜单下拉选项序列化器"""
    value = serializers.SerializerMethodField()
    label = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()

    class Meta:
        model = Menu
        fields = ['value', 'label', 'children']

    def get_value(self, obj):
        """获取菜单ID作为value"""
        return str(obj.id)

    def get_label(self, obj):
        """获取菜单名称作为label"""
        return obj.name

    def get_children(self, obj):
        """获取子菜单选项"""
        # 按上下文 types 过滤子节点类型（为空表示全部类型）
        types = self.context.get('types') or []

        query = Q(parent_id=obj.id)
        if types:
            query &= Q(type__in=types)

        # 查询子菜单并按排序字段和ID排序
        children = Menu.objects.filter(query).order_by('sort', 'id')

        # 递归序列化子菜单
        return MenuOptionSerializer(children, many=True, context=self.context).data

    def to_representation(self, instance):
        """重写to_representation方法，处理value和children字段"""
        ret = super().to_representation(instance)

        # 如果children为空列表，则删除该字段
        if 'children' in ret and not ret['children']:
            del ret['children']

        return ret


class KeyValueSerializer(serializers.Serializer):
    """键值对序列化器，用于菜单参数"""
    key = serializers.CharField(required=True)
    value = serializers.CharField(required=True)


class MenuCreateSerializer(StandardModelSerializer):
    """菜单创建序列化器"""
    parentId = BigIntAsStringField(source='parent_id', required=False, default=0)
    routeName = serializers.CharField(source='route_name', required=False, allow_null=True, allow_blank=True)
    routePath = serializers.CharField(source='route_path', required=False, allow_null=True, allow_blank=True)
    keepAlive = serializers.IntegerField(source='keep_alive', required=False, allow_null=True, default=0)
    generateCrudButtons = serializers.BooleanField(required=False, default=False, write_only=True)
    buttonPermPrefix = serializers.CharField(required=False, allow_null=True, allow_blank=True, write_only=True)
    params = serializers.ListField(child=KeyValueSerializer(), required=False, allow_null=True, allow_empty=True)
    externalUrl = serializers.CharField(source='external_url', required=False, allow_null=True, allow_blank=True)

    class Meta:
        model = Menu
        fields = ['id', 'parentId', 'name', 'type', 'routeName', 'routePath', 'component',
                  'perm', 'visible', 'sort', 'icon', 'redirect', 'keepAlive',
                  'params', 'externalUrl', 'generateCrudButtons', 'buttonPermPrefix']
        extra_kwargs = {
            'name': {'required': True},
            'type': {'required': True},
            'visible': {'required': False, 'default': 1},
            'sort': {'required': False},
            'icon': {'required': False, 'allow_blank': True, 'allow_null': True},
            'redirect': {'required': False, 'allow_blank': True, 'allow_null': True},
            'component': {'required': False, 'allow_blank': True, 'allow_null': True},
            'perm': {'required': False, 'allow_blank': True, 'allow_null': True},
        }

    def validate(self, attrs):
        """验证菜单属性"""
        if attrs.get('keep_alive') is None:
            attrs['keep_alive'] = 0

        menu_type = attrs.get('type')
        parent_id = attrs.get('parent_id', 0)
        is_external = menu_type == 'E'
        is_embedded = is_external and attrs.get('component') == 'iframe'
        needs_route_name = menu_type == 'M' or is_embedded

        if needs_route_name:
            route_name = attrs.get('route_name')
            if route_name and Menu.objects.filter(route_name=route_name).exists():
                raise serializers.ValidationError({"routeName": "路由名称已存在"})
        else:
            attrs['route_name'] = None

        if menu_type == 'C':
            attrs['component'] = 'Layout'
            if parent_id == 0 and 'route_path' in attrs:
                rp = attrs['route_path']
                if rp and not rp.startswith('/'):
                    attrs['route_path'] = '/' + rp
        elif is_external and not is_embedded:
            attrs['component'] = None
        elif menu_type == 'B' and not attrs.get('perm'):
            raise serializers.ValidationError({"perm": "按钮类型必须设置权限标识"})

        return attrs

    def create(self, validated_data):
        """创建菜单"""
        # 父级层级校验：按钮只能挂在菜单下，其他类型只能挂在顶级或目录下
        parent = validate_menu_parent(validated_data.get('type'), validated_data.get('parent_id', 0))

        # 提取并移除设计期参数，避免写入模型字段
        generate_crud_buttons = validated_data.pop('generateCrudButtons', False)
        button_perm_prefix = validated_data.pop('buttonPermPrefix', None)

        # 提取并移除params字段
        params_data = validated_data.pop('params', [])

        parent_id = validated_data.get('parent_id', 0)

        # 未指定排序时排到同级末尾
        if validated_data.get('sort') is None:
            validated_data['sort'] = resolve_next_sort(parent_id)

        # 父节点ID路径（含父不含己），顶级菜单固定为 0
        validated_data['tree_path'] = menu_tree_path_of(parent) if parent else '0'

        validated_data['create_time'] = timezone.now()

        # 处理params字段 - 转换为dict格式存储
        if params_data:
            validated_data['params'] = {item['key']: item['value'] for item in params_data}
        else:
            validated_data['params'] = None

        menu = Menu.objects.create(**validated_data)

        # 新增页面菜单时按需生成增删改查按钮
        if generate_crud_buttons and button_perm_prefix and button_perm_prefix.strip():
            create_crud_buttons(menu, button_perm_prefix.strip())

        return menu


class MenuUpdateSerializer(StandardModelSerializer):
    """菜单更新序列化器"""
    id = BigIntAsStringField(read_only=True)
    parentId = BigIntAsStringField(source='parent_id', required=False)
    routeName = serializers.CharField(source='route_name', required=False, allow_null=True, allow_blank=True)
    routePath = serializers.CharField(source='route_path', required=False, allow_null=True, allow_blank=True)
    keepAlive = serializers.IntegerField(source='keep_alive', required=False, allow_null=True)
    params = serializers.ListField(child=KeyValueSerializer(), required=False, allow_null=True, allow_empty=True)
    externalUrl = serializers.CharField(source='external_url', required=False, allow_null=True, allow_blank=True)

    class Meta:
        model = Menu
        fields = ['id', 'parentId', 'name', 'type', 'routeName', 'routePath', 'component',
                  'perm', 'visible', 'sort', 'icon', 'redirect', 'keepAlive',
                  'params', 'externalUrl']
        extra_kwargs = {
            'name': {'required': False},
            'type': {'required': False},
            'visible': {'required': False},
            'sort': {'required': False},
            'icon': {'required': False, 'allow_blank': True, 'allow_null': True},
            'redirect': {'required': False, 'allow_blank': True, 'allow_null': True},
            'component': {'required': False, 'allow_blank': True, 'allow_null': True},
            'perm': {'required': False, 'allow_blank': True, 'allow_null': True},
        }

    def validate(self, attrs):
        """验证菜单属性"""
        if 'keep_alive' in attrs and attrs.get('keep_alive') is None:
            attrs['keep_alive'] = 0

        # parentId 不能指向自己
        if 'parent_id' in attrs and 'id' in attrs:
            if attrs['parent_id'] == attrs.get('id') or (
                self.instance and attrs['parent_id'] == self.instance.id
            ):
                raise serializers.ValidationError({"parentId": "父级菜单不能为当前菜单"})

        menu_type = attrs.get('type')
        if menu_type is None and self.instance is not None:
            menu_type = getattr(self.instance, 'type', None)

        parent_id = attrs.get('parent_id')
        if parent_id is None and self.instance is not None:
            parent_id = getattr(self.instance, 'parent_id', 0)

        # 父级层级校验：父级变更时才校验，未变更时放行历史遗留的非法层级
        current_parent_id = self.instance.parent_id if self.instance is not None else None
        validate_menu_parent(menu_type, parent_id, current_parent_id)

        is_external = menu_type == 'E'
        is_embedded = is_external and attrs.get('component') == 'iframe'
        needs_route_name = menu_type == 'M' or is_embedded

        if needs_route_name:
            route_name = attrs.get('route_name')
            if route_name is None and self.instance is not None:
                route_name = getattr(self.instance, 'route_name', None)
            if route_name:
                instance = self.instance
                qs = Menu.objects.filter(route_name=route_name)
                if instance:
                    qs = qs.exclude(id=instance.id)
                if qs.exists():
                    raise serializers.ValidationError({"routeName": "路由名称已存在"})
        elif 'route_name' in attrs:
            attrs['route_name'] = None

        if menu_type == 'C':
            attrs['component'] = 'Layout'
            if parent_id == 0 and 'route_path' in attrs:
                rp = attrs['route_path']
                if rp and not rp.startswith('/'):
                    attrs['route_path'] = '/' + rp
        elif is_external and not is_embedded:
            attrs['component'] = None
        elif menu_type == 'B' and 'perm' in attrs and not attrs.get('perm'):
            raise serializers.ValidationError({"perm": "按钮类型必须设置权限标识"})

        return attrs

    def update(self, instance, validated_data):
        """更新菜单"""
        # 提取并移除params字段
        params_data = validated_data.pop('params', None)

        parent_id = validated_data.get('parent_id')

        # 父级变更时同步 tree_path（父节点ID路径，含父不含己），顶级为 0
        if parent_id is not None and parent_id != instance.parent_id:
            parent = Menu.objects.filter(id=parent_id).first() if parent_id else None
            if parent is None and parent_id != 0:
                raise serializers.ValidationError({"parentId": "父菜单不存在"})
            validated_data['tree_path'] = menu_tree_path_of(parent) if parent else '0'

        validated_data['update_time'] = timezone.now()

        # 处理params字段 - 转换为dict格式存储
        if 'params' in self.initial_data:
            if params_data is None or params_data == []:
                validated_data['params'] = None
            else:
                validated_data['params'] = {item['key']: item['value'] for item in params_data}

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        return instance


class MenuRouteSerializer(serializers.ModelSerializer):
    """菜单路由序列化器"""
    path = serializers.SerializerMethodField()
    component = serializers.SerializerMethodField()
    redirect = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    meta = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()

    class Meta:
        model = Menu
        fields = ['path', 'component', 'redirect', 'name', 'meta', 'children']

    def get_path(self, obj):
        """获取路由路径"""
        is_external = obj.type == 'E'
        is_embedded = is_external and obj.component == 'iframe'
        if is_external and not is_embedded and obj.external_url:
            return obj.external_url
        return obj.route_path or ''

    def get_component(self, obj):
        """获取组件路径"""
        is_external = obj.type == 'E'
        is_embedded = is_external and obj.component == 'iframe'
        if is_embedded:
            return 'iframe'
        if is_external:
            return None
        return obj.component or None

    def get_redirect(self, obj):
        """获取跳转链接"""
        return obj.redirect or ''

    def get_name(self, obj):
        """获取路由名称"""
        if obj.type == 'E':
            return obj.route_name or ''
        return obj.route_name or obj.route_path or ''

    def get_meta(self, obj):
        """获取路由元数据"""
        is_external = obj.type == 'E'
        is_embedded = is_external and obj.component == 'iframe'
        meta = {
            'title': obj.name,
            'icon': obj.icon or '',
            'hidden': obj.visible == 0,
            'keepAlive': (obj.type == 'M' or is_embedded) and bool(obj.keep_alive),
            'params': obj.params
        }
        if is_external and obj.external_url:
            meta['externalUrl'] = obj.external_url
        return meta

    def get_children(self, obj):
        """获取子路由"""
        # 获取上下文中的menu_ids参数，用于过滤菜单
        menu_ids = self.context.get('menu_ids', [])

        # 构建查询条件
        query = Q(parent_id=obj.id)

        # routes 仅返回目录(C)/菜单(M)，按钮(B)只用于权限标识，不应出现在路由树
        query &= ~Q(type='B')

        # 如果指定了menu_ids参数，则添加ID过滤
        if menu_ids:
            query &= Q(id__in=menu_ids)

        # 查询子菜单并按排序字段和ID排序
        children = Menu.objects.filter(query).order_by('sort', 'id')

        # 递归序列化子菜单
        return MenuRouteSerializer(children, many=True, context=self.context).data


class MenuFormSerializer(StandardModelSerializer):
    """菜单表单序列化器"""
    id = BigIntAsStringField(read_only=True)
    parentId = BigIntAsStringField(source='parent_id')
    routeName = serializers.CharField(source='route_name', allow_null=True)
    routePath = serializers.CharField(source='route_path', allow_null=True)
    keepAlive = serializers.IntegerField(source='keep_alive', allow_null=True)

    externalUrl = serializers.CharField(source='external_url', allow_null=True)

    class Meta:
        model = Menu
        fields = ['id', 'parentId', 'name', 'type', 'routeName', 'routePath',
                  'component', 'perm', 'visible', 'sort', 'icon', 'redirect',
                  'keepAlive', 'params', 'externalUrl']

    def to_representation(self, instance):
        """重写to_representation方法，将id和parentId转换为字符串类型"""
        ret = super().to_representation(instance)

        # 将id转换为字符串类型
        if ret['id'] is not None:
            ret['id'] = str(ret['id'])

        # 将parentId转换为字符串类型
        if ret['parentId'] is not None:
            ret['parentId'] = str(ret['parentId'])

        if ret.get('keepAlive') is None:
            ret['keepAlive'] = 0

        # 处理params字段 - dict转换为KeyValue列表
        if instance.params:
            ret['params'] = [{"key": k, "value": v} for k, v in instance.params.items()]
        else:
            ret['params'] = None

        return ret


class MenuAiFillSerializer(serializers.Serializer):
    """菜单 AI 推断入参"""
    name = serializers.CharField(required=True, allow_blank=False)
    type = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    parentId = BigIntAsStringField(required=False, allow_null=True)


class MenuAiFillResultSerializer(serializers.Serializer):
    """菜单 AI 推断结果"""
    routePath = serializers.CharField(allow_null=True)
    perm = serializers.CharField(allow_null=True)
    iconKeywords = serializers.ListField(child=serializers.CharField(), allow_empty=True)
