"""Artifact 相关内置工具。"""

from __future__ import annotations

from typing import Any

from models import Artifact, ArtifactType, MemberRole
from services import get_artifact_store
from services.permission_service import is_admin_role
from tools.base import BaseTool, ToolExecutionError
from tools.runtime import ToolRuntime
from tools.schemas import RiskLevel, ToolResult, ToolSourceType, ToolSpec


def _store(runtime: ToolRuntime):
    return runtime.store or get_artifact_store()


def _artifact_type(value: str | None) -> ArtifactType:
    if not value:
        return ArtifactType.TOOL_RESULT
    try:
        return ArtifactType(value)
    except ValueError:
        return ArtifactType.TOOL_RESULT


def _coerce_role(value: str | None) -> MemberRole | None:
    if not value:
        return None
    try:
        return MemberRole(value)
    except ValueError:
        return None


async def ensure_artifact_visible(artifact: Artifact, runtime: ToolRuntime) -> None:
    """校验 Artifact 读取边界，防止直接工具调用绕过 WorkflowRun 归属校验。"""
    if runtime.workflow_run_id:
        if artifact.workflow_run_id != runtime.workflow_run_id:
            raise ToolExecutionError("ARTIFACT_ACCESS_DENIED", "Artifact 不属于当前工作流运行")
        return

    store = _store(runtime)
    if not hasattr(store, "get_workflow_run"):
        raise ToolExecutionError("ARTIFACT_ACCESS_DENIED", "无法确认 Artifact 的运行归属")

    workflow_run = await store.get_workflow_run(artifact.workflow_run_id)
    metadata = getattr(workflow_run, "metadata", None) if workflow_run is not None else None
    if not isinstance(metadata, dict):
        raise ToolExecutionError("ARTIFACT_ACCESS_DENIED", "Artifact 所属工作流缺少归属信息")

    if metadata.get("workspace_id") != runtime.workspace_id:
        raise ToolExecutionError("ARTIFACT_ACCESS_DENIED", "Artifact 不属于当前工作空间")

    role = _coerce_role(runtime.role)
    if not is_admin_role(role) and metadata.get("user_id") != runtime.user_id:
        raise ToolExecutionError("ARTIFACT_ACCESS_DENIED", "Artifact 不属于当前用户")


class ArtifactReadTool(BaseTool):
    spec = ToolSpec(
        name="artifact.read",
        title="读取 Artifact",
        description="读取当前工作流可见的 Artifact 内容和元数据。",
        category="artifact",
        source_type=ToolSourceType.INTERNAL,
        input_schema={
            "type": "object",
            "properties": {"artifact_id": {"type": "string", "minLength": 1}},
            "required": ["artifact_id"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        risk_level=RiskLevel.READ_PRIVATE,
        permissions=["workflow_run.read"],
    )

    async def execute(self, input_data: dict[str, Any], runtime: ToolRuntime) -> ToolResult:
        artifact = await _store(runtime).get_artifact(input_data["artifact_id"])
        if artifact is None:
            raise ToolExecutionError("ARTIFACT_NOT_FOUND", "Artifact 不存在")
        await ensure_artifact_visible(artifact, runtime)
        return ToolResult(
            output=artifact.model_dump(mode="json"),
            summary=f"已读取 Artifact {artifact.id}",
        )


class ArtifactWriteTool(BaseTool):
    spec = ToolSpec(
        name="artifact.write",
        title="写入 Artifact",
        description="把工具输出或中间数据写入版本化 Artifact。",
        category="artifact",
        source_type=ToolSourceType.INTERNAL,
        input_schema={
            "type": "object",
            "properties": {
                "content": {},
                "artifact_type": {"type": "string", "default": "tool_result"},
                "metadata": {"type": "object", "default": {}},
                "parent_version_id": {"type": ["string", "null"]},
            },
            "required": ["content"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        risk_level=RiskLevel.WRITE_INTERNAL,
        permissions=["workflow.update"],
    )

    async def execute(self, input_data: dict[str, Any], runtime: ToolRuntime) -> ToolResult:
        if not runtime.workflow_run_id:
            raise ToolExecutionError(
                "TOOL_RUNTIME_MISSING_WORKFLOW", "写入 Artifact 需要 workflow_run_id"
            )
        node_run_id = runtime.node_run_id or runtime.workflow_run_id
        artifact = await _store(runtime).create_artifact(
            artifact_type=_artifact_type(input_data.get("artifact_type")),
            content=input_data["content"],
            workflow_run_id=runtime.workflow_run_id,
            node_run_id=node_run_id,
            parent_version_id=input_data.get("parent_version_id"),
            metadata={
                **(input_data.get("metadata") or {}),
                "tool_name": self.spec.name,
                "tool_call_id": runtime.tool_call_id,
            },
        )
        return ToolResult(
            output=artifact.model_dump(mode="json"),
            summary=f"已写入 Artifact {artifact.id}",
            artifact_ids=[artifact.id],
        )


class ArtifactListVersionsTool(BaseTool):
    spec = ToolSpec(
        name="artifact.list_versions",
        title="列出 Artifact 版本",
        description="返回指定 Artifact 的版本链。",
        category="artifact",
        source_type=ToolSourceType.INTERNAL,
        input_schema={
            "type": "object",
            "properties": {"artifact_id": {"type": "string", "minLength": 1}},
            "required": ["artifact_id"],
            "additionalProperties": False,
        },
        output_schema={"type": "array"},
        risk_level=RiskLevel.READ_PRIVATE,
        permissions=["workflow_run.read"],
    )

    async def execute(self, input_data: dict[str, Any], runtime: ToolRuntime) -> ToolResult:
        artifact = await _store(runtime).get_artifact(input_data["artifact_id"])
        if artifact is None:
            raise ToolExecutionError("ARTIFACT_NOT_FOUND", "Artifact 不存在")
        await ensure_artifact_visible(artifact, runtime)
        versions = await _store(runtime).get_version_history(input_data["artifact_id"])
        return ToolResult(
            output=[item.model_dump(mode="json") for item in versions],
            summary=f"已返回 {len(versions)} 个 Artifact 版本",
        )
