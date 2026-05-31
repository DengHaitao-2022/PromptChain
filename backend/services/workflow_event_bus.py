"""
工作流事件总线

用于在不改变现有 snapshot SSE 语义的前提下，
为单个 workflow_run 提供 token/section 级细粒度事件。
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from core.config import get_settings
from core.time import utc_now_iso

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class WorkflowStreamEvent:
    """SSE 细粒度事件载体。"""

    type: str
    workflow_run_id: str
    event_id: str
    timestamp: str
    data: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        """序列化为 Redis Pub/Sub 可传输的结构。"""
        return {
            "type": self.type,
            "workflow_run_id": self.workflow_run_id,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "data": self.data,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> WorkflowStreamEvent:
        """从 Redis Pub/Sub 消息恢复事件对象。"""
        data = payload.get("data")
        return cls(
            type=str(payload.get("type") or "message"),
            workflow_run_id=str(payload.get("workflow_run_id") or ""),
            event_id=str(payload.get("event_id") or uuid4()),
            timestamp=str(payload.get("timestamp") or utc_now_iso()),
            data=data if isinstance(data, dict) else {},
        )


class _WorkflowEventBusBackend(Protocol):
    """事件总线后端协议，保持路由层现有队列接口不变。"""

    def subscribe(self, workflow_run_id: str) -> asyncio.Queue[WorkflowStreamEvent]:
        """为指定 workflow_run 创建一个订阅队列。"""

    def unsubscribe(
        self,
        workflow_run_id: str,
        queue: asyncio.Queue[WorkflowStreamEvent],
    ) -> None:
        """移除订阅队列。"""

    async def publish(
        self,
        workflow_run_id: str,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        """发布事件。"""

    async def close(self) -> None:
        """释放后端资源。"""


def _build_event(
    workflow_run_id: str,
    event_type: str,
    data: dict[str, Any],
) -> WorkflowStreamEvent:
    """构建统一事件载体。"""
    return WorkflowStreamEvent(
        type=event_type,
        workflow_run_id=workflow_run_id,
        event_id=str(uuid4()),
        timestamp=utc_now_iso(),
        data=data,
    )


class _MemoryWorkflowEventBus:
    """进程内事件总线。

    适用于本地单进程开发；多 worker 或多实例部署应使用 Redis 后端。
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
        event = _build_event(workflow_run_id, event_type, data)

        for queue in list(self._queues.get(workflow_run_id, set())):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                continue

    async def close(self) -> None:
        """进程内事件总线无需释放外部资源。"""


@dataclass(slots=True)
class _RedisSubscription:
    """Redis 订阅任务上下文。"""

    task: asyncio.Task[None]


