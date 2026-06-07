"""知识检索内置工具。"""

from __future__ import annotations

from typing import Any

from db.postgres_store import get_postgres_store
from models import KnowledgeScope, KnowledgeSearchRequest, RetrievalMode
from services.knowledge_service import KnowledgeService
from tools.base import BaseTool, ToolExecutionError
from tools.runtime import ToolRuntime
from tools.schemas import RiskLevel, ToolResult, ToolSourceType, ToolSpec


class QueryWorkspaceKnowledgeTool(BaseTool):
    spec = ToolSpec(
        name="retrieval.query_workspace_knowledge",
        title="检索工作空间知识库",
        description="按当前工作空间权限检索 workspace/personal/run_upload 知识库证据。",
        category="retrieval",
        source_type=ToolSourceType.INTERNAL,
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "scopes": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["workspace", "personal", "run_upload"]},
                    "default": ["workspace"],
                },
                "top_k": {"type": "integer", "minimum": 1, "maximum": 30, "default": 8},
                "min_score": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.55},
                "mode": {
                    "type": "string",
                    "enum": ["vector", "keyword", "hybrid"],
                    "default": "hybrid",
                },
                "filters": {"type": "object", "default": {}},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        risk_level=RiskLevel.READ_PRIVATE,
        permissions=["knowledge_base.read"],
        cost_policy={"max_calls_per_minute": 30},
    )

    async def execute(self, input_data: dict[str, Any], runtime: ToolRuntime) -> ToolResult:
        if not runtime.workspace_id or not runtime.user_id:
            raise ToolExecutionError(
                "TOOL_RUNTIME_MISSING_AUTH", "知识检索需要用户和工作空间上下文"
            )
        scopes = [KnowledgeScope(scope) for scope in (input_data.get("scopes") or ["workspace"])]
        request = KnowledgeSearchRequest(
            query=input_data["query"],
            scopes=scopes,
            top_k=input_data.get("top_k") or 8,
            min_score=input_data.get("min_score")
            if input_data.get("min_score") is not None
            else 0.55,
            mode=RetrievalMode(input_data.get("mode") or "hybrid"),
            filters=input_data.get("filters") or {},
            workflow_run_id=runtime.workflow_run_id,
            node_run_id=runtime.node_run_id,
        )
        if runtime.db_session is not None:
            service = KnowledgeService(runtime.db_session)
            response = await service.search(
                request=request,
                workspace_id=runtime.workspace_id,
                user_id=runtime.user_id,
            )
        else:
            async with get_postgres_store().initialized_session() as session:
                service = KnowledgeService(session)
                response = await service.search(
                    request=request,
                    workspace_id=runtime.workspace_id,
                    user_id=runtime.user_id,
                )
        payload = response.model_dump(mode="json")
        return ToolResult(
            output=payload,
            summary=f"检索到 {len(payload.get('evidence_pack', {}).get('chunks', []))} 条证据",
            state_patch={"evidence_pack": payload.get("evidence_pack")},
            metadata={"retrieval_log_id": payload.get("retrieval_log_id")},
        )
