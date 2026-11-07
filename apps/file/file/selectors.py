"""平台-文件查询。

"""

from __future__ import annotations

from django.conf import settings


def extract_file_path(path_or_url: str) -> str | None:
    """URL 或对象路径解析为对象 key；URL 兼容直链与自定义域名，自动剥掉签名 query"""
    if not path_or_url:
        return None

    if path_or_url.startswith(('http://', 'https://')):
        # 预签名 URL 的签名参数不属于对象 key
        path = path_or_url.split('?', 1)[0]
        marker = f"/{settings.S3_BUCKET_NAME}/"
        index = path.find(marker)
        if index < 0:
            return None
        return path[index + len(marker):] or None

    return path_or_url
