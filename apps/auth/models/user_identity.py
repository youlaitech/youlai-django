"""本地用户与外部账号的关联模型。"""

from django.db import models

# 微信小程序的认证源标识，与配置保持一致
WECHAT_MINI_PROVIDER = "wechat-mini-main"


class UserIdentity(models.Model):
    """本地用户与外部账号的关联表"""

    id = models.BigAutoField(primary_key=True)
    user_id = models.BigIntegerField(verbose_name="本地用户ID")
    provider = models.CharField(max_length=64, verbose_name="具体认证源标识")
    provider_account_id = models.CharField(max_length=255, verbose_name="来源方账号ID")
    display_name = models.CharField(max_length=128, null=True, blank=True, verbose_name="外部账号展示名")
    avatar_url = models.CharField(max_length=512, null=True, blank=True, verbose_name="外部账号头像")
    last_login_time = models.DateTimeField(null=True, blank=True, verbose_name="最近一次登录时间")
    create_time = models.DateTimeField(auto_now_add=True, verbose_name="关联创建时间")
    update_time = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "sys_user_identity"
        verbose_name = "本地用户与外部账号的关联"
        unique_together = [("provider", "provider_account_id"), ("user_id", "provider")]

    def __str__(self):
        return f"{self.provider}:{self.provider_account_id}"
