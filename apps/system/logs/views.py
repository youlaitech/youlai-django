"""系统管理-日志视图。

"""

from datetime import datetime, timedelta

from django.db import models
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.system.logs.models import Log
from core.openapi import page_resp, resp
from core.pagination import StandardResultsPagination
from core.permissions.decorators import permission_required
from core.permissions.perms import HasPerm
from core.response import error, success
from core.viewsets import BaseModelViewSet

from .filters import LogFilter
from .serializers import LogPageSerializer


@extend_schema(tags=["09.日志接口"])
class LogViewSet(BaseModelViewSet):
    """日志管理"""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, HasPerm]
    pagination_class = StandardResultsPagination
    queryset = Log.objects.order_by("-create_time")
    filterset_class = LogFilter

    def get_serializer_class(self):
        return LogPageSerializer

    @permission_required(["sys:log:list"])
    @extend_schema(
        summary="日志分页列表",
        parameters=[
            OpenApiParameter(
                name="keywords",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="关键词",
            ),
            OpenApiParameter(
                name="createTime",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="创建时间范围：start,end",
            ),
            OpenApiParameter(
                name="pageNum",
                location=OpenApiParameter.QUERY,
                required=False,
                type=int,
                description="页码（默认 1）",
            ),
            OpenApiParameter(
                name="pageSize",
                location=OpenApiParameter.QUERY,
                required=False,
                type=int,
                description="每页记录数（默认 10）",
            ),
        ],
        responses=page_resp("LogPageResult", LogPageSerializer(many=True)),
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="访问趋势统计",
        parameters=[
            OpenApiParameter(
                name="startDate",
                location=OpenApiParameter.QUERY,
                required=True,
                type=str,
                description="开始日期（YYYY-MM-DD）",
            ),
            OpenApiParameter(
                name="endDate",
                location=OpenApiParameter.QUERY,
                required=True,
                type=str,
                description="结束日期（YYYY-MM-DD）",
            ),
        ],
        responses=resp(
            "VisitTrendResult",
            inline_serializer(
                name="VisitTrendData",
                fields={
                    "dates": serializers.ListField(child=serializers.CharField()),
                    "pvList": serializers.ListField(child=serializers.IntegerField()),
                    "uvList": serializers.ListField(child=serializers.IntegerField()),
                },
            ),
        ),
    )
    @action(methods=["get"], detail=False, url_path="analytics/trend", permission_classes=[AllowAny])
    def views_trend(self, request, *args, **kwargs):
        start_date_str = request.query_params.get("startDate", "")
        end_date_str = request.query_params.get("endDate", "")

        if not start_date_str or not end_date_str:
            return error("开始日期和结束日期不能为空")

        try:
            start_date = timezone.make_aware(datetime.strptime(start_date_str, "%Y-%m-%d"))
            end_date = timezone.make_aware(datetime.strptime(end_date_str, "%Y-%m-%d"))
            end_date = end_date + timedelta(days=1)  # 包含结束日期当天
        except ValueError:
            return error("日期格式不正确，请使用 YYYY-MM-DD 格式")

        if start_date > end_date - timedelta(days=1):
            return error("开始日期不能晚于结束日期")

        # 生成日期范围内的连续日期列表
        current_date = start_date
        date_list = []
        while current_date < end_date:
            date_list.append(current_date.strftime("%Y-%m-%d"))
            current_date += timedelta(days=1)

        # PV: 按天统计日志条数
        pv_data = (
            Log.objects.filter(create_time__gte=start_date, create_time__lt=end_date)
            .annotate(date=TruncDate("create_time"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )

        # UV: 按天统计去重IP数
        ip_data = (
            Log.objects.filter(create_time__gte=start_date, create_time__lt=end_date)
            .annotate(date=TruncDate("create_time"))
            .values("date")
            .annotate(count=Count("ip", distinct=True))
            .order_by("date")
        )

        # 将查询结果转为 {日期: 数值} 映射，补齐无数据的日期为0
        # 过滤 date 为 None 的记录，防止 strftime 空指针异常
        pv_dict = {item["date"].strftime("%Y-%m-%d"): item["count"] for item in pv_data if item.get("date") is not None}
        ip_dict = {item["date"].strftime("%Y-%m-%d"): item["count"] for item in ip_data if item.get("date") is not None}

        pv_list = [pv_dict.get(date, 0) for date in date_list]
        ip_list = [ip_dict.get(date, 0) for date in date_list]

        return success(
            {
                "dates": date_list,
                "pvList": pv_list,
                "uvList": ip_list,
            }
        )

    @extend_schema(
        summary="访问统计概览",
        responses=resp(
            "VisitOverviewResult",
            inline_serializer(
                name="VisitOverviewData",
                fields={
                    "todayUvCount": serializers.IntegerField(),
                    "totalUvCount": serializers.IntegerField(),
                    "uvGrowthRate": serializers.FloatField(),
                    "todayPvCount": serializers.IntegerField(),
                    "totalPvCount": serializers.IntegerField(),
                    "pvGrowthRate": serializers.FloatField(),
                },
            ),
        ),
    )
    @action(methods=["get"], detail=False, url_path="analytics/overview", permission_classes=[AllowAny])
    def views(self, request, *args, **kwargs):
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        yesterday_start = today_start - timedelta(days=1)
        yesterday_end = today_start

        # 今日 PV/UV
        today_pv_count = Log.objects.filter(create_time__gte=today_start, create_time__lt=today_end).count()
        today_uv_count = (
            Log.objects.filter(create_time__gte=today_start, create_time__lt=today_end)
            .values("ip")
            .distinct()
            .count()
        )

        # 昨日 PV/UV（用于计算增长率）
        yesterday_pv_count = Log.objects.filter(
            create_time__gte=yesterday_start, create_time__lt=yesterday_end
        ).count()
        yesterday_uv_count = (
            Log.objects.filter(create_time__gte=yesterday_start, create_time__lt=yesterday_end)
            .values("ip")
            .distinct()
            .count()
        )

        # 累计 PV/UV
        total_pv_count = Log.objects.count()
        total_uv_count = Log.objects.values("ip").distinct().count()

        # 增长率 = (今日 - 昨日) / 昨日 * 100
        pv_growth_rate = 0
        if yesterday_pv_count > 0:
            pv_growth_rate = round((today_pv_count - yesterday_pv_count) / yesterday_pv_count * 100, 2)

        uv_growth_rate = 0
        if yesterday_uv_count > 0:
            uv_growth_rate = round((today_uv_count - yesterday_uv_count) / yesterday_uv_count * 100, 2)

        return success(
            {
                "todayUvCount": today_uv_count,
                "totalUvCount": total_uv_count,
                "uvGrowthRate": uv_growth_rate,
                "todayPvCount": today_pv_count,
                "totalPvCount": total_pv_count,
                "pvGrowthRate": pv_growth_rate,
            }
        )


