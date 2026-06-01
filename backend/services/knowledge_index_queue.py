"""知识库索引任务队列。"""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass
from typing import Any, Protocol

from core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class KnowledgeIndexJob:
    """知识库索引任务载体。"""

    document_id: str
    message_id: str | None = None


class KnowledgeIndexQueue(Protocol):
    """索引任务队列协议。"""

    async def enqueue(self, document_id: str) -> None:
        """投递待索引文档。"""

    async def read(self, *, count: int, block_ms: int) -> list[KnowledgeIndexJob]:
        """读取一批待处理任务。"""

    async def ack(self, job: KnowledgeIndexJob) -> None:
        """确认任务已处理。"""

    async def close(self) -> None:
        """释放队列资源。"""


class DatabaseKnowledgeIndexQueue:
    """数据库状态轮询队列，作为本地开发和 Redis 不可用时的回退。"""

    async def enqueue(self, document_id: str) -> None:
        # 数据库队列以 kb_documents.pending 状态作为任务源，入队无需额外写入。
        _ = document_id

    async def read(self, *, count: int, block_ms: int) -> list[KnowledgeIndexJob]:
        _ = (count, block_ms)
        return []

    async def ack(self, job: KnowledgeIndexJob) -> None:
        _ = job

    async def close(self) -> None:
        return None


class RedisKnowledgeIndexQueue:
    """Redis Streams 索引队列，支持多实例 worker consumer group。"""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._redis: Any | None = None
        self._group_ready = False
        self._consumer_name = (
            self.settings.KNOWLEDGE_INDEX_QUEUE_REDIS_CONSUMER
            or f"{socket.gethostname()}-{id(self)}"
        )

    def _get_redis(self) -> Any:
        if self._redis is not None:
            return self._redis
        try:
            from redis import ResponseError
            from redis import asyncio as redis_asyncio
        except ImportError as exc:  # pragma: no cover - 依赖缺失只在 redis 模式触发
            raise RuntimeError(
                "KNOWLEDGE_INDEX_QUEUE_BACKEND=redis 需要安装 redis Python 客户端"
            ) from exc

        self._response_error = ResponseError
        self._redis = redis_asyncio.from_url(self.settings.REDIS_URL, decode_responses=True)
        return self._redis

    async def _ensure_group(self) -> None:
        if self._group_ready:
            return
        redis = self._get_redis()
        try:
            await redis.xgroup_create(
                name=self.settings.KNOWLEDGE_INDEX_QUEUE_REDIS_STREAM,
                groupname=self.settings.KNOWLEDGE_INDEX_QUEUE_REDIS_GROUP,
                id="0",
                mkstream=True,
            )
        except self._response_error as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        self._group_ready = True

    async def enqueue(self, document_id: str) -> None:
        await self._ensure_group()
        await self._get_redis().xadd(
            self.settings.KNOWLEDGE_INDEX_QUEUE_REDIS_STREAM,
            {"document_id": document_id},
            maxlen=self.settings.KNOWLEDGE_INDEX_QUEUE_MAXLEN,
            approximate=True,
        )

    async def read(self, *, count: int, block_ms: int) -> list[KnowledgeIndexJob]:
        await self._ensure_group()
        redis = self._get_redis()
        response = await redis.xreadgroup(
            groupname=self.settings.KNOWLEDGE_INDEX_QUEUE_REDIS_GROUP,
            consumername=self._consumer_name,
            streams={self.settings.KNOWLEDGE_INDEX_QUEUE_REDIS_STREAM: ">"},
            count=count,
            block=block_ms,
        )
        return _parse_stream_jobs(response)

    async def ack(self, job: KnowledgeIndexJob) -> None:
        if not job.message_id:
            return
        await self._get_redis().xack(
            self.settings.KNOWLEDGE_INDEX_QUEUE_REDIS_STREAM,
            self.settings.KNOWLEDGE_INDEX_QUEUE_REDIS_GROUP,
            job.message_id,
        )

    async def close(self) -> None:
        if self._redis is None:
            return
        close = getattr(self._redis, "aclose", None) or getattr(self._redis, "close", None)
        if close is not None:
            result = close()
            if hasattr(result, "__await__"):
                await result
        self._redis = None
        self._group_ready = False


def _parse_stream_jobs(response: Any) -> list[KnowledgeIndexJob]:
    """兼容 redis-py stream 响应结构并提取 document_id。"""
    jobs: list[KnowledgeIndexJob] = []
    for stream in response or []:
        if not isinstance(stream, (list, tuple)) or len(stream) != 2:
            continue
        _, messages = stream
        for message in messages or []:
            if not isinstance(message, (list, tuple)) or len(message) != 2:
                continue
            message_id, payload = message
            document_id = str((payload or {}).get("document_id") or "")
            if document_id:
                jobs.append(KnowledgeIndexJob(document_id=document_id, message_id=str(message_id)))
    return jobs


_queue_instance: KnowledgeIndexQueue | None = None


def get_knowledge_index_queue() -> KnowledgeIndexQueue:
    """获取索引队列实例。"""
    global _queue_instance
    settings = get_settings()
    if _queue_instance is None:
        if settings.KNOWLEDGE_INDEX_QUEUE_BACKEND == "redis":
            _queue_instance = RedisKnowledgeIndexQueue()
        else:
            _queue_instance = DatabaseKnowledgeIndexQueue()
    return _queue_instance


async def dispose_knowledge_index_queue() -> None:
    """释放索引队列连接。"""
    global _queue_instance
    if _queue_instance is None:
        return
    await _queue_instance.close()
    _queue_instance = None
