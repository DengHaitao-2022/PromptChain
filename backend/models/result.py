"""
统一 API 响应兼容层。

注意：该模块保留给仍使用 `Result/PageResult` 的旧成功响应与局部兼容场景。
新错误路径应抛出 `PromptChainError`，由 `core.errors` 的全局 handler 输出统一
`ErrorEnvelope`。
"""

from pydantic import BaseModel

from core.errors.codes import get_legacy_numeric_code
from core.errors.models import ErrorEnvelope


class Result[T](BaseModel):
    """
    旧版 API 响应格式。

    成功响应:
    {
        "code": 0,
        "message": "success",
        "data": {...}
    }

    错误响应:
    {
        "code": 40001,
        "message": "错误描述",
        "data": null
    }
    """

    code: int = 0
    message: str = "success"
    data: T | None = None

    @classmethod
    def success(cls, data: T = None, message: str = "success") -> Result[T]:
        """创建旧版成功响应。"""
        return cls(code=0, message=message, data=data)

    @classmethod
    def error(cls, code: int, message: str, data: T = None) -> Result[T]:
        """创建旧版错误响应，仅供未迁移调用方临时兼容。"""
        return cls(code=code, message=message, data=data)

    @classmethod
    def from_error_envelope(cls, error: ErrorEnvelope) -> Result[None]:
        """把统一错误 envelope 桥接为旧数字 code 风格。"""

        return cls(
            code=get_legacy_numeric_code(error.code),
            message=error.message,
            data=None,
        )

    @classmethod
    def bad_request(cls, message: str = "请求参数错误") -> Result:
        """400 Bad Request，仅供未迁移调用方临时兼容。"""
        return cls(code=40000, message=message)

    @classmethod
    def unauthorized(cls, message: str = "未授权") -> Result:
        """401 Unauthorized，仅供未迁移调用方临时兼容。"""
        return cls(code=40100, message=message)

    @classmethod
    def forbidden(cls, message: str = "无权限") -> Result:
        """403 Forbidden，仅供未迁移调用方临时兼容。"""
        return cls(code=40300, message=message)

    @classmethod
    def not_found(cls, message: str = "资源不存在") -> Result:
        """404 Not Found，仅供未迁移调用方临时兼容。"""
        return cls(code=40400, message=message)

    @classmethod
    def server_error(cls, message: str = "服务器内部错误") -> Result:
        """500 Internal Server Error，仅供未迁移调用方临时兼容。"""
        return cls(code=50000, message=message)


class PageResult[T](BaseModel):
    """
    分页响应格式
    """

    code: int = 0
    message: str = "success"
    data: list[T] | None = None
    total: int = 0
    page: int = 1
    page_size: int = 20

    @classmethod
    def success(
        cls, data: list[T], total: int, page: int = 1, page_size: int = 20
    ) -> PageResult[T]:
        """创建分页成功响应"""
        return cls(
            code=0, message="success", data=data, total=total, page=page, page_size=page_size
        )
