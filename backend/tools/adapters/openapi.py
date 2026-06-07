"""OpenAPI operation 到 ToolSpec 的映射。"""

from __future__ import annotations

from typing import Any

from tools.schemas import RiskLevel, ToolSourceType, ToolSpec


def openapi_operation_to_spec(
    *,
    operation_id: str,
    method: str,
    path: str,
    operation: dict[str, Any],
    server_url: str | None = None,
) -> ToolSpec:
    """把单个 OpenAPI operation 映射为工具定义。

    V1 只负责统一发现与治理建模，实际 HTTP 调用仍需管理员显式启用。
    """
    method_upper = method.upper()
    risk_level = RiskLevel.READ_PRIVATE if method_upper == "GET" else RiskLevel.EXTERNAL_ACTION
    request_body = (
        operation.get("requestBody") if isinstance(operation.get("requestBody"), dict) else {}
    )
    content = request_body.get("content") if isinstance(request_body.get("content"), dict) else {}
    json_content = (
        content.get("application/json") if isinstance(content.get("application/json"), dict) else {}
    )
    input_schema = (
        json_content.get("schema")
        if isinstance(json_content.get("schema"), dict)
        else {"type": "object"}
    )
    return ToolSpec(
        name=f"openapi.{operation_id}",
        title=operation.get("summary") or operation_id,
        description=operation.get("description")
        or operation.get("summary")
        or f"{method_upper} {path}",
        category="openapi",
        source_type=ToolSourceType.OPENAPI,
        input_schema=input_schema,
        risk_level=risk_level,
        permissions=["workflow_run.read"]
        if risk_level == RiskLevel.READ_PRIVATE
        else ["workflow.execute"],
        requires_approval=risk_level == RiskLevel.EXTERNAL_ACTION,
        enabled=False,
        metadata={
            "openapi": {
                "operation_id": operation_id,
                "method": method_upper,
                "path": path,
                "server_url": server_url,
            }
        },
    )
