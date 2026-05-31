"""
统一错误响应模型。
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorEnvelope(BaseModel):
    """统一失败响应外观。"""

    success: Literal[False] = False
    code: str
    message: str
    request_id: str
    details: dict[str, Any] | list[dict[str, Any]] | None = None
    data: None = None


class RequestErrorContext(BaseModel):
    """请求级错误上下文。"""

    request_id: str
    path: str = Field(default="")
    method: str = Field(default="")
    error_code: str | None = None
    internal_cause: str | None = None
