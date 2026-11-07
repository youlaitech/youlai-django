from __future__ import annotations

import django_filters

from apps.system.configs.models import SysConfig


class ConfigFilter(django_filters.FilterSet):
    """系统配置列表筛选器。"""

    configName = django_filters.CharFilter(field_name="config_name", lookup_expr="icontains")
    configKey = django_filters.CharFilter(field_name="config_key", lookup_expr="icontains")

    class Meta:
        model = SysConfig
        fields: list[str] = []
