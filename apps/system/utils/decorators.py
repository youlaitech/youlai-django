"""系统管理-utils模块。

"""

import time
from functools import wraps

import jwt
from django.utils.timezone import now
from rest_framework_simplejwt.backends import TokenBackend
from user_agents import parse

from apps.system.logs.models import ActionType, Log, LogModule
from apps.system.utils.utils import get_ip_location


def operation_log(content, module, action_type=ActionType.OTHER):
    """操作日志装饰器，用于记录接口操作行为。

    Args:
        content: 操作描述，如"新增用户"
        module: 所属模块，如"用户模块"
        action_type: 行为类型，使用 ActionType 枚举，默认 OTHER
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(self, request, *args, **kwargs):
            start_time = time.time()

            # 从 Authorization 头解析用户ID
            user_id = None
            if request.headers.get("Authorization"):
                auth_header = request.headers.get("Authorization")
                token = auth_header.split()[1]
                token_backend = TokenBackend(algorithm="HS256")
                try:
                    token_data = token_backend.decode(token, verify=False)
                    user_id = token_data.get("user_id")
                except jwt.DecodeError:
                    pass

            try:
                response = view_func(self, request, *args, **kwargs)
            except Exception as e:
                execution_time = int((time.time() - start_time) * 1000)
                ip = request.META.get("REMOTE_ADDR")
                location = get_ip_location(ip)

                if location != "本地":
                    location_parts = location.split()
                    province = location_parts[0] if len(location_parts) > 0 else "未知"
                    city = location_parts[1] if len(location_parts) > 1 else "未知"
                else:
                    province = "本地"
                    city = "本地"

                user_agent = request.META.get('HTTP_USER_AGENT', '')
                parsed_agent = parse(user_agent)

                browser = parsed_agent.browser.family if parsed_agent.browser.family else "未知"
                os = parsed_agent.os.family if parsed_agent.os.family else "未知"

                Log.objects.create(
                    action_type=action_type,
                    module=module,
                    title=content,
                    content=content,
                    request_method=request.method,
                    request_uri=request.get_full_path(),
                    ip=ip,
                    province=province,
                    city=city,
                    execution_time=execution_time,
                    create_time=now(),
                    browser=browser,
                    os=os,
                    status=0,
                    error_msg=str(e)[:255] if str(e) else None,
                )
                raise

            execution_time = int((time.time() - start_time) * 1000)
            ip = request.META.get("REMOTE_ADDR")
            location = get_ip_location(ip)

            if location != "本地":
                location_parts = location.split()
                province = location_parts[0] if len(location_parts) > 0 else "未知"
                city = location_parts[1] if len(location_parts) > 1 else "未知"
            else:
                province = "本地"
                city = "本地"

            user_agent = request.META.get('HTTP_USER_AGENT', '')
            parsed_agent = parse(user_agent)

            browser = parsed_agent.browser.family if parsed_agent.browser.family else "未知"
            os = parsed_agent.os.family if parsed_agent.os.family else "未知"

            Log.objects.create(
                action_type=action_type,
                module=module,
                title=content,
                content=content,
                request_method=request.method,
                request_uri=request.get_full_path(),
                ip=ip,
                province=province,
                city=city,
                execution_time=execution_time,
                create_time=now(),
                browser=browser,
                os=os,
                status=1,
            )
            return response

        return wrapper

    return decorator

log = operation_log
log_api = operation_log
