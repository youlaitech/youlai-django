"""系统管理-日志模型。

"""

from django.db import models


class LogModule(models.IntegerChoices):
    """日志模块枚举"""

    LOGIN = 1, "登录"
    USER = 2, "用户管理"
    ROLE = 3, "角色管理"
    DEPT = 4, "部门管理"
    MENU = 5, "菜单管理"
    DICT = 6, "字典管理"
    CONFIG = 7, "系统配置"
    FILE = 8, "文件管理"
    NOTICE = 9, "通知公告"
    LOG = 10, "日志管理"
    CODEGEN = 11, "代码生成"
    FORM = 12, "动态表单"
    OTHER = 99, "其他"


class ActionType(models.IntegerChoices):
    """操作类型枚举"""

    LOGIN = 1, "登录"
    LOGOUT = 2, "登出"
    INSERT = 3, "新增"
    UPDATE = 4, "修改"
    DELETE = 5, "删除"
    GRANT = 6, "授权"
    EXPORT = 7, "导出"
    IMPORT = 8, "导入"
    UPLOAD = 9, "上传"
    DOWNLOAD = 10, "下载"
    CHANGE_PASSWORD = 11, "修改密码"
    RESET_PASSWORD = 12, "重置密码"
    ENABLE = 13, "启用"
    DISABLE = 14, "禁用"
    LIST = 15, "查询列表"
    OTHER = 99, "其他"

    # 新增资源专属操作类型（避免与通用 INSERT/UPDATE/DELETE 混淆）
    USER_LIST = 16, "用户列表"
    USER_CREATE = 17, "新增用户"
    USER_UPDATE = 18, "更新用户"
    USER_DELETE = 19, "删除用户"
    UPDATE_PROFILE = 20, "更新个人信息"
    CHANGE_PWD = 21, "修改密码"
    ROLE_LIST = 22, "角色列表"
    ROLE_CREATE = 23, "新增角色"
    ROLE_UPDATE = 24, "更新角色"
    ROLE_DELETE = 25, "删除角色"
    MENU_CREATE = 26, "新增菜单"
    MENU_UPDATE = 27, "更新菜单"
    MENU_DELETE = 28, "删除菜单"
    API = 29, "查询"
    DICT_CREATE = 30, "创建字典"
    DICT_UPDATE = 31, "更新字典"
    DICT_DELETE = 32, "删除字典"
    DEPT_CREATE = 33, "新增部门"
    DEPT_UPDATE = 34, "更新部门"
    DEPT_DELETE = 35, "删除部门"
    CONFIG_CREATE = 36, "新增配置"
    CONFIG_UPDATE = 37, "更新配置"
    CONFIG_DELETE = 38, "删除配置"


class Log(models.Model):
    """
    表名：sys_log
    表说明：操作日志表
    """

    module = models.SmallIntegerField(verbose_name="模块", choices=LogModule.choices)
    action_type = models.SmallIntegerField(verbose_name="操作类型", choices=ActionType.choices)
    title = models.CharField(max_length=100, verbose_name="操作标题")
    content = models.TextField(blank=True, null=True, verbose_name="自定义日志内容")
    operator_id = models.BigIntegerField(null=True, blank=True, verbose_name="操作人ID")
    operator_name = models.CharField(max_length=50, blank=True, null=True, verbose_name="操作人名称")
    request_uri = models.CharField(max_length=255, blank=True, null=True, verbose_name="请求路径")
    request_method = models.CharField(max_length=10, blank=True, null=True, verbose_name="请求方式")
    ip = models.CharField(max_length=45, blank=True, null=True, verbose_name="IP地址")
    province = models.CharField(max_length=100, blank=True, null=True, verbose_name="省份")
    city = models.CharField(max_length=100, blank=True, null=True, verbose_name="城市")
    device = models.CharField(max_length=100, blank=True, null=True, verbose_name="设备")
    os = models.CharField(max_length=100, blank=True, null=True, verbose_name="操作系统")
    browser = models.CharField(max_length=100, blank=True, null=True, verbose_name="浏览器")
    status = models.SmallIntegerField(default=1, verbose_name="状态：0失败 1成功")
    error_msg = models.CharField(max_length=255, blank=True, null=True, verbose_name="错误信息")
    execution_time = models.IntegerField(blank=True, null=True, verbose_name="执行时间(ms)")
    create_time = models.DateTimeField(null=True, blank=True, verbose_name="创建时间")

    class Meta:
        db_table = "sys_log"
        verbose_name = "日志表"
        verbose_name_plural = "日志表"

    def __str__(self):
        return f"{self.title} - {self.request_method}"
