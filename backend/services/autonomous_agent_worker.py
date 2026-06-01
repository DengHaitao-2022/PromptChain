"""Autonomous Agent 后台执行队列。"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from core.config import get_settings
from core.time import utc_now_naive
from db.postgres_store import get_postgres_store
from models.autonomous_agent import AgentRunStatus
from services.artifact_store import get_artifact_store
from services.autonomous_agent_runtime import AutonomousAgentRuntime
from services.autonomous_agent_store import AutonomousAgentStore

logger = logging.getLogger(__name__)


class AutonomousAgentWorkerQueue:
    """进程内最小执行队列，后续可替换为 Redis/Celery/RQ。"""

    def __init__(self, *, max_concurrency: int = 2):
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._queued_run_ids: set[str] = set()
        self._active_run_ids: set[str] = set()
        self._workers: list[asyncio.Task[None]] = []
        self._lock = asyncio.Lock()
        self._start_lock = asyncio.Lock()
        self._max_concurrency = max(1, max_concurrency)

    async def start(self) -> None:
        """启动后台 worker。"""
        async with self._start_lock:
            if self._workers:
                return
            for index in range(self._max_concurrency):
                self._workers.append(asyncio.create_task(self._worker_loop(index)))

    async def stop(self) -> None:
        """停止后台 worker，并取消尚未完成的轮询任务。"""
        workers = list(self._workers)
        self._workers.clear()
        for task in workers:
            task.cancel()
        for task in workers:
            with suppress(asyncio.CancelledError):
                await task
        while not self._queue.empty():
            with suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
                self._queue.task_done()
        async with self._lock:
            self._queued_run_ids.clear()
            self._active_run_ids.clear()

    async def enqueue(self, run_id: str) -> bool:
        """把运行加入后台队列；同一 run 已排队或运行中时返回 False。"""
        await self.start()
        async with self._lock:
            if run_id in self._queued_run_ids or run_id in self._active_run_ids:
                return False
            self._queued_run_ids.add(run_id)
            self._queue.put_nowait(run_id)
            return True

    async def snapshot(self) -> dict[str, list[str] | int]:
        """返回队列快照，供测试和诊断使用。"""
        async with self._lock:
            return {
                "queued": sorted(self._queued_run_ids),
                "active": sorted(self._active_run_ids),
                "worker_count": len(self._workers),
                "queue_size": self._queue.qsize(),
            }

    async def _worker_loop(self, index: int) -> None:
        """持续消费队列中的 AgentRun。"""
        while True:
            run_id = await self._queue.get()
            async with self._lock:
                self._queued_run_ids.discard(run_id)
                self._active_run_ids.add(run_id)
            try:
                await self._execute_run(run_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception(
                    "Autonomous Agent worker 执行失败: worker=%s run_id=%s", index, run_id
                )
                await self._mark_run_failed(run_id, str(exc))
            finally:
                async with self._lock:
                    self._active_run_ids.discard(run_id)
                self._queue.task_done()

    async def _execute_run(self, run_id: str) -> None:
        """使用独立 DB session 执行一次 AgentRun，避免占用 API 请求 session。"""
        store = get_postgres_store()
        await store.ensure_initialized()
        async with store.async_session() as session:
            runtime = AutonomousAgentRuntime(
                store=AutonomousAgentStore(session),
                artifact_store=get_artifact_store(),
            )
            run = await runtime.store.get_run(run_id)
            if not run:
                return
            if run.status not in {AgentRunStatus.RUNNING, AgentRunStatus.PAUSED}:
                return
            run.metadata["worker"] = {
                "backend": "in_process",
                "queued_at": run.metadata.get("queued_at"),
                "started_at": utc_now_naive().isoformat(),
            }
            await runtime.store.update_run(run)
            await runtime.execute_until_stop(run_id)

    async def _mark_run_failed(self, run_id: str, message: str) -> None:
        """worker 顶层异常兜底，避免运行长期停留在 running。"""
        with suppress(Exception):
            store = get_postgres_store()
            await store.ensure_initialized()
            async with store.async_session() as session:
                runtime = AutonomousAgentRuntime(
                    store=AutonomousAgentStore(session),
                    artifact_store=get_artifact_store(),
                )
                run = await runtime.store.get_run(run_id)
                if not run or run.status in {
                    AgentRunStatus.COMPLETED,
                    AgentRunStatus.FAILED,
                    AgentRunStatus.CANCELLED,
                }:
                    return
                run.status = AgentRunStatus.FAILED
                run.error_message = message or "Autonomous Agent worker 执行失败"
                run.completed_at = utc_now_naive()
                run.updated_at = utc_now_naive()
                await runtime.store.update_run(run)


_agent_worker_queue: AutonomousAgentWorkerQueue | None = None


def get_agent_worker_queue() -> AutonomousAgentWorkerQueue:
    """获取进程内 Agent worker 队列单例。"""
    global _agent_worker_queue
    if _agent_worker_queue is None:
        _agent_worker_queue = AutonomousAgentWorkerQueue(
            max_concurrency=get_settings().AUTONOMOUS_AGENT_WORKER_MAX_CONCURRENCY
        )
    return _agent_worker_queue


async def dispose_agent_worker_queue() -> None:
    """应用关闭时释放 Agent worker 任务。"""
    global _agent_worker_queue
    if _agent_worker_queue is not None:
        await _agent_worker_queue.stop()
        _agent_worker_queue = None
