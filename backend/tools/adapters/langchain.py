"""LangChain Tool 适配。"""

from __future__ import annotations

from typing import Any

from tools.base import BaseTool
from tools.runtime import ToolRuntime
from tools.schemas import RiskLevel, ToolResult, ToolSourceType, ToolSpec


def langchain_tool_to_spec(tool: Any) -> ToolSpec:
    """从 LangChain tool 元数据生成 ToolSpec。"""
    args_schema = getattr(tool, "args_schema", None)
    if args_schema is not None and hasattr(args_schema, "model_json_schema"):
        input_schema = args_schema.model_json_schema()
    else:
        input_schema = {"type": "object"}
    name = str(getattr(tool, "name", None) or tool.__class__.__name__)
    return ToolSpec(
        name=f"langchain.{name}",
        title=name,
        description=str(getattr(tool, "description", None) or name),
        category="langchain",
        source_type=ToolSourceType.LANGCHAIN,
        input_schema=input_schema,
        risk_level=RiskLevel.READ_PRIVATE,
        permissions=["workflow_run.read"],
        enabled=False,
        metadata={"langchain": {"name": name}},
    )


class LangChainToolWrapper(BaseTool):
    """把 LangChain Tool 包装为 PromptChain BaseTool。"""

    def __init__(self, tool: Any, spec: ToolSpec | None = None):
        super().__init__(spec or langchain_tool_to_spec(tool))
        self._tool = tool

    async def execute(self, input_data: dict[str, Any], runtime: ToolRuntime) -> ToolResult:
        if hasattr(self._tool, "ainvoke"):
            output = await self._tool.ainvoke(input_data)
        elif hasattr(self._tool, "invoke"):
            output = self._tool.invoke(input_data)
        else:
            output = self._tool(**input_data)
        return ToolResult(output=output, summary=f"LangChain tool {self.spec.name} 执行完成")
