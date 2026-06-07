"""Workflow-as-Tool 适配。"""

from __future__ import annotations

from typing import Any

from tools.schemas import RiskLevel, ToolSourceType, ToolSpec


def workflow_context_to_tool_spec(workflow_context: dict[str, Any]) -> ToolSpec:
    """把已发布工作流快照映射为可复用工具定义。"""
    workflow_id = workflow_context.get("workflow_definition_id") or workflow_context.get("id")
    version_id = workflow_context.get("workflow_version_id")
    name = workflow_context.get("definition_name") or workflow_context.get("name") or workflow_id
    return ToolSpec(
        name=f"workflow.{workflow_id}",
        title=str(name),
        description=str(workflow_context.get("definition_description") or "已发布工作流工具"),
        category="workflow",
        source_type=ToolSourceType.WORKFLOW,
        input_schema={
            "type": "object",
            "properties": {
                "user_input": {"type": "string", "minLength": 1},
                "metadata": {"type": "object", "default": {}},
            },
            "required": ["user_input"],
        },
        output_schema={"type": "object"},
        risk_level=RiskLevel.WRITE_INTERNAL,
        permissions=["workflow.execute"],
        enabled=False,
        metadata={
            "workflow": {
                "workflow_definition_id": workflow_id,
                "workflow_version_id": version_id,
            }
        },
    )
