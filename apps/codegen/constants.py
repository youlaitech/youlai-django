"""平台-代码生成常量。

"""

from __future__ import annotations

from dataclasses import dataclass


CODE_OK = "00000"
MSG_OK = "成功"

CODEGEN_DOWNLOAD_FILE_NAME = "youlai-admin-code.zip"
CODEGEN_BACKEND_APP_NAME = "youlai-django"
CODEGEN_FRONTEND_APP_NAME = "vue3-element-admin"
DEFAULT_AUTHOR = "youlaitech"
DEFAULT_MODULE_NAME = "system"
DEFAULT_PACKAGE_NAME = ""
DEFAULT_REMOVE_TABLE_PREFIX = "sys_"

# 模块名 → 权限前缀，未配置时用模块名
PERMISSION_NAMESPACES = {"system": "sys"}


@dataclass(frozen=True)
class TemplateConfig:
    template_path: str
    subpackage_name: str
    extension: str


TEMPLATE_CONFIGS: dict[str, TemplateConfig] = {
    "API": TemplateConfig("frontend/ts/api.ts.vm", "api", ".ts"),
    "API_TYPES": TemplateConfig("frontend/ts/api-types.ts.vm", "types", ".ts"),
    "VIEW": TemplateConfig("frontend/ts/index.vue.vm", "views", ".vue"),
    "DjangoModels": TemplateConfig("backend/models.py.vm", "", ".py"),
    "DjangoSerializers": TemplateConfig("backend/serializers.py.vm", "", ".py"),
    "DjangoViews": TemplateConfig("backend/views.py.vm", "", ".py"),
    "DjangoUrls": TemplateConfig("backend/urls.py.vm", "", ".py"),
}
