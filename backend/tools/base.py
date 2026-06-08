"""工具基类与输入输出校验。"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from jsonschema import Draft202012Validator
from jsonschema import exceptions as jsonschema_exceptions

from tools.runtime import ToolRuntime
from tools.schemas import ToolError, ToolResult, ToolSpec


class ToolExecutionError(Exception):
    """工具执行错误，向 ToolExecutor 返回结构化失败。"""

    def __init__(self, code: str, message: str, details: Any | None = None):
        super().__init__(message)
        self.code = code
        self.details = details


class BaseTool(ABC):
    """所有工具的统一抽象。"""

    spec: ToolSpec
    _validator_cache: ClassVar[dict[str, Draft202012Validator]] = {}

    def __init__(self, spec: ToolSpec | None = None):
        if spec is not None:
            self.spec = spec

    def validate_input(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """基于 JSON Schema 校验输入，保证权限策略之外仍有参数边界。"""
        schema = self.spec.input_schema or {"type": "object"}
        try:
            validator = self._validator_for_schema(schema)
            errors = sorted(validator.iter_errors(input_data), key=lambda item: item.path)
        except jsonschema_exceptions.SchemaError as exc:
            raise ToolExecutionError(
                "TOOL_SCHEMA_INVALID",
                f"工具 {self.spec.name} 的 input_schema 无效",
                {"schema_error": exc.message},
            ) from exc

        if errors:
            details = [
                {
                    "path": ".".join(map(str, error.absolute_path)) or "$",
                    "message": error.message,
                }
                for error in errors
            ]
            raise ToolExecutionError(
                "TOOL_INPUT_INVALID",
                f"工具 {self.spec.name} 的输入不符合 schema",
                details,
            )
        return input_data

    @classmethod
    def _validator_for_schema(cls, schema: dict[str, Any]) -> Draft202012Validator:
        """缓存固定 ToolSpec 的 JSON Schema validator，避免高频调用重复构造。"""
        cache_key = json.dumps(schema, sort_keys=True, default=str)
        validator = cls._validator_cache.get(cache_key)
        if validator is None:
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema)
            cls._validator_cache[cache_key] = validator
        return validator

    async def __call__(self, input_data: dict[str, Any], runtime: ToolRuntime) -> ToolResult:
        validated = self.validate_input(input_data)
        return await self.execute(validated, runtime)

    @abstractmethod
    async def execute(self, input_data: dict[str, Any], runtime: ToolRuntime) -> ToolResult:
        """执行工具。"""
        raise NotImplementedError


def tool_failure_result(code: str, message: str, details: Any | None = None) -> ToolResult:
    """构造结构化失败结果。"""
    return ToolResult(
        success=False,
        error=ToolError(code=code, message=message, details=details),
        summary=message,
    )
