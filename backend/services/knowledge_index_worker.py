"""知识库后台索引 worker。"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from sqlalchemy import and_, select

from core.config import get_settings
from db.postgres_store import get_postgres_store
from models.knowledge import KnowledgeDocumentStatus
from orm.knowledge_orm import KnowledgeDocumentORM
from services.knowledge_service import KnowledgeService

logger = logging.getLogger(__name__)

_worker_task: asyncio.Task | None = None


async def _pending_document_ids(limit: int) -> list[str]:
    async with get_postgres_store().initialized_session() as session:
        result = await session.execute(
            select(KnowledgeDocumentORM.id)
            .where(
                and_(
                    KnowledgeDocumentORM.parse_status == KnowledgeDocumentStatus.PENDING.value,
                    KnowledgeDocumentORM.index_status == KnowledgeDocumentStatus.PENDING.value,
                )
            )
            .order_by(KnowledgeDocumentORM.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())


async def index_pending_documents(*, limit: int | None = None) -> int:
    """处理一批待索引文档，返回实际处理数量。"""
    settings = get_settings()
    batch_size = limit or settings.KNOWLEDGE_INDEX_WORKER_BATCH_SIZE
    document_ids = await _pending_document_ids(batch_size)
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
