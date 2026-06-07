"""知识库原始文件对象存储抽象。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from core.config import get_settings


class KnowledgeObjectStorage(Protocol):
    """知识库原始文件存储协议。"""

    async def put_document(
        self,
        *,
        workspace_id: str,
        document_id: str,
        file_name: str,
        content: bytes,
    ) -> str:
        """写入原始文件并返回 storage_uri。"""

    async def get_bytes(self, storage_uri: str) -> bytes:
        """读取 storage_uri 对应的原始文件内容。"""

    async def delete(self, storage_uri: str) -> None:
        """删除 storage_uri 对应对象，删除不存在对象应保持幂等。"""


def _safe_suffix(file_name: str) -> str:
    suffix = Path(file_name).suffix
    return suffix or ".txt"


class LocalKnowledgeObjectStorage:
    """本地文件存储，保持开发和测试场景的最小依赖。"""

    def __init__(self, storage_dir: str | None = None) -> None:
        self.storage_root = Path(storage_dir or get_settings().KNOWLEDGE_STORAGE_DIR)

    async def put_document(
        self,
        *,
        workspace_id: str,
        document_id: str,
        file_name: str,
        content: bytes,
    ) -> str:
        workspace_dir = self.storage_root / workspace_id
        workspace_dir.mkdir(parents=True, exist_ok=True)
        target = workspace_dir / f"{document_id}{_safe_suffix(file_name)}"
        target.write_bytes(content)
        return str(target)

    async def get_bytes(self, storage_uri: str) -> bytes:
        return Path(storage_uri).read_bytes()

    async def delete(self, storage_uri: str) -> None:
        Path(storage_uri).unlink(missing_ok=True)


class S3KnowledgeObjectStorage:
    """S3/MinIO 兼容对象存储。"""

    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.KNOWLEDGE_S3_BUCKET:
            raise RuntimeError("KNOWLEDGE_OBJECT_STORAGE_BACKEND=s3 需要配置 KNOWLEDGE_S3_BUCKET")
        self._client = None

    def _object_key(self, *, workspace_id: str, document_id: str, file_name: str) -> str:
        prefix = self.settings.KNOWLEDGE_S3_PREFIX
        key = f"{workspace_id}/{document_id}{_safe_suffix(file_name)}"
        return f"{prefix}/{key}" if prefix else key

    def _get_client(self):
        if self._client is not None:
            return self._client

        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - 依赖由生产环境按需安装
            raise RuntimeError("S3 知识库对象存储需要安装 boto3") from exc

        config = Config(
            s3={
                "addressing_style": "path"
                if self.settings.KNOWLEDGE_S3_FORCE_PATH_STYLE
                else "auto"
            }
        )
        kwargs = {
            "service_name": "s3",
            "region_name": self.settings.KNOWLEDGE_S3_REGION,
            "config": config,
        }
        if self.settings.KNOWLEDGE_S3_ENDPOINT_URL:
            kwargs["endpoint_url"] = self.settings.KNOWLEDGE_S3_ENDPOINT_URL
        if self.settings.KNOWLEDGE_S3_ACCESS_KEY_ID:
            kwargs["aws_access_key_id"] = self.settings.KNOWLEDGE_S3_ACCESS_KEY_ID
        if self.settings.KNOWLEDGE_S3_SECRET_ACCESS_KEY:
            kwargs["aws_secret_access_key"] = self.settings.KNOWLEDGE_S3_SECRET_ACCESS_KEY
        self._client = boto3.client(**kwargs)
        return self._client

    async def put_document(
        self,
        *,
        workspace_id: str,
        document_id: str,
        file_name: str,
        content: bytes,
    ) -> str:
        key = self._object_key(
            workspace_id=workspace_id,
            document_id=document_id,
            file_name=file_name,
        )
        await asyncio.to_thread(
            self._get_client().put_object,
            Bucket=self.settings.KNOWLEDGE_S3_BUCKET,
            Key=key,
            Body=content,
        )
        return f"s3://{self.settings.KNOWLEDGE_S3_BUCKET}/{key}"

    async def get_bytes(self, storage_uri: str) -> bytes:
        bucket, key = _parse_s3_uri(storage_uri)
        response = await asyncio.to_thread(
            self._get_client().get_object,
            Bucket=bucket,
            Key=key,
        )
        body = response["Body"]
        try:
            return await asyncio.to_thread(body.read)
        finally:
            close = getattr(body, "close", None)
            if close is not None:
                close()

    async def delete(self, storage_uri: str) -> None:
        bucket, key = _parse_s3_uri(storage_uri)
        await asyncio.to_thread(
            self._get_client().delete_object,
            Bucket=bucket,
            Key=key,
        )


def _parse_s3_uri(storage_uri: str) -> tuple[str, str]:
    parsed = urlparse(storage_uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.strip("/"):
        raise ValueError(f"非法 S3 storage_uri: {storage_uri}")
    return parsed.netloc, parsed.path.lstrip("/")


def get_knowledge_object_storage() -> KnowledgeObjectStorage:
    """按配置创建知识库对象存储 provider。"""
    settings = get_settings()
    if settings.KNOWLEDGE_OBJECT_STORAGE_BACKEND == "s3":
        return S3KnowledgeObjectStorage()
    return LocalKnowledgeObjectStorage(settings.KNOWLEDGE_STORAGE_DIR)


def get_knowledge_object_storage_for_uri(storage_uri: str) -> KnowledgeObjectStorage:
    """按已有 storage_uri 选择读取/删除 provider，支持平滑迁移。"""
    if storage_uri.startswith("s3://"):
        return S3KnowledgeObjectStorage()
    return LocalKnowledgeObjectStorage(get_settings().KNOWLEDGE_STORAGE_DIR)
