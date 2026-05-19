"""
请求级错误上下文与基础设施异常脱敏工具。
"""

from collections.abc import Mapping
from contextvars import ContextVar, Token
from typing import Any
from uuid import uuid4

from fastapi import Request

REQUEST_ID_HEADER = "X-Request-ID"
_request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)
_SAFE_INFRA_DETAIL_KEYS = frozenset(
    {
        "dependency",
        "hint",
        "operation",
        "provider",
        "resource",
        "retryable",
        "service",
    }
)


def generate_request_id() -> str:
    """生成请求追踪标识。"""

    return uuid4().hex


def bind_request_id(request_id: str) -> Token[str | None]:
    """绑定请求级 request_id 到上下文。"""

    return _request_id_context.set(request_id)


def release_request_id(token: Token[str | None]) -> None:
    """释放请求级 request_id 上下文。"""

    _request_id_context.reset(token)


def get_request_id(default: str | None = None) -> str | None:
    """读取当前上下文中的 request_id。"""

    return _request_id_context.get() or default


def resolve_request_id(request: Request | None = None) -> str:
    """优先从请求和上下文解析 request_id，不存在时自动生成。"""

    if request is not None:
        header_request_id = request.headers.get(REQUEST_ID_HEADER)
        if header_request_id:
            return header_request_id

        state_request_id = getattr(request.state, "request_id", None)
        if state_request_id:
            return state_request_id

    return get_request_id() or generate_request_id()


def sanitize_infrastructure_details(details: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """仅保留允许对外暴露的基础设施上下文字段。"""

    if not details:
        return None

    safe_details = {
        key: value
        for key, value in details.items()
        if key in _SAFE_INFRA_DETAIL_KEYS and value is not None
    }
    return safe_details or None


def summarize_internal_cause(exc: BaseException | None) -> str | None:
    """生成仅用于内部排障的原因摘要。"""

    if exc is None:
        return None
    return str(exc)[:500] or exc.__class__.__name__
