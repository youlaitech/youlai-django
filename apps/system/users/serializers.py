"""用户序列化器。"""
from rest_framework import serializers

from core.serializers import BigIntAsStringField, StandardModelSerializer
from core.validators import MOBILE_PATTERN, MOBILE_PATTERN_ALLOW_EMPTY, EMAIL_PATTERN

from apps.system.dept.models import Department
from apps.system.menus.models import Menu
from apps.system.roles.models import Role
from apps.system.users.models import User


class UserInfoSerializer(StandardModelSerializer):
    """用户信息序列化器"""
    userId = BigIntAsStringField(source='id')
    roles = serializers.SerializerMethodField()
    perms = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['userId', 'username', 'nickname', 'avatar', 'roles', 'perms']

    @staticmethod
    def get_roles(obj):
        """获取用户角色列表"""
        return [role.code for role in obj.roles.all()]

    @staticmethod
    def get_perms(obj):
        """获取用户权限列表"""
        from core.permissions.role_perm_service import get_role_perms, refresh_role_perms_cache_batch

        role_codes = [role.code for role in obj.roles.all()]
        if not role_codes:
            return []

        perms = get_role_perms(role_codes)
        # 缓存未命中时触发全量刷新（防止 DB 数据已更新但缓存未同步）
        if not perms:
            refresh_role_perms_cache_batch(role_codes)
            perms = get_role_perms(role_codes)

        return perms


class UserPageSerializer(StandardModelSerializer):
    """用户分页查询序列化器"""
    deptName = serializers.SerializerMethodField()
    roleNames = serializers.SerializerMethodField()
    createTime = serializers.DateTimeField(source='date_joined')

    class Meta:
        model = User
        fields = ['id', 'username', 'nickname', 'mobile', 'gender', 'avatar',
                  'email', 'status', 'deptName', 'roleNames', 'createTime']

    @staticmethod
    def get_deptName(obj):
        """获取部门名称"""
        if obj.dept:
            return obj.dept.name
        return ""

    @staticmethod
    def get_roleNames(obj):
        """获取角色名称（逗号分隔）"""
        roles = obj.roles.all()
        if roles:
            return ", ".join([role.name for role in roles])
        return ""


class UserFormSerializer(StandardModelSerializer):
    """用户表单序列化器"""
    deptId = BigIntAsStringField(source='dept_id', allow_null=True)
    roleIds = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'nickname', 'mobile', 'gender', 'avatar',
                  'email', 'status', 'deptId', 'roleIds']

    @staticmethod
    def get_roleIds(obj):
        """获取用户角色ID列表"""
        return [str(role_id) for role_id in obj.roles.values_list('id', flat=True)]


class UserCreateSerializer(StandardModelSerializer):
    """用户创建序列化器"""
    roleIds = serializers.ListField(
        child=serializers.IntegerField(),
        required=True,
        write_only=True,
        help_text="角色ID列表"
    )
    deptId = serializers.IntegerField(required=False, allow_null=True, write_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'nickname', 'password', 'mobile', 'gender',
                  'avatar', 'email', 'status', 'deptId', 'roleIds']
        extra_kwargs = {
            'password': {'write_only': True, 'required': False, 'allow_blank': True},
            'status': {'required': False, 'default': 1},
            'gender': {'required': False, 'default': 1},
        }

    @staticmethod
    def validate_mobile(value):
        if value and not MOBILE_PATTERN_ALLOW_EMPTY.match(value):
            raise serializers.ValidationError("手机号格式不正确")
        return value

    def create(self, validated_data):
        role_ids = validated_data.pop('roleIds', [])
        dept_id = validated_data.pop('deptId', None)

        if dept_id is not None:
            validated_data['dept_id'] = dept_id

        # email 数据库列 NOT NULL，null 转空字符串
        if 'email' in validated_data and validated_data['email'] is None:
            validated_data['email'] = ''

        # 移除非模型字段（dept_id 是 FK 隐藏字段，需保留）
        field_names = {f.name for f in User._meta.get_fields()}
        field_names.add('dept_id')
        for key in list(validated_data.keys()):
            if key not in field_names:
                validated_data.pop(key, None)

        password = validated_data.pop('password', None) or '123456'
        user = User(**validated_data)
        user.set_password(password)
        user.save()

        if role_ids:
            roles = Role.objects.filter(id__in=role_ids)
            user.roles.set(roles)

        return user


