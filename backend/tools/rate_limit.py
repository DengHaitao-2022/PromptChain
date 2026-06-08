"""工具调用限流实现。"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Any

from core.config import get_settings

logger = logging.getLogger(__name__)


class RateLimitUnavailableError(RuntimeError):
    """限流后端不可用时抛出，生产 Redis 模式下必须 fail-closed。"""


class MemoryFixedWindowRateLimiter:
    """进程内固定窗口限流，仅作为本地开发 fallback。"""

    def __init__(self) -> None:
        self._windows: dict[str, deque[float]] = defaultdict(deque)

    async def hit(self, key: str, *, limit: int, window_seconds: int = 60) -> bool:
        """记录一次调用；返回 True 表示仍在限额内。"""
        now = time.monotonic()
        window = self._windows[key]
        while window and now - window[0] > window_seconds:
            window.popleft()
        if not window:
            self._windows.pop(key, None)
            window = self._windows[key]
        if len(window) >= limit:
            return False
        window.append(now)
        return True


class RedisFixedWindowRateLimiter:
    """Redis 固定窗口限流，支持多实例共享计数。"""

    def __init__(self, redis_url: str | None = None, *, key_prefix: str | None = None) -> None:
        settings = get_settings()
        self.redis_url = redis_url or settings.REDIS_URL
        self.key_prefix = key_prefix or settings.TOOL_RATE_LIMIT_REDIS_PREFIX
        self._redis: Any | None = None

    def _get_redis(self) -> Any:
        if self._redis is not None:
            return self._redis
        from redis import asyncio as redis_asyncio

        self._redis = redis_asyncio.from_url(self.redis_url, decode_responses=True)
        return self._redis

    async def hit(self, key: str, *, limit: int, window_seconds: int = 60) -> bool:
        """记录一次调用；返回 True 表示仍在限额内。"""
        window_id = int(time.time() // window_seconds)
        redis_key = f"{self.key_prefix}:{key}:{window_id}"
        redis = self._get_redis()
        current = await redis.incr(redis_key)
        if current == 1:
            await redis.expire(redis_key, window_seconds + 5)
        return int(current) <= limit


class ToolRateLimiter:
    """按配置选择 Redis 或内存限流。"""

    def __init__(self) -> None:
        settings = get_settings()
        self.backend = settings.TOOL_RATE_LIMIT_BACKEND
        self._memory = MemoryFixedWindowRateLimiter()
        self._redis = RedisFixedWindowRateLimiter() if self.backend == "redis" else None

    async def hit(self, key: str, *, limit: int, window_seconds: int = 60) -> bool:
        if self._redis is None:
            return await self._memory.hit(key, limit=limit, window_seconds=window_seconds)
        try:
            return await self._redis.hit(key, limit=limit, window_seconds=window_seconds)
        except Exception as exc:
            logger.exception("Redis 工具限流失败，拒绝工具调用: key=%s", key)
            raise RateLimitUnavailableError("工具限流 Redis 后端不可用，已拒绝调用") from exc
