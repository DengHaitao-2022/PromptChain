"""
统一错误处理器与请求上下文挂接。
"""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from core.errors.context import (
    REQUEST_ID_HEADER,
    bind_request_id,
    release_request_id,
    resolve_request_id,
)
from core.errors.exceptions import PromptChainError
from core.errors.mapping import MappedError, map_exception


def _build_json_response(mapped_error: MappedError) -> JSONResponse:
    """把统一错误映射结果转换为 JSON 响应。"""

    return JSONResponse(
        status_code=mapped_error.http_status,
        content=mapped_error.envelope.model_dump(),
        headers={REQUEST_ID_HEADER: mapped_error.envelope.request_id},
    )


def install_request_context(application: FastAPI) -> None:
    """挂接请求级 request_id 中间件。"""

    if getattr(application.state, "_request_context_installed", False):
        return

    @application.middleware("http")
    async def _request_context_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = resolve_request_id(request)
        request.state.request_id = request_id
        token = bind_request_id(request_id)
        try:
            response = await call_next(request)
        finally:
            release_request_id(token)

        response.headers.setdefault(REQUEST_ID_HEADER, request_id)
        return response

    application.state._request_context_installed = True


def register_error_handlers(application: FastAPI) -> None:
    """注册统一异常处理器。"""

    if getattr(application.state, "_error_handlers_registered", False):
        return

    async def _handle_error(request: Request, exc: Exception) -> JSONResponse:
        mapped_error = map_exception(
            exc,
            request_id=resolve_request_id(request),
            path=str(request.url.path),
            method=request.method,
        )
        return _build_json_response(mapped_error)

    application.add_exception_handler(PromptChainError, _handle_error)
    application.add_exception_handler(HTTPException, _handle_error)
    application.add_exception_handler(RequestValidationError, _handle_error)
    application.add_exception_handler(Exception, _handle_error)
    application.state._error_handlers_registered = True


def install_error_infrastructure(application: FastAPI) -> None:
    """统一挂接 request_id 中间件和全局异常处理器。"""

    install_request_context(application)
    register_error_handlers(application)
