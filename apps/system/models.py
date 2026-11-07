"""系统数据模型定义。"""

from apps.codegen.models import GenTable, GenTableColumn
from apps.system.configs.models import SysConfig
from apps.system.dept.models import Department
from apps.system.dicts.models import Dictionary, DictionaryItem
from apps.system.form.models import FormData, FormDefinition, FormSnapshot
from apps.system.logs.models import Log
from apps.system.menus.models import Menu
from apps.system.notices.models import Notice, UserNotice
from apps.system.roles.models import Role, RoleMenu
from apps.system.users.models import User, UserRole

__all__ = [
    "Department",
    "Dictionary",
    "DictionaryItem",
    "FormData",
    "FormDefinition",
    "FormSnapshot",
    "GenTable",
    "GenTableColumn",
    "Log",
    "Menu",
    "Notice",
    "Role",
    "RoleMenu",
    "SysConfig",
    "User",
    "UserNotice",
    "UserRole",
]