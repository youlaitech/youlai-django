"""动态表单路由：form_key 为小写字母/数字/下划线，id 段为纯数字，二者不冲突。"""
from django.urls import re_path

from apps.system.form import views

urlpatterns = [
    # 固定段优先，避免被 form_key 模式吞掉
    re_path(r"^options$", views.FormOptionsApi.as_view()),
    re_path(r"^ai-generate$", views.FormAiGenerateApi.as_view()),
    re_path(r"^public/(?P<form_key>[A-Za-z0-9_]+)/render$", views.FormPublicRenderApi.as_view()),
    re_path(r"^public/(?P<form_key>[A-Za-z0-9_]+)/data$", views.FormPublicDataApi.as_view()),
    # 表单定义
    re_path(r"^(?P<form_id>\d+)/publish$", views.FormStatusApi.as_view(), {"action": "publish"}),
    re_path(r"^(?P<form_id>\d+)/disable$", views.FormStatusApi.as_view(), {"action": "disable"}),
    re_path(r"^(?P<form_id>\d+)/menu$", views.FormMenuApi.as_view()),
    re_path(r"^(?P<form_id>\d+)/form$", views.FormDefinitionApi.as_view()),
    re_path(r"^(?P<form_id>\d+)$", views.FormDefinitionApi.as_view(), {"ids": None}),
    re_path(r"^(?P<ids>[\d,]+)$", views.FormDefinitionApi.as_view()),
    # 表单渲染与数据
    re_path(r"^(?P<form_key>[A-Za-z0-9_]+)/render$", views.FormRenderApi.as_view()),
    re_path(r"^(?P<form_key>[A-Za-z0-9_]+)/data/(?P<ids>[\d,]+)$", views.FormDataItemApi.as_view()),
    re_path(r"^(?P<form_key>[A-Za-z0-9_]+)/data$", views.FormDataApi.as_view()),
    # 分页列表与新增
    re_path(r"^$", views.FormDefinitionListApi.as_view()),
]
