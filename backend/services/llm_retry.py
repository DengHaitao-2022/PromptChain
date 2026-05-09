"""LLM 调用重试工具。"""

import asyncio
from collections.abc import Awaitable, Callable

from .llm_errors import is_retryable_llm_error


async def invoke_with_llm_retry[T](
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay_seconds: float = 1.0,
    max_delay_seconds: float = 4.0,
) -> T:
    """对短暂性模型服务异常做指数退避重试。"""
    last_error: Exception | None = None

    for attempt_index in range(attempts):
        try:
            return await operation()
        except Exception as exc:
            last_error = exc
            is_last_attempt = attempt_index >= attempts - 1
            if is_last_attempt or not is_retryable_llm_error(exc):
                raise

            delay = min(max_delay_seconds, base_delay_seconds * (2**attempt_index))
            await asyncio.sleep(delay)

    if last_error is not None:
        raise last_error
    raise RuntimeError("LLM retry operation did not run")