class UserUpdateSerializer(StandardModelSerializer):
    """用户更新序列化器"""
    roleIds = serializers.SerializerMethodField()
    deptId = BigIntAsStringField(source='dept_id', required=False, allow_null=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'nickname', 'mobile', 'gender',
                  'avatar', 'email', 'status', 'deptId', 'roleIds']
        extra_kwargs = {
            'username': {'required': True},
            'nickname': {'required': True},
            'email': {'allow_null': True},
            'avatar': {'allow_null': True},
            'mobile': {'allow_null': True},
        }

    @staticmethod
    def get_roleIds(obj):
        """获取用户角色ID"""
        return [str(role_id) for role_id in obj.roles.values_list('id', flat=True)]

    @staticmethod
    def validate_mobile(value):
        if value and not MOBILE_PATTERN_ALLOW_EMPTY.match(value):
            raise serializers.ValidationError("手机号格式不正确")
        return value

    def update(self, instance, validated_data):
        """更新用户"""
        role_ids = self.initial_data.get('roleIds', None)
        dept_id = validated_data.pop('dept_id', None)

        if dept_id is not None:
            validated_data['dept_id'] = dept_id

        # email 数据库列 NOT NULL，null 转空字符串
        if 'email' in validated_data and validated_data['email'] is None:
            validated_data['email'] = ''

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if role_ids is not None:
            roles = Role.objects.filter(id__in=role_ids)
            instance.roles.set(roles)

        return instance


class UserPasswordResetSerializer(serializers.Serializer):
    """用户密码重置序列化器"""
    password = serializers.CharField(required=True, write_only=True)

    def update(self, instance, validated_data):
        """更新用户密码"""
        password = validated_data.get('password')
        if password:
            instance.set_password(password)
            instance.save(update_fields=['password'])
        return instance


class UserStatusSerializer(serializers.Serializer):
    """用户状态序列化器"""
    status = serializers.IntegerField(required=True)

    @staticmethod
    def validate_status(value):
        """验证用户状态"""
        if value not in [0, 1]:
            raise serializers.ValidationError("用户状态不正确，应为 0(禁用) 或 1(启用)")
        return value

    def update(self, instance, validated_data):
        """更新用户状态"""
        status = validated_data.get('status')
        instance.status = status
        instance.save(update_fields=['status'])
        return instance


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    """用户个人资料更新序列化器"""

    class Meta:
        model = User
        fields = ['nickname', 'avatar', 'gender', 'mobile', 'email']

    @staticmethod
    def validate_mobile(value):
        if value and not MOBILE_PATTERN.match(value):
            raise serializers.ValidationError("手机号格式不正确")
        return value

    @staticmethod
    def validate_email(value):
        if value and not EMAIL_PATTERN.match(value):
            raise serializers.ValidationError("邮箱格式不正确")
        return value

    @staticmethod
    def validate_gender(value):
        """验证性别值"""
        if value not in [0, 1, 2]:
            raise serializers.ValidationError("性别值不正确，应为 0(保密)、1(男) 或 2(女)")
        return value


class UserPasswordChangeSerializer(serializers.Serializer):
    """用户密码修改序列化器"""
    oldPassword = serializers.CharField(required=True, write_only=True, help_text="原密码")
    newPassword = serializers.CharField(required=True, write_only=True, help_text="新密码")
    confirmPassword = serializers.CharField(required=True, write_only=True, help_text="确认密码")

    def validate(self, attrs):
        """验证密码"""
        user = self.context['request'].user

        # 验证原密码
        if not user.check_password(attrs.get('oldPassword')):
            raise serializers.ValidationError({"oldPassword": "原密码不正确"})

        # 验证新密码
        if attrs.get('oldPassword') == attrs.get('newPassword'):
            raise serializers.ValidationError({"newPassword": "新密码不能与原密码相同"})

        if attrs.get('newPassword') != attrs.get('confirmPassword'):
            raise serializers.ValidationError({"confirmPassword": "新密码和确认密码不一致"})

        return attrs

    def update(self, instance, validated_data):
        """更新用户密码"""
        instance.set_password(validated_data.get('newPassword'))
        instance.save(update_fields=['password'])
        return instance


