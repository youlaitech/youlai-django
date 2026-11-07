"""动态表单模型：表单定义、表单数据、版本快照。"""
from django.db import models


class FormDefinition(models.Model):
    """表单定义表（form_definition）"""

    form_key = models.CharField(max_length=64, unique=True, verbose_name="表单唯一标识")
    form_name = models.CharField(max_length=100, verbose_name="表单名称")
    description = models.CharField(max_length=255, null=True, blank=True, verbose_name="表单描述")
    form_json = models.JSONField(default=list, verbose_name="表单规则（form-create rule 数组）")
    options_json = models.JSONField(null=True, blank=True, verbose_name="表单全局配置")
    status = models.SmallIntegerField(default=0, verbose_name="状态", help_text="0草稿 1已发布 -1已停用")
    is_public = models.SmallIntegerField(default=0, verbose_name="是否允许匿名公开访问", help_text="0否 1是")
    category = models.CharField(max_length=16, default="normal", verbose_name="表单类型",
                                help_text="normal通用表单 workflow审批表单")
    menu_id = models.BigIntegerField(null=True, blank=True, verbose_name="生成的访问菜单ID",
                                     help_text="NULL未生成，幂等防重复")
    version = models.IntegerField(default=1, verbose_name="版本号")
    create_time = models.DateTimeField(null=True, blank=True, verbose_name="创建时间")
    create_by = models.BigIntegerField(null=True, blank=True, verbose_name="创建人ID")
    update_time = models.DateTimeField(null=True, blank=True, verbose_name="更新时间")
    update_by = models.BigIntegerField(null=True, blank=True, verbose_name="修改人ID")
    is_deleted = models.SmallIntegerField(default=0, verbose_name="是否删除", help_text="0未删除 1已删除")

    class Meta:
        db_table = "form_definition"
        verbose_name = "表单定义表"
        verbose_name_plural = "表单定义表"

    def __str__(self):
        return self.form_name


class FormData(models.Model):
    """表单数据表（form_data）"""

    form_id = models.BigIntegerField(verbose_name="表单定义ID")
    form_version = models.IntegerField(verbose_name="表单版本（提交时快照）")
    data_json = models.JSONField(default=dict, verbose_name="表单数据（field -> value 映射）")
    create_time = models.DateTimeField(null=True, blank=True, verbose_name="提交时间")
    create_by = models.BigIntegerField(null=True, blank=True, verbose_name="提交人ID",
                                       help_text="匿名提交为空")
    update_time = models.DateTimeField(null=True, blank=True, verbose_name="更新时间")
    update_by = models.BigIntegerField(null=True, blank=True, verbose_name="修改人ID")
    is_deleted = models.SmallIntegerField(default=0, verbose_name="是否删除")

    class Meta:
        db_table = "form_data"
        verbose_name = "表单数据表"
        verbose_name_plural = "表单数据表"


class FormSnapshot(models.Model):
    """表单版本快照表（form_snapshot）：发布时固化规则，快照只增不改"""

    form_id = models.BigIntegerField(verbose_name="表单定义ID")
    version = models.IntegerField(verbose_name="版本号（发布时递增后的值）")
    form_json = models.JSONField(default=list, verbose_name="表单规则快照")
    options_json = models.JSONField(null=True, blank=True, verbose_name="表单全局配置快照")
    create_time = models.DateTimeField(null=True, blank=True, verbose_name="创建时间")
    update_time = models.DateTimeField(null=True, blank=True, verbose_name="更新时间")
    is_deleted = models.SmallIntegerField(default=0, verbose_name="是否删除")

    class Meta:
        db_table = "form_snapshot"
        verbose_name = "表单版本快照表"
        verbose_name_plural = "表单版本快照表"
