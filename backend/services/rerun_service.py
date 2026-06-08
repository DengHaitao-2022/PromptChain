"""
版本化重跑服务

核心原则：
1. rerun 从指定节点起，创建新版本
2. 不覆盖旧版本，保留完整历史
3. 下游节点自动继承新版本输入
"""

from typing import Any

from core.time import normalize_api_datetime, utc_now_iso
from models import (
    ArtifactType,
    FactCheckReport,
    IntentCard,
    Outline,
    WorkflowRun,
    WorkflowRunStatus,
)
from services.artifact_store import ArtifactStore, get_artifact_store
from services.trace_service import TraceService, get_trace_service


class RerunService:
    """版本化重跑服务"""

    def __init__(
        self, artifact_store: ArtifactStore | None = None, trace_service: TraceService | None = None
    ):
        self.store = artifact_store or get_artifact_store()
        self.traces = trace_service or get_trace_service()

    async def get_rerun_options(self, workflow_run_id: str) -> list:
        """
        获取可重跑的节点列表

        返回每个节点及其最新 Artifact 版本，供用户选择重跑起点
        """
        options = await self.traces.get_rerun_options(workflow_run_id)
        allowed_nodes = await self._get_runtime_plan_node_ids(workflow_run_id)
        if not allowed_nodes:
            return options
        return [option for option in options if option.get("node_name") in allowed_nodes]

    async def _get_runtime_plan_node_ids(self, workflow_run_id: str) -> set[str]:
        workflow_run = await self.store.get_workflow_run(workflow_run_id)
        metadata = dict(workflow_run.metadata or {}) if workflow_run else {}
        plan = metadata.get("runtime_plan")
        if not isinstance(plan, dict):
            return set()

        steps = plan.get("steps")
        if not isinstance(steps, list):
            return set()

        node_ids = {
            str(step.get("id")) for step in steps if isinstance(step, dict) and step.get("id")
        }
        if "parse_intent" in node_ids:
            node_ids.add("clarify_intent")
        return node_ids

    async def _ensure_rerun_node_allowed(self, workflow_run_id: str, from_node: str) -> None:
        allowed_nodes = await self._get_runtime_plan_node_ids(workflow_run_id)
        if allowed_nodes and from_node not in allowed_nodes:
            raise ValueError(f"Node '{from_node}' is not enabled by this workflow runtime plan")

    async def prepare_rerun_state(
        self, workflow_run_id: str, from_node: str, updated_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        准备重跑状态

        收集 from_node 之前的所有 Artifact，构建新的初始状态

        Args:
            workflow_run_id: 原工作流运行ID
            from_node: 从哪个节点开始重跑
            updated_input: 可选的更新输入（如用户修改后的提纲）

        Returns:
            可用于启动新工作流的状态字典
        """
        await self._ensure_rerun_node_allowed(workflow_run_id, from_node)

        # 获取原工作流追踪
        trace = await self.traces.get_workflow_trace(workflow_run_id)

        # 找到 from_node 的位置
        from_node_index = -1
        for i, node in enumerate(trace["nodes"]):
            if node["node_name"] == from_node:
                from_node_index = i
                break

        if from_node_index == -1:
            raise ValueError(f"Node '{from_node}' not found in workflow")

        # 收集 from_node 之前的所有 Artifact（作为新运行的输入）
        preserved_state = {}

        for i, node in enumerate(trace["nodes"]):
            if i >= from_node_index:
                break

            for aid in node["output_artifact_ids"]:
                artifact_data = trace["artifacts"].get(aid)
                if artifact_data:
                    # 根据类型映射到状态字段
                    artifact_type = artifact_data["type"]
                    content = artifact_data["content"]

                    if artifact_type == ArtifactType.INTENT_CARD.value:
                        preserved_state["intent_card"] = IntentCard.model_validate(content)
                        preserved_state["intent_card_artifact_id"] = aid
                    elif artifact_type == ArtifactType.OUTLINE.value:
                        preserved_state["outline"] = Outline.model_validate(content)
                        preserved_state["outline_artifact_id"] = aid
                        preserved_state["outline_approved"] = True
                    elif artifact_type == ArtifactType.SECTION_CONTENT.value:
                        if "draft_sections" not in preserved_state:
                            preserved_state["draft_sections"] = {}
                        if "section_artifact_ids" not in preserved_state:
                            preserved_state["section_artifact_ids"] = {}

                        section_id = content.get("section_id")
                        if section_id:
                            preserved_state["draft_sections"][section_id] = content.get(
                                "content", ""
                            )
                            preserved_state["section_artifact_ids"][section_id] = aid
                    elif artifact_type == ArtifactType.FACT_CHECK_REPORT.value:
                        preserved_state["fact_check_report"] = FactCheckReport.model_validate(
                            content
                        )
                        preserved_state["fact_check_artifact_id"] = aid
                    elif artifact_type == ArtifactType.EVIDENCE_PACK.value:
                        preserved_state["evidence_pack"] = content
                        preserved_state["evidence_artifact_id"] = aid
                        if isinstance(content, dict):
                            preserved_state["citations"] = [
                                {
                                    "chunk_id": chunk.get("chunk_id"),
                                    "document_id": chunk.get("document_id"),
                                    "document_name": chunk.get("document_name"),
                                    "score": chunk.get("score"),
                                    "scope": chunk.get("scope"),
                                    "page_number": chunk.get("page_number"),
                                    "heading_path": chunk.get("heading_path") or [],
                                }
                                for chunk in content.get("chunks") or []
                                if isinstance(chunk, dict)
                            ]
                            preserved_state["knowledge_conflicts"] = content.get("conflicts") or []
                            preserved_state["unverified_points"] = (
                                content.get("unverified_points") or []
                            )
                    elif artifact_type == ArtifactType.FINAL_CONTENT.value:
                        preserved_state["final_content"] = content.get("sections", {})
                        preserved_state["final_content_artifact_id"] = aid

        # 应用用户更新
        if updated_input:
            preserved_state.update(updated_input)

        return preserved_state

    async def create_rerun_workflow(
        self,
        original_workflow_run_id: str,
        from_node: str,
        reason: str = "",
        updated_user_input: str | None = None,
    ) -> WorkflowRun:
        """
        创建新的 WorkflowRun 用于重跑（关联原始运行）

        Returns:
            新的 WorkflowRun 对象
        """
        # 获取原工作流
        original = await self.store.get_workflow_run(original_workflow_run_id)
        if not original:
            raise ValueError(f"WorkflowRun not found: {original_workflow_run_id}")

        original_metadata = dict(original.metadata or {})
        inherited_metadata = {
            key: original_metadata[key]
            for key in (
                "workspace_id",
                "user_id",
                "model_provider_id",
                "model_provider_name",
                "model_name",
                "runtime_model",
                "requested_model_provider_id",
                "requested_model_name",
                "runtime_plan",
                "retrieval_config",
                "scenario_code",
                "project_id",
                "edit_mode",
                "generation_mode",
                "target_asset_id",
            )
            if key in original_metadata
        }
        inherited_metadata.update(
            {
                "is_rerun": True,
                "original_workflow_run_id": original_workflow_run_id,
                "rerun_from_node": from_node,
                "rerun_reason": reason,
                "rerun_at": utc_now_iso(),
            }
        )

        # 创建新的 WorkflowRun
        new_workflow_run = WorkflowRun(
            workflow_name=original.workflow_name,
            workflow_version=original.workflow_version,
            workflow_definition_id=original.workflow_definition_id,
            workflow_version_id=original.workflow_version_id,
            user_input=updated_user_input or original.user_input,
            status=WorkflowRunStatus.RUNNING,
            metadata=inherited_metadata,
        )

        await self.store.create_workflow_run(new_workflow_run)
        return new_workflow_run

    async def get_rerun_history(self, workflow_run_id: str) -> list:
        """
        获取工作流的重跑历史

        返回所有由此工作流派生的重跑记录，或此工作流的原始来源
        """
        current = await self.store.get_workflow_run(workflow_run_id)
        if not current:
            return []

        # 先向上找到重跑树根节点，再从根节点向下收集整棵派生树。
        root = current
        visited_ancestors: set[str] = set()
        metadata = current.metadata or {}
        while metadata.get("is_rerun") and metadata.get("original_workflow_run_id"):
            original_id = metadata["original_workflow_run_id"]
            if original_id in visited_ancestors:
                break
            visited_ancestors.add(original_id)

            original = await self.store.get_workflow_run(original_id)
            if not original:
                break
            root = original
            metadata = original.metadata or {}

        all_runs = await self.store.get_all_workflow_runs()
        children_by_parent: dict[str, list[WorkflowRun]] = {}
        for run in all_runs:
            run_metadata = run.metadata or {}
            parent_id = run_metadata.get("original_workflow_run_id")
            if parent_id:
                children_by_parent.setdefault(parent_id, []).append(run)

        def _sort_key(run: WorkflowRun) -> tuple[str, str]:
            run_metadata = run.metadata or {}
            timestamp = (
                run_metadata.get("rerun_at")
                or getattr(run, "created_at", None)
                or getattr(run, "started_at", None)
                or ""
            )
            return str(timestamp), run.id

        history: list[dict[str, Any]] = []
        visited_descendants: set[str] = set()

        def _append_tree(run: WorkflowRun) -> None:
            if run.id in visited_descendants:
                return
            visited_descendants.add(run.id)
            history.append(normalize_api_datetime(run.model_dump()))

            children = sorted(children_by_parent.get(run.id, []), key=_sort_key)
            for child in children:
                _append_tree(child)

        _append_tree(root)

        return history


# 全局实例
_rerun_service: RerunService | None = None


def get_rerun_service() -> RerunService:
    """获取 RerunService 单例"""
    global _rerun_service
    if _rerun_service is None:
        _rerun_service = RerunService()
    return _rerun_service