class UserEmailUpdateSerializer(serializers.Serializer):
    """用户邮箱更新序列化器"""
    email = serializers.EmailField(required=True, help_text="新邮箱")
    code = serializers.CharField(required=True, help_text="邮箱验证码")
    password = serializers.CharField(required=True, write_only=True, help_text="当前密码")

    @staticmethod
    def validate_email(value):
        if not EMAIL_PATTERN.match(value):
            raise serializers.ValidationError("邮箱格式不正确")
        return value

    def validate(self, attrs):
        """验证邮箱验证码"""
        email = attrs.get('email')
        code = attrs.get('code')
        password = attrs.get('password')

        user_id = self.context['request'].user.id
        user = self.context['request'].user

        if not user.check_password(password):
            raise serializers.ValidationError({"password": "当前密码错误"})

        exists = User.objects.filter(email=email, is_deleted=0).exclude(id=user_id).exists()
        if exists:
            raise serializers.ValidationError({"email": "邮箱已被其他账号绑定"})

        # 验证邮箱验证码
        from apps.utils.email_utils import verify_email_code
        if not verify_email_code(email, code, user_id):
            raise serializers.ValidationError({"code": "邮箱验证码错误或已过期"})

        return attrs

    def update(self, instance, validated_data):
        """更新用户邮箱"""
        instance.email = validated_data.get('email')
        instance.save(update_fields=['email'])
        return instance


class UserMobileUpdateSerializer(serializers.Serializer):
    """用户手机号更新序列化器"""
    mobile = serializers.CharField(required=True, help_text="新手机号")
    code = serializers.CharField(required=True, help_text="手机验证码")
    password = serializers.CharField(required=True, write_only=True, help_text="当前密码")

    @staticmethod
    def validate_mobile(value):
        if not MOBILE_PATTERN.match(value):
            raise serializers.ValidationError("手机号格式不正确")
        return value

    def validate(self, attrs):
        """验证手机验证码"""
        mobile = attrs.get('mobile')
        code = attrs.get('code')
        password = attrs.get('password')

        user_id = self.context['request'].user.id
        user = self.context['request'].user

        if not user.check_password(password):
            raise serializers.ValidationError({"password": "当前密码错误"})

        exists = User.objects.filter(mobile=mobile, is_deleted=0).exclude(id=user_id).exists()
        if exists:
            raise serializers.ValidationError({"mobile": "手机号已被其他账号绑定"})

        # 验证手机验证码
        from apps.utils.mobile_utils import verify_mobile_code
        if not verify_mobile_code(mobile, code, user_id):
            raise serializers.ValidationError({"code": "手机验证码错误或已过期"})

        return attrs

    def update(self, instance, validated_data):
        """更新用户手机号"""
        instance.mobile = validated_data.get('mobile')
        instance.save(update_fields=['mobile'])
        return instance


class PasswordVerifySerializer(serializers.Serializer):
    password = serializers.CharField(required=True, write_only=True, help_text="当前密码")


class DepartmentOptionSerializer(serializers.ModelSerializer):
    """部门选项序列化器"""
    value = serializers.SerializerMethodField()
    label = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = ['value', 'label', 'children']

    def get_value(self, obj):
        """获取部门ID作为 value"""
        return str(obj.id)

    @staticmethod
    def get_label(obj):
        """获取部门名称作为 label"""
        return obj.name

    @staticmethod
    def get_children(obj):
        """递归获取子部门"""
        children = Department.objects.filter(
            parent_id=obj.id,
            status=1,
            is_deleted=0
        ).order_by('sort')

        if children.exists():
            # 递归序列化子部门
            return DepartmentOptionSerializer(children, many=True).data
        return []
