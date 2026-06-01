"""知识库后台索引 worker。"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from core.config import get_settings
from db.postgres_store import get_postgres_store
from services.knowledge_index_queue import (
    KnowledgeIndexJob,
    dispose_knowledge_index_queue,
    get_knowledge_index_queue,
)
from services.knowledge_service import KnowledgeService

logger = logging.getLogger(__name__)

_worker_task: asyncio.Task | None = None


async def _claim_document_ids(limit: int) -> list[str]:
    async with get_postgres_store().initialized_session() as session:
        return await KnowledgeService(session).claim_pending_documents_for_indexing(limit=limit)


async def _claim_queued_document_ids(jobs: list[KnowledgeIndexJob]) -> list[str]:
    async with get_postgres_store().initialized_session() as session:
        return await KnowledgeService(session).claim_documents_for_indexing(
            document_ids=[job.document_id for job in jobs],
        )


async def _ack_job(job: KnowledgeIndexJob) -> None:
    try:
        await get_knowledge_index_queue().ack(job)
    except Exception:
        logger.exception("知识库索引队列 ACK 失败 document_id=%s", job.document_id)


async def index_pending_documents(*, limit: int | None = None) -> int:
    """处理一批待索引文档，返回实际处理数量。"""
    settings = get_settings()
    batch_size = limit or settings.KNOWLEDGE_INDEX_WORKER_BATCH_SIZE
    jobs: list[KnowledgeIndexJob] = []
    if settings.KNOWLEDGE_INDEX_QUEUE_BACKEND == "redis":
        try:
            jobs = await get_knowledge_index_queue().read(
                count=batch_size,
                block_ms=settings.KNOWLEDGE_INDEX_QUEUE_BLOCK_MS,
            )
        except Exception:
            logger.exception("读取知识库 Redis 索引队列失败，已回退数据库扫描")

    document_ids = await _claim_queued_document_ids(jobs) if jobs else []
    claimed_ids = set(document_ids)
    for job in jobs:
        if job.document_id not in claimed_ids:
            await _ack_job(job)

    if not document_ids:
        document_ids = await _claim_document_ids(batch_size)
    if not document_ids:
        return 0

    processed = 0
    for document_id in document_ids:
        async with get_postgres_store().initialized_session() as session:
            try:
                await KnowledgeService(session).index_document(document_id=document_id)
            except Exception:
                logger.exception("知识库后台索引任务失败 document_id=%s", document_id)
            finally:
                processed += 1
                for job in jobs:
                    if job.document_id == document_id:
                        await _ack_job(job)
    return processed


async def _worker_loop() -> None:
    settings = get_settings()
    interval_seconds = settings.KNOWLEDGE_INDEX_WORKER_INTERVAL_SECONDS
    while True:
        try:
            processed = await index_pending_documents()
            if processed == 0:
                await asyncio.sleep(interval_seconds)
            else:
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("知识库后台索引循环异常")
            await asyncio.sleep(interval_seconds)


async def run_knowledge_index_worker_forever() -> None:
    """作为独立进程运行知识库索引 worker。"""
    settings = get_settings()
    if not settings.KNOWLEDGE_INDEX_WORKER_ENABLED:
        logger.info("知识库索引 worker 已通过配置关闭")
        return
    try:
        await _worker_loop()
    finally:
        await dispose_knowledge_index_queue()


def start_knowledge_index_worker() -> None:
    """启动本进程轻量索引 worker，生产多实例队列后可替换此调度器。"""
    global _worker_task
    settings = get_settings()
    if not settings.KNOWLEDGE_INDEX_WORKER_ENABLED:
        return
    if _worker_task is not None and not _worker_task.done():
        return
    _worker_task = asyncio.create_task(_worker_loop())


async def stop_knowledge_index_worker() -> None:
    """停止后台 worker，供 FastAPI shutdown 生命周期调用。"""
    global _worker_task
    if _worker_task is None:
        return
    _worker_task.cancel()
    with suppress(asyncio.CancelledError):
        await _worker_task
    _worker_task = None
    await dispose_knowledge_index_queue()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_knowledge_index_worker_forever())
