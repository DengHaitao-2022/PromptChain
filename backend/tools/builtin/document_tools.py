"""文档处理内置工具。"""

from __future__ import annotations

from typing import Any

from services import get_artifact_store
from tools.base import BaseTool, ToolExecutionError
from tools.builtin.artifact_tools import ensure_artifact_visible
from tools.runtime import ToolRuntime
from tools.schemas import RiskLevel, ToolResult, ToolSourceType, ToolSpec


class DocumentLoadTextTool(BaseTool):
    spec = ToolSpec(
        name="document.load_text",
        title="载入文本",
        description="从直接文本或 Artifact 中载入纯文本内容。",
        category="document",
        source_type=ToolSourceType.INTERNAL,
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "artifact_id": {"type": "string"},
                "field_path": {"type": "string", "default": "content"},
            },
            "anyOf": [{"required": ["text"]}, {"required": ["artifact_id"]}],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        risk_level=RiskLevel.READ_PRIVATE,
        permissions=["workflow_run.read"],
    )

    async def execute(self, input_data: dict[str, Any], runtime: ToolRuntime) -> ToolResult:
        text = input_data.get("text")
        source = "inline"
        if text is None:
            artifact = await (runtime.store or get_artifact_store()).get_artifact(
                input_data["artifact_id"]
            )
            if artifact is None:
                raise ToolExecutionError("ARTIFACT_NOT_FOUND", "Artifact 不存在")
            await ensure_artifact_visible(artifact, runtime)
            source = artifact.id
            value = artifact.model_dump(mode="json")
            for part in str(input_data.get("field_path") or "content").split("."):
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    value = None
                    break
            text = value if isinstance(value, str) else str(value or "")
        return ToolResult(
            output={"text": text, "length": len(text), "source": source},
            summary=f"已载入 {len(text)} 个字符",
        )


class DocumentChunkTextTool(BaseTool):
    spec = ToolSpec(
        name="document.chunk_text",
        title="文本切块",
        description="按字符窗口把文本切成可检索或可处理片段。",
        category="document",
        source_type=ToolSourceType.INTERNAL,
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "minLength": 1},
                "chunk_size": {
                    "type": "integer",
                    "minimum": 100,
                    "maximum": 20000,
                    "default": 1200,
                },
                "overlap": {"type": "integer", "minimum": 0, "maximum": 2000, "default": 120},
            },
            "required": ["text"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        risk_level=RiskLevel.READ_PUBLIC,
    )

    async def execute(self, input_data: dict[str, Any], runtime: ToolRuntime) -> ToolResult:
        text = input_data["text"]
        chunk_size = int(input_data.get("chunk_size") or 1200)
        overlap = min(int(input_data.get("overlap") or 120), chunk_size - 1)
        chunks: list[dict[str, Any]] = []
        start = 0
        while start < len(text):
            end = min(len(text), start + chunk_size)
            chunks.append(
                {
                    "index": len(chunks),
                    "start": start,
                    "end": end,
                    "content": text[start:end],
                }
            )
            if end == len(text):
                break
            start = end - overlap
        return ToolResult(
            output={"chunks": chunks, "chunk_count": len(chunks)},
            summary=f"已生成 {len(chunks)} 个文本块",
        )
