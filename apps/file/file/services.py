"""平台-文件服务。

"""

from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import time
import uuid
from dataclasses import dataclass

import boto3
import botocore
from django.conf import settings

from core.exceptions.business import BusinessException


@dataclass(frozen=True)
class UploadedFileInfo:
    """上传结果：原文件名与访问 URL"""

    name: str
    url: str


def _endpoint_host() -> str:
    """对象存储地址，去掉协议头"""
    endpoint = settings.S3_ENDPOINT
    if endpoint.startswith('http://'):
        return endpoint[len('http://'):]
    if endpoint.startswith('https://'):
        return endpoint[len('https://'):]
    return endpoint


def _build_client():
    """创建 S3 客户端，IP 端点必须走 path-style（桶名落在路径而非子域名）"""
    return boto3.client(
        's3',
        endpoint_url=f"{'https' if settings.S3_SSL else 'http'}://{_endpoint_host()}",
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        # 区域值仅占位，非 AWS 服务任意值均可
        region_name='us-east-1',
        config=botocore.config.Config(signature_version='s3v4', s3={'addressing_style': 'path'}),
    )


class S3FileService:
    """RustFS（S3 协议兼容）文件存储"""

    def upload_file(self, upload_file) -> UploadedFileInfo:
        """上传文件，返回访问 URL"""
        # 扩展名 + 大小白名单校验
        file_name = upload_file.name or "file"
        ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
        allowed = [e.strip().lower() for e in settings.FILE_ALLOWED_EXTENSIONS.split(",") if e.strip()]
        if allowed and ext not in allowed:
            raise BusinessException(f"不支持的文件类型: .{ext}", code="A0400", status=400)
        max_bytes = settings.FILE_MAX_SIZE_MB * 1024 * 1024
        if upload_file.size > max_bytes:
            raise BusinessException(f"文件大小超过限制: {upload_file.size // 1024 // 1024}MB", code="A0400", status=400)

        s3_client = _build_client()
        bucket_name = settings.S3_BUCKET_NAME
        try:
            s3_client.head_bucket(Bucket=bucket_name)
        except botocore.exceptions.ClientError as exc:
            # 桶不存在（404）才创建，其余错误（如权限不足）原样抛出
            if exc.response.get('ResponseMetadata', {}).get('HTTPStatusCode') != 404:
                raise
            s3_client.create_bucket(Bucket=bucket_name)
            self._set_bucket_public_policy(s3_client, bucket_name)

        file_content = upload_file.read()

        md5_code = hashlib.md5(file_content).hexdigest()

        timestamp = str(int(time.time()))
        random_str = str(uuid.uuid4()).replace('-', '')[:12]
        signature_data = f"{md5_code}_{timestamp}_{random_str}"
        signature = hmac.new(
            settings.SECRET_KEY.encode('utf-8'),
            signature_data.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()[:16]
        security_part = f"{timestamp}{random_str}{signature}"

        first_char = md5_code[0]
        second_char = md5_code[1]
        storage_path = f"{first_char}/{second_char}/{md5_code}__{security_part}__{file_name}"

        content_type, _ = mimetypes.guess_type(file_name)
        if content_type is None:
            content_type = 'application/octet-stream'

        s3_client.put_object(
            Bucket=bucket_name,
            Key=storage_path,
            # 固定长度的字节数组上传，避免流式分块签名在部分 S3 兼容服务上报校验和不匹配
            Body=file_content,
            ContentType=content_type,
        )

        protocol = 'https' if settings.S3_SSL else 'http'
        url = f"{protocol}://{_endpoint_host()}/{bucket_name}/{storage_path}"

        return UploadedFileInfo(name=file_name, url=url)

    def delete_file(self, file_path: str) -> None:
        """删除对象存储中的文件"""
        _build_client().delete_object(Bucket=settings.S3_BUCKET_NAME, Key=file_path)

    def _set_bucket_public_policy(self, s3_client, bucket_name: str) -> None:
        """设置桶的匿名只读策略，禁止匿名写入"""
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": "*"},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket_name}/*"],
                }
            ],
        }

        s3_client.put_bucket_policy(Bucket=bucket_name, Policy=json.dumps(policy))
