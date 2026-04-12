"""
统一异常映射逻辑。
"""

from dataclasses import dataclass
from typing import Any

import aiosmtplib
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError

from core.errors.codes import (
    COMMON_INTERNAL_ERROR,
    COMMON_VALIDATION_ERROR,
    INFRA_DATABASE_ERROR,
    INFRA_EMAIL_SERVICE_ERROR,
    INFRA_EXTERNAL_SERVICE_ERROR,
    INFRA_MODEL_SERVICE_ERROR,
    ErrorCodeDefinition,
    get_error_definition,
    get_fallback_code_for_status,
)
from core.errors.context import sanitize_infrastructure_details, summarize_internal_cause
from core.errors.exceptions import InfrastructureError, PromptChainError
from core.errors.models import ErrorEnvelope, RequestErrorContext


@dataclass(frozen=True, slots=True)
class MappedError:
    """异常映射结果。"""

    http_status: int
    envelope: ErrorEnvelope
    context: RequestErrorContext


def _build_context(
    *,
    request_id: str,
    path: str,
    method: str,
    code: str,
    internal_cause: BaseException | None = None,
) -> RequestErrorContext:
    return RequestErrorContext(
        request_id=request_id,
        path=path,
        method=method,
        error_code=code,
        internal_cause=summarize_internal_cause(internal_cause),
    )


def _build_envelope(
    *,
    definition: ErrorCodeDefinition,
    request_id: str,
    message: str | None = None,
    details: dict[str, Any] | list[dict[str, Any]] | None = None,
) -> ErrorEnvelope:
    return ErrorEnvelope(
        code=definition.code,
        message=message or definition.default_message,
        request_id=request_id,
        details=details,
    )


def _normalize_http_exception_message(exc: HTTPException, definition: ErrorCodeDefinition) -> str:
    if exc.status_code >= 500:
        return definition.default_message
    if isinstance(exc.detail, str) and exc.detail.strip():
        return exc.detail
    return definition.default_message


def _normalize_validation_details(exc: RequestValidationError) -> list[dict[str, Any]]:
    return [
        {
            "loc": list(error.get("loc", ())),
            "msg": error.get("msg"),
            "type": error.get("type"),
        }
        for error in exc.errors()
    ]


def _infer_raw_infrastructure_code(exc: BaseException) -> str | None:
    """基于常见基础设施异常类型推导统一错误码。"""

    if isinstance(exc, SQLAlchemyError):
        return INFRA_DATABASE_ERROR

    if isinstance(exc, aiosmtplib.errors.SMTPException):
        return INFRA_EMAIL_SERVICE_ERROR

    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        module_name = exc.__class__.__module__.lower()
        cause_text = f"{exc.__class__.__name__} {exc}".lower()
        model_markers = (
            "openai",
            "anthropic",
            "langchain",
            "litellm",
            "google",
            "gemini",
            "model",
        )
        if any(marker in module_name or marker in cause_text for marker in model_markers):
            return INFRA_MODEL_SERVICE_ERROR
        return INFRA_EXTERNAL_SERVICE_ERROR

    return None


def map_exception(
    exc: Exception,
    *,
    request_id: str,
    path: str,
    method: str,
) -> MappedError:
    """把内部异常统一映射为外部错误契约。"""

    if isinstance(exc, RequestValidationError):
        definition = get_error_definition(COMMON_VALIDATION_ERROR)
        return MappedError(
            http_status=definition.http_status,
            envelope=_build_envelope(
                definition=definition,
                request_id=request_id,
                details=_normalize_validation_details(exc),
            ),
            context=_build_context(
                request_id=request_id,
                path=path,
                method=method,
                code=definition.code,
                internal_cause=exc,
            ),
        )

    if isinstance(exc, PromptChainError):
        definition = get_error_definition(exc.code)
        details = exc.details
        message = exc.message or definition.default_message

        if isinstance(exc, InfrastructureError):
            details = sanitize_infrastructure_details(exc.details)
            message = definition.default_message

        return MappedError(
            http_status=definition.http_status,
            envelope=_build_envelope(
                definition=definition,
                request_id=request_id,
                message=message,
                details=details,
            ),
            context=_build_context(
                request_id=request_id,
                path=path,
                method=method,
                code=definition.code,
                internal_cause=exc.cause or exc,
            ),
        )

    if isinstance(exc, HTTPException):
        code = get_fallback_code_for_status(exc.status_code)
        definition = get_error_definition(code)
        return MappedError(
            http_status=exc.status_code,
            envelope=_build_envelope(
                definition=definition,
                request_id=request_id,
                message=_normalize_http_exception_message(exc, definition),
            ),
            context=_build_context(
                request_id=request_id,
                path=path,
                method=method,
                code=definition.code,
                internal_cause=exc,
            ),
        )

    raw_infra_code = _infer_raw_infrastructure_code(exc)
    if raw_infra_code is not None:
        definition = get_error_definition(raw_infra_code)
        return MappedError(
            http_status=definition.http_status,
            envelope=_build_envelope(
                definition=definition,
                request_id=request_id,
                message=definition.default_message,
            ),
            context=_build_context(
                request_id=request_id,
                path=path,
                method=method,
                code=definition.code,
                internal_cause=exc,
            ),
        )

    definition = get_error_definition(COMMON_INTERNAL_ERROR)
    return MappedError(
        http_status=definition.http_status,
        envelope=_build_envelope(
            definition=definition,
            request_id=request_id,
            message=definition.default_message,
        ),
        context=_build_context(
            request_id=request_id,
            path=path,
            method=method,
            code=definition.code,
            internal_cause=exc,
        ),
    )
