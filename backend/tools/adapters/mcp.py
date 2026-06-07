"""MCP tool schema 适配。"""

from __future__ import annotations

from typing import Any

from tools.schemas import RiskLevel, ToolSourceType, ToolSpec


def mcp_tool_to_spec(tool: dict[str, Any]) -> ToolSpec:
    """把 MCP tools/list 返回项映射为 PromptChain ToolSpec。"""
    annotations = tool.get("annotations") if isinstance(tool.get("annotations"), dict) else {}
    risk_value = annotations.get("riskLevel") or annotations.get("risk_level") or "external_action"
    try:
        risk_level = RiskLevel(str(risk_value))
    except ValueError:
        risk_level = RiskLevel.EXTERNAL_ACTION
    return ToolSpec(
        name=str(tool["name"]),
        title=tool.get("title"),
        description=str(tool.get("description") or tool["name"]),
        category=str(annotations.get("category") or "mcp"),
        source_type=ToolSourceType.MCP,
        input_schema=tool.get("inputSchema") or {"type": "object"},
        output_schema=tool.get("outputSchema"),
        annotations=annotations,
        risk_level=risk_level,
        requires_approval=risk_level in {RiskLevel.EXTERNAL_ACTION, RiskLevel.DESTRUCTIVE},
        enabled=False,
        metadata={"mcp": {"original_tool": tool}},
    )


def spec_to_mcp_tool(spec: ToolSpec) -> dict[str, Any]:
    """把 PromptChain ToolSpec 输出为 MCP 兼容 tool 描述。"""
    return spec.to_mcp_tool()
