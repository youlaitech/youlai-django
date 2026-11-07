from __future__ import annotations

import django_filters
from django.db.models import Q

from apps.system.dept.models import Department


class DeptFilter(django_filters.FilterSet):
    """部门树筛选器。"""

    keywords = django_filters.CharFilter(method="filter_keywords")
    status = django_filters.CharFilter(method="filter_status")

    class Meta:
        model = Department
        fields: list[str] = []

    def filter_keywords(self, queryset, name, value):
        if not value:
            return queryset

        matching = Department.objects.filter(name__icontains=value, is_deleted=0).only("id", "tree_path", "parent_id")
        if not matching.exists():
            return queryset.none()

        include_ids: set[int] = set()
        for dept in matching:
            include_ids.add(int(dept.id))
            if dept.parent_id is not None:
                try:
                    include_ids.add(int(dept.parent_id))
                except (TypeError, ValueError):
                    pass
            if dept.tree_path:
                for pid in str(dept.tree_path).split(","):
                    pid = pid.strip()
                    if not pid:
                        continue
                    try:
                        include_ids.add(int(pid))
                    except (TypeError, ValueError):
                        continue

        return queryset.filter(Q(id__in=include_ids) | Q(parent_id__in=include_ids))

    def filter_status(self, queryset, name, value):
        if value is None or value == "":
            return queryset
        try:
            return queryset.filter(status=int(value))
        except (TypeError, ValueError):
            return queryset
