"""验证类内置工具。"""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator
from jsonschema import exceptions as jsonschema_exceptions

from tools.base import BaseTool
from tools.runtime import ToolRuntime
from tools.schemas import RiskLevel, ToolResult, ToolSourceType, ToolSpec


class JsonSchemaValidateTool(BaseTool):
    spec = ToolSpec(
        name="validation.json_schema_validate",
        title="JSON Schema 校验",
        description="使用 JSON Schema draft 2020-12 校验任意 JSON 数据。",
        category="validation",
        source_type=ToolSourceType.INTERNAL,
        input_schema={
            "type": "object",
            "properties": {
                "schema": {"type": "object"},
                "instance": {},
            },
            "required": ["schema", "instance"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "valid": {"type": "boolean"},
                "errors": {"type": "array"},
            },
        },
        risk_level=RiskLevel.READ_PUBLIC,
    )

    async def execute(self, input_data: dict[str, Any], runtime: ToolRuntime) -> ToolResult:
        schema = input_data["schema"]
        instance = input_data.get("instance")
        try:
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema)
            errors = sorted(validator.iter_errors(instance), key=lambda item: item.path)
        except jsonschema_exceptions.SchemaError as exc:
            return ToolResult(
                output={
                    "valid": False,
                    "schema_valid": False,
                    "errors": [{"path": "$schema", "message": exc.message}],
                },
                summary="JSON Schema 本身无效",
            )

        payload = {
            "valid": not errors,
            "schema_valid": True,
            "errors": [
                {
                    "path": ".".join(map(str, error.absolute_path)) or "$",
                    "message": error.message,
                }
                for error in errors
            ],
        }
        return ToolResult(
            output=payload,
            summary="校验通过" if payload["valid"] else f"发现 {len(errors)} 个校验错误",
        )
