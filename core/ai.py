"""AI 对话：OpenAI 兼容的 chat/completions 调用与提示词加载。"""
import json
import logging
import os

import requests
from django.conf import settings

from core.exceptions.business import BusinessException

logger = logging.getLogger(__name__)

# 提示词目录，各模块的 md 提示词集中放在动态表单模块下
PROMPTS_DIR = os.path.join(str(settings.BASE_DIR), "apps", "system", "form", "prompts")


def load_prompt(name):
    """读取提示词文件，文件不存在时返回参数错误。"""
    path = os.path.join(PROMPTS_DIR, name)
    if not os.path.exists(path):
        raise BusinessException(f"提示词不存在：{name}", code="A0400")
    with open(path, encoding="utf-8") as handle:
        return handle.read().strip()


def chat(system_prompt, user_prompt):
    """调用 AI 对话接口，返回去掉代码围栏的文本内容。"""
    if not getattr(settings, "AI_ENABLED", False):
        raise BusinessException("AI 功能未开启，请配置 AI_ENABLED 与 AI_API_KEY")

    url = f"{settings.AI_BASE_URL.rstrip('/')}/chat/completions"
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {settings.AI_API_KEY}"},
        json={
            "model": settings.AI_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        },
        timeout=60,
    )
    if response.status_code != 200:
        logger.error("AI 调用失败 %s: %s", response.status_code, response.text)
        raise BusinessException(f"AI 调用失败：{response.status_code}")

    content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    return _strip_code_fence(content)


def chat_json(system_prompt, user_prompt):
    """调用 AI 对话接口，把返回内容解析为字典。"""
    content = chat(system_prompt, user_prompt)
    try:
        result = json.loads(content)
    except ValueError:
        raise BusinessException("AI 返回内容不是合法 JSON")

    if not isinstance(result, dict):
        raise BusinessException("AI 返回内容不是合法 JSON 对象")
    return result


def _strip_code_fence(content):
    """去掉模型输出里可能包裹的 json 代码围栏。"""
    text = (content or "").strip()
    if not text.startswith("```"):
        return text
    start = text.find("\n")
    end = text.rfind("```")
    return text[start + 1:end].strip() if start != -1 and end > start else text
