"""
统一异常分层定义。
"""

from typing import Any

from core.errors.codes import COMMON_VALIDATION_ERROR, is_registered_error_code


class PromptChainError(Exception):
    """统一错误体系的基类异常。"""

    def __init__(
        self,
        *,
        code: str,
        message: str | None = None,
        details: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message or code)
        if not is_registered_error_code(code):
            raise ValueError(f"未注册的 PromptChain 错误码: {code}")
        self.code = code
        self.message = message
        self.details = details or None
        self.cause = cause
        if cause is not None:
            self.__cause__ = cause


class DomainError(PromptChainError):
    """业务规则错误。"""


class ApplicationError(PromptChainError):
    """应用流程错误。"""


class InfrastructureError(PromptChainError):
    """基础设施依赖错误。"""


class ValidationFailedError(ApplicationError):
    """请求参数或输入校验失败。"""

    def __init__(self, message: str | None = None, details: dict[str, Any] | None = None) -> None:
        super().__init__(code=COMMON_VALIDATION_ERROR, message=message, details=details)
