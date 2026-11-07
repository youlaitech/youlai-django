"""平台-认证路由。

"""

from django.urls import path

from .views import AuthViewSet
from .views_qrcode import QrCodeViewSet
from .views_wxma import WxMaAuthViewSet

urlpatterns = [
    path("login", AuthViewSet.as_view({"post": "login"}), name="token_obtain_pair"),
    path("sms/login", AuthViewSet.as_view({"post": "login_by_sms"}), name="login_by_sms"),
    path("sms/code", AuthViewSet.as_view({"post": "send_sms_login_code"}), name="send_sms_login_code"),
    path("captcha", AuthViewSet.as_view({"get": "captcha"}), name="captcha"),
    path("refresh-token", AuthViewSet.as_view({"post": "refresh_token"}), name="token_refresh"),
    path("logout", AuthViewSet.as_view({"delete": "logout"}), name="logout"),
    # 扫码登录
    path("qr-code/generate", QrCodeViewSet.as_view({"post": "generate"}), name="qr_code_generate"),
    path("qr-code/status", QrCodeViewSet.as_view({"get": "status"}), name="qr_code_status"),
    path("qr-code/scan", QrCodeViewSet.as_view({"post": "scan"}), name="qr_code_scan"),
    path("qr-code/confirm", QrCodeViewSet.as_view({"post": "confirm"}), name="qr_code_confirm"),
    path("qr-code/cancel", QrCodeViewSet.as_view({"post": "cancel"}), name="qr_code_cancel"),
    path("qr-code/login", QrCodeViewSet.as_view({"post": "login"}), name="qr_code_login"),
    # 微信小程序认证
    path("auth/wxma/silent-login", WxMaAuthViewSet.as_view({"post": "silent_login"}), name="wxma_silent_login"),
    path("auth/wxma/phone-login", WxMaAuthViewSet.as_view({"post": "phone_login"}), name="wxma_phone_login"),
    path("auth/wxma/bind-mobile", WxMaAuthViewSet.as_view({"post": "bind_mobile"}), name="wxma_bind_mobile"),
]