class _RedisWorkflowEventBus:
    """Redis Pub/Sub 事件总线。

    每个 SSE 连接仍拿到本地 asyncio.Queue；后台任务负责把 Redis
    channel 消息转入本地队列，从而保持路由层调用契约稳定。
    """

    def __init__(self, redis_url: str, channel_prefix: str) -> None:
        self._redis_url = redis_url
        self._channel_prefix = channel_prefix.rstrip(":")
        self._redis: Any | None = None
        self._subscriptions: dict[
            str, dict[asyncio.Queue[WorkflowStreamEvent], _RedisSubscription]
        ] = {}

    def _channel_name(self, workflow_run_id: str) -> str:
        """生成单个 workflow_run 的 Redis channel 名称。"""
        return f"{self._channel_prefix}:{workflow_run_id}"

    def _get_redis(self) -> Any:
        """延迟创建 Redis 客户端，避免 memory 模式需要 redis 依赖。"""
        if self._redis is not None:
            return self._redis

        try:
            from redis import asyncio as redis_asyncio
        except ImportError as exc:
            raise RuntimeError(
                "WORKFLOW_EVENT_BUS_BACKEND=redis 需要安装 redis Python 客户端"
            ) from exc

        self._redis = redis_asyncio.from_url(self._redis_url, decode_responses=True)
        return self._redis

    def subscribe(self, workflow_run_id: str) -> asyncio.Queue[WorkflowStreamEvent]:
        """订阅指定 workflow_run 的 Redis channel。"""
        queue: asyncio.Queue[WorkflowStreamEvent] = asyncio.Queue(maxsize=1000)
        pubsub = self._get_redis().pubsub()
        task = asyncio.create_task(self._consume_pubsub(workflow_run_id, queue, pubsub))
        task.add_done_callback(self._discard_task_result)
        self._subscriptions.setdefault(workflow_run_id, {})[queue] = _RedisSubscription(task)
        return queue

    def unsubscribe(
        self,
        workflow_run_id: str,
        queue: asyncio.Queue[WorkflowStreamEvent],
    ) -> None:
        """取消单个 SSE 连接对应的 Redis 订阅任务。"""
        subscriptions = self._subscriptions.get(workflow_run_id)
        if not subscriptions:
            return

        subscription = subscriptions.pop(queue, None)
        if subscription:
            subscription.task.cancel()

        if not subscriptions:
            self._subscriptions.pop(workflow_run_id, None)

    async def publish(
        self,
        workflow_run_id: str,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        """通过 Redis Pub/Sub 发布细粒度事件。"""
        event = _build_event(workflow_run_id, event_type, data)
        payload = json.dumps(event.to_payload(), ensure_ascii=False, default=str)

        try:
            await self._get_redis().publish(self._channel_name(workflow_run_id), payload)
        except Exception:
            # 细粒度事件不可用不应中断内容生成；SSE 仍会通过 snapshot 轮询补偿状态。
            logger.exception("Redis 工作流事件发布失败: workflow_run_id=%s", workflow_run_id)

    async def close(self) -> None:
        """取消所有订阅并关闭 Redis 连接。"""
        tasks: list[asyncio.Task[None]] = []
        for subscriptions in self._subscriptions.values():
            for subscription in subscriptions.values():
                subscription.task.cancel()
                tasks.append(subscription.task)
        self._subscriptions.clear()

        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task

        if self._redis is not None:
            close = getattr(self._redis, "aclose", None) or getattr(self._redis, "close", None)
            if close is not None:
                result = close()
                if hasattr(result, "__await__"):
                    await result
            self._redis = None

    async def _consume_pubsub(
        self,
        workflow_run_id: str,
        queue: asyncio.Queue[WorkflowStreamEvent],
        pubsub: Any,
    ) -> None:
        """把 Redis channel 消息转入当前 SSE 连接的本地队列。"""
        channel = self._channel_name(workflow_run_id)
        try:
            await pubsub.subscribe(channel)
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue

                event = self._event_from_redis_message(message)
                if event is None:
                    continue

                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    continue
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Redis 工作流事件订阅失败: workflow_run_id=%s", workflow_run_id)
            self._put_stream_error(queue, workflow_run_id)
        finally:
            with suppress(Exception):
                await pubsub.unsubscribe(channel)
            close = getattr(pubsub, "aclose", None) or getattr(pubsub, "close", None)
            if close is not None:
                with suppress(Exception):
                    result = close()
                    if hasattr(result, "__await__"):
                        await result

    def _event_from_redis_message(self, message: dict[str, Any]) -> WorkflowStreamEvent | None:
        """解析 Redis Pub/Sub 消息，非法消息直接丢弃。"""
        raw_data = message.get("data")
        if not isinstance(raw_data, str):
            return None

        try:
            payload = json.loads(raw_data)
        except json.JSONDecodeError:
            logger.warning("忽略无法解析的 Redis 工作流事件消息")
            return None

        if not isinstance(payload, dict):
            return None

        return WorkflowStreamEvent.from_payload(payload)

    def _put_stream_error(
        self,
        queue: asyncio.Queue[WorkflowStreamEvent],
        workflow_run_id: str,
    ) -> None:
        """订阅失败时向当前 SSE 连接报告非致命流错误。"""
        event = _build_event(
            workflow_run_id,
            "stream_error",
            {"detail": "实时事件通道暂不可用，页面将继续使用状态快照刷新。"},
        )
        with suppress(asyncio.QueueFull):
            queue.put_nowait(event)

    @staticmethod
    def _discard_task_result(task: asyncio.Task[None]) -> None:
        """取回后台任务结果，避免断开连接后的取消异常污染日志。"""
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Redis 工作流事件后台任务异常")


class WorkflowEventBus:
    """根据配置选择具体事件总线后端的门面。"""

    def __init__(self) -> None:
        settings = get_settings()
        backend = settings.WORKFLOW_EVENT_BUS_BACKEND
        if backend == "memory":
            self._backend: _WorkflowEventBusBackend = _MemoryWorkflowEventBus()
        elif backend == "redis":
            self._backend = _RedisWorkflowEventBus(
                settings.REDIS_URL,
                settings.WORKFLOW_EVENT_BUS_REDIS_CHANNEL_PREFIX,
            )
        else:
            raise RuntimeError(f"不支持的 WORKFLOW_EVENT_BUS_BACKEND: {backend}")

    def subscribe(self, workflow_run_id: str) -> asyncio.Queue[WorkflowStreamEvent]:
        """为指定 workflow_run 创建一个订阅队列。"""
        return self._backend.subscribe(workflow_run_id)

    def unsubscribe(
        self,
        workflow_run_id: str,
        queue: asyncio.Queue[WorkflowStreamEvent],
    ) -> None:
        """移除订阅队列，避免连接断开后残留引用。"""
        self._backend.unsubscribe(workflow_run_id, queue)

    async def publish(
        self,
        workflow_run_id: str,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        """广播事件给当前 workflow_run 的所有订阅者。"""
        await self._backend.publish(workflow_run_id, event_type, data)

    async def close(self) -> None:
        """释放事件总线资源。"""
        await self._backend.close()


_workflow_event_bus = WorkflowEventBus()


def get_workflow_event_bus() -> WorkflowEventBus:
    """获取全局工作流事件总线实例。"""
    return _workflow_event_bus


async def dispose_workflow_event_bus() -> None:
    """释放全局工作流事件总线资源。"""
    await _workflow_event_bus.close()
