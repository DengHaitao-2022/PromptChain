"""
工作流事件总线

用于在不改变现有 snapshot SSE 语义的前提下，
为单个 workflow_run 提供 token/section 级细粒度事件。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from core.time import utc_now_iso


@dataclass(slots=True)
class WorkflowStreamEvent:
    """SSE 细粒度事件载体。"""

    type: str
    workflow_run_id: str
    event_id: str
    timestamp: str
    data: dict[str, Any]


class WorkflowEventBus:
    """进程内事件总线。

    第一版先使用内存队列，满足单进程开发与本地调试场景。
    后续如需多进程/多实例部署，可替换为 Redis Pub/Sub。
    """

    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue[WorkflowStreamEvent]]] = {}

    def subscribe(self, workflow_run_id: str) -> asyncio.Queue[WorkflowStreamEvent]:
        """为指定 workflow_run 创建一个订阅队列。"""
        queue: asyncio.Queue[WorkflowStreamEvent] = asyncio.Queue(maxsize=1000)
        self._queues.setdefault(workflow_run_id, set()).add(queue)
        return queue

    def unsubscribe(
        self,
        workflow_run_id: str,
        queue: asyncio.Queue[WorkflowStreamEvent],
    ) -> None:
        """移除订阅队列，避免连接断开后残留引用。"""
        queues = self._queues.get(workflow_run_id)
        if not queues:
            return

        queues.discard(queue)
        if not queues:
            self._queues.pop(workflow_run_id, None)

    async def publish(
        self,
        workflow_run_id: str,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        """广播事件给当前 workflow_run 的所有订阅者。

        这里故意采用 drop-on-full 策略，避免慢客户端反向拖垮生成流程。
        """
        event = WorkflowStreamEvent(
            type=event_type,
            workflow_run_id=workflow_run_id,
            event_id=str(uuid4()),
            timestamp=utc_now_iso(),
            data=data,
        )

        for queue in list(self._queues.get(workflow_run_id, set())):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                continue


_workflow_event_bus = WorkflowEventBus()


def get_workflow_event_bus() -> WorkflowEventBus:
    """获取全局工作流事件总线实例。"""
    return _workflow_event_bus
