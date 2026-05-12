"""
版本化重跑服务

核心原则：
1. rerun 从指定节点起，创建新版本
2. 不覆盖旧版本，保留完整历史
3. 下游节点自动继承新版本输入
"""

from typing import Any

from core.time import utc_now_iso
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
        return await self.traces.get_rerun_options(workflow_run_id)

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

        # 创建新的 WorkflowRun
        new_workflow_run = WorkflowRun(
            workflow_name=original.workflow_name,
            workflow_version=original.workflow_version,
            user_input=updated_user_input or original.user_input,
            status=WorkflowRunStatus.RUNNING,
            metadata={
                "is_rerun": True,
                "original_workflow_run_id": original_workflow_run_id,
                "rerun_from_node": from_node,
                "rerun_reason": reason,
                "rerun_at": utc_now_iso(),
            },
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

        history = [current.model_dump()]

        # 向上追溯原始工作流
        metadata = current.metadata or {}
        while metadata.get("is_rerun") and metadata.get("original_workflow_run_id"):
            original_id = metadata["original_workflow_run_id"]
            original = await self.store.get_workflow_run(original_id)
            if original:
                history.insert(0, original.model_dump())
                metadata = original.metadata or {}
            else:
                break

        # 向下查找派生的重跑
        all_runs = await self.store.get_all_workflow_runs()
        for run in all_runs:
            run_metadata = run.metadata or {}
            if run_metadata.get("original_workflow_run_id") == workflow_run_id:
                history.append(run.model_dump())

        return history


# 全局实例
_rerun_service: RerunService | None = None


def get_rerun_service() -> RerunService:
    """获取 RerunService 单例"""
    global _rerun_service
    if _rerun_service is None:
        _rerun_service = RerunService()
    return _rerun_service
