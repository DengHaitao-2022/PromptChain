"""
工作流执行器

ContentGenerationWorkflow 负责：
- 启动、恢复、暂停工作流
- 逐节点驱动 LangGraph 图
- 同步 WorkflowRun 持久化状态
- WebSocket 实时状态推送
"""

import asyncio
from typing import Any

from graph.builder import build_content_generation_graph
from graph.state import GraphState
from models import WorkflowRun, WorkflowRunStatus
from services import format_workflow_error, get_artifact_store


class ContentGenerationWorkflow:
    """内容生成工作流执行器"""

    def __init__(self):
        self.graph = build_content_generation_graph()
        self.store = get_artifact_store()
        self._active_tasks: dict[str, asyncio.Task] = {}
        self._workflow_locks: dict[str, asyncio.Lock] = {}

    def _base_config(self, workflow_run_id: str) -> dict:
        return {"configurable": {"thread_id": workflow_run_id}}

    def _get_lock(self, workflow_run_id: str) -> asyncio.Lock:
        if workflow_run_id not in self._workflow_locks:
            self._workflow_locks[workflow_run_id] = asyncio.Lock()
        return self._workflow_locks[workflow_run_id]

    def _is_task_running(self, workflow_run_id: str) -> bool:
        task = self._active_tasks.get(workflow_run_id)
        return task is not None and not task.done()

    async def _safe_get_state(self, config: dict) -> Any:
        try:
            return await self.graph.aget_state(config)
        except Exception:
            return None

    async def _get_latest_node_run(self, workflow_run_id: str):
        if hasattr(self.store, "get_latest_node_run"):
            return await self.store.get_latest_node_run(workflow_run_id)
        node_runs = await self.store.get_node_runs_by_workflow(workflow_run_id)
        if not node_runs:
            return None
        return max(node_runs, key=lambda run: run.started_at)

    async def _load_workflow_context(self, workflow_run: WorkflowRun) -> dict | None:
        if hasattr(self.store, "get_workflow_context"):
            return await self.store.get_workflow_context(
                workflow_run.workflow_definition_id,
                workflow_run.workflow_version_id,
            )
        return None

    async def _build_initial_state(
        self,
        workflow_run: WorkflowRun,
        overrides: dict | None = None,
    ) -> GraphState:
        workflow_context = await self._load_workflow_context(workflow_run)
        state: GraphState = {
            "user_input": workflow_run.user_input,
            "workflow_run_id": workflow_run.id,
            "workspace_id": (workflow_run.metadata or {}).get("workspace_id"),
            "user_id": (workflow_run.metadata or {}).get("user_id"),
            "model_provider_id": (workflow_run.metadata or {}).get("model_provider_id"),
            "model_name": (workflow_run.metadata or {}).get("model_name"),
            "workflow_definition_id": workflow_run.workflow_definition_id,
            "workflow_version_id": workflow_run.workflow_version_id,
            "workflow_context": workflow_context,
            "is_paused": False,
            "pause_reason": None,
            "needs_clarification": False,
            "clarification_questions": [],
            "user_clarifications": {},
            "awaiting_outline_approval": False,
            "outline_approved": False,
            "draft_sections": {},
            "section_artifact_ids": {},
            "refinement_history": [],
        }
        if overrides:
            state.update(overrides)
        return state

    # ==================== WebSocket 事件推送 ====================

    async def _emit_node_status(
        self,
        workflow_run_id: str,
        node_id: str,
        status: str,
        data: dict | None = None,
    ) -> None:
        try:
            from routes.websocket_routes import emit_node_status

            await emit_node_status(workflow_run_id, node_id, status, data or {})
        except Exception:
            return

    async def _emit_workflow_status(
        self,
        workflow_run_id: str,
        status: str,
        data: dict | None = None,
    ) -> None:
        try:
            from routes.websocket_routes import emit_workflow_status

            await emit_workflow_status(workflow_run_id, status, data or {})
        except Exception:
            return

    # ==================== 状态同步 ====================

    async def _sync_workflow_run(
        self,
        workflow_run_id: str,
        state: dict,
        snapshot: Any = None,
    ) -> WorkflowRun:
        workflow_run = await self.store.get_workflow_run(workflow_run_id)
        if workflow_run is None:
            raise ValueError(f"WorkflowRun not found: {workflow_run_id}")

        latest_node_run = await self._get_latest_node_run(workflow_run_id)
        next_node = None
        checkpoint_id = None
        if snapshot is not None:
            next_node = snapshot.next[0] if getattr(snapshot, "next", None) else None
            checkpoint_id = (
                snapshot.config.get("configurable", {}).get("checkpoint_id")
                if getattr(snapshot, "config", None)
                else None
            )

        workflow_run.current_node = next_node or (
            latest_node_run.node_name if latest_node_run is not None else None
        )

        if workflow_run.status != WorkflowRunStatus.COMPLETED:
            if state.get("is_paused"):
                workflow_run.status = WorkflowRunStatus.PAUSED
            elif workflow_run.status == WorkflowRunStatus.PAUSED:
                # 外部 pause 请求在当前节点完成后才真正落到 graph state，
                # 在此之前先保留持久化 paused 标记，避免被 running 覆盖。
                workflow_run.status = WorkflowRunStatus.PAUSED
            elif state.get("error"):
                workflow_run.status = WorkflowRunStatus.FAILED
            else:
                workflow_run.status = WorkflowRunStatus.RUNNING

        metadata = dict(workflow_run.metadata or {})
        metadata["last_public_status"] = self._get_workflow_status(state)
        if "pause_reason" in state and state.get("pause_reason") is not None:
            metadata["pause_reason"] = state.get("pause_reason")
        elif workflow_run.status != WorkflowRunStatus.PAUSED:
            metadata["pause_reason"] = None
        if state.get("error"):
            metadata["error"] = state.get("error")
        elif workflow_run.status != WorkflowRunStatus.FAILED:
            metadata.pop("error", None)

        if checkpoint_id is not None:
            metadata["checkpoint_id"] = checkpoint_id
        metadata["workflow_context_loaded"] = bool(state.get("workflow_context"))
        workflow_run.metadata = metadata

        await self.store.update_workflow_run(workflow_run)
        return workflow_run

    async def _mark_failed(self, workflow_run_id: str, error: str) -> None:
        workflow_run = await self.store.get_workflow_run(workflow_run_id)
        if workflow_run is None:
            return
        workflow_run.status = WorkflowRunStatus.FAILED
        metadata = dict(workflow_run.metadata or {})
        metadata["error"] = error
        workflow_run.metadata = metadata
        await self.store.update_workflow_run(workflow_run)
        await self._emit_workflow_status(
            workflow_run_id,
            "failed",
            {"error": error, "current_node": workflow_run.current_node},
        )

    async def _capture_graph_failure(
        self,
        workflow_run_id: str,
        current_config: dict,
        current_node: str | None,
        exc: Exception,
        fallback_state: dict | None = None,
    ) -> dict:
        """把节点异常写入图状态，避免审批/恢复接口直接抛 500。"""
        public_error = format_workflow_error(exc)
        snapshot = await self._safe_get_state(current_config)
        state = dict(snapshot.values) if snapshot is not None else dict(fallback_state or {})
        state["error"] = public_error
        if current_node:
            state["current_node"] = current_node

        failed_snapshot = snapshot
        try:
            failed_config = await self.graph.aupdate_state(
                current_config,
                {"error": public_error, "current_node": current_node},
            )
            failed_snapshot = await self._safe_get_state(failed_config)
            if failed_snapshot is not None:
                state = dict(failed_snapshot.values)
                state["error"] = public_error
                if current_node:
                    state["current_node"] = current_node
        except Exception:
            failed_snapshot = snapshot

        workflow_run = await self._sync_workflow_run(
            workflow_run_id,
            state,
            failed_snapshot,
        )

        latest_node_run = await self._get_latest_node_run(workflow_run_id)
        if current_node:
            await self._emit_node_status(
                workflow_run_id,
                current_node,
                "failed",
                {
                    "node_run_id": latest_node_run.id if latest_node_run else None,
                    "status": latest_node_run.status.value if latest_node_run else "failed",
                    "duration_ms": latest_node_run.duration_ms if latest_node_run else None,
                    "error": public_error,
                },
            )
        await self._emit_workflow_status(
            workflow_run_id,
            "failed",
            {"error": public_error, "current_node": workflow_run.current_node or current_node},
        )

        return {
            "workflow_run_id": workflow_run_id,
            "state": state,
            "status": "failed",
        }

    # ==================== 图驱动引擎 ====================

    async def _run_scheduled_drive(
        self,
        workflow_run_id: str,
        *,
        initial_state: dict | None = None,
        config: dict | None = None,
        emit_resumed: bool = False,
    ) -> None:
        try:
            await self._drive_workflow(
                workflow_run_id,
                initial_state=initial_state,
                config=config,
                emit_resumed=emit_resumed,
            )
        except Exception as exc:
            await self._mark_failed(workflow_run_id, str(exc))

    def _schedule_drive(
        self,
        workflow_run_id: str,
        *,
        initial_state: dict | None = None,
        config: dict | None = None,
        emit_resumed: bool = False,
    ) -> None:
        if self._is_task_running(workflow_run_id):
            return

        task = asyncio.create_task(
            self._run_scheduled_drive(
                workflow_run_id,
                initial_state=initial_state,
                config=config,
                emit_resumed=emit_resumed,
            )
        )
        self._active_tasks[workflow_run_id] = task

        def _cleanup(_: asyncio.Task) -> None:
            self._active_tasks.pop(workflow_run_id, None)

        task.add_done_callback(_cleanup)

    async def _drive_workflow(
        self,
        workflow_run_id: str,
        *,
        initial_state: dict | None = None,
        config: dict | None = None,
        emit_resumed: bool = False,
    ) -> dict:
        current_config = config or self._base_config(workflow_run_id)
        invoke_input = initial_state

        async with self._get_lock(workflow_run_id):
            if emit_resumed:
                workflow_run = await self.store.get_workflow_run(workflow_run_id)
                await self._emit_workflow_status(
                    workflow_run_id,
                    "resumed",
                    {"current_node": workflow_run.current_node if workflow_run else None},
                )

            while True:
                snapshot_before = await self._safe_get_state(current_config)
                current_node = (
                    snapshot_before.next[0]
                    if snapshot_before is not None and getattr(snapshot_before, "next", None)
                    else None
                )
                if current_node:
                    await self._emit_node_status(
                        workflow_run_id,
                        current_node,
                        "started",
                        {"current_node": current_node},
                    )

                try:
                    result = await self.graph.ainvoke(invoke_input, current_config)
                except Exception as exc:
                    return await self._capture_graph_failure(
                        workflow_run_id,
                        current_config,
                        current_node,
                        exc,
                        fallback_state=invoke_input,
                    )
                invoke_input = None

                snapshot_after = await self._safe_get_state(self._base_config(workflow_run_id))
                if snapshot_after is None:
                    state = result
                else:
                    state = snapshot_after.values
                    current_config = snapshot_after.config or current_config

                workflow_run = await self._sync_workflow_run(
                    workflow_run_id,
                    state,
                    snapshot_after,
                )

                latest_node_run = await self._get_latest_node_run(workflow_run_id)
                if current_node and latest_node_run and latest_node_run.node_name == current_node:
                    node_status = (
                        "failed" if latest_node_run.status.value == "failed" else "completed"
                    )
                    await self._emit_node_status(
                        workflow_run_id,
                        current_node,
                        node_status,
                        {
                            "node_run_id": latest_node_run.id,
                            "status": latest_node_run.status.value,
                            "duration_ms": latest_node_run.duration_ms,
                            "error": latest_node_run.error_message,
                        },
                    )

                if workflow_run.status == WorkflowRunStatus.PAUSED:
                    pause_reason = workflow_run.metadata.get("pause_reason")
                    if not state.get("is_paused"):
                        paused_config = await self.graph.aupdate_state(
                            current_config,
                            {"is_paused": True, "pause_reason": pause_reason},
                        )
                        paused_snapshot = await self._safe_get_state(paused_config)
                        if paused_snapshot is not None:
                            state = paused_snapshot.values
                            current_config = paused_snapshot.config or paused_config
                            workflow_run = await self._sync_workflow_run(
                                workflow_run_id,
                                state,
                                paused_snapshot,
                            )

                    await self._emit_workflow_status(
                        workflow_run_id,
                        "paused",
                        {
                            "reason": pause_reason,
                            "current_node": workflow_run.current_node,
                        },
                    )
                    break

                public_status = self._get_workflow_status(state)
                if public_status == "needs_clarification":
                    await self._emit_workflow_status(
                        workflow_run_id,
                        "gate_waiting",
                        {
                            "gate_type": "clarification",
                            "questions": state.get("clarification_questions", []),
                            "current_node": workflow_run.current_node,
                        },
                    )
                    break
                if public_status == "awaiting_outline_approval":
                    outline = state.get("outline")
                    if hasattr(outline, "model_dump"):
                        outline = outline.model_dump()
                    await self._emit_workflow_status(
                        workflow_run_id,
                        "gate_waiting",
                        {
                            "gate_type": "outline_approval",
                            "outline": outline,
                            "current_node": workflow_run.current_node,
                        },
                    )
                    break
                if public_status == "awaiting_fact_check_approval":
                    report = state.get("fact_check_report")
                    if hasattr(report, "model_dump"):
                        report = report.model_dump()
                    await self._emit_workflow_status(
                        workflow_run_id,
                        "gate_waiting",
                        {
                            "gate_type": "fact_check_approval",
                            "questions": report,
                            "current_node": workflow_run.current_node,
                        },
                    )
                    break
                if public_status == "completed":
                    await self._emit_workflow_status(
                        workflow_run_id,
                        "completed",
                        {"current_node": workflow_run.current_node},
                    )
                    break
                if public_status == "failed":
                    await self._emit_workflow_status(
                        workflow_run_id,
                        "failed",
                        {
                            "error": state.get("error"),
                            "current_node": workflow_run.current_node,
                        },
                    )
                    break
                if snapshot_after is None or not getattr(snapshot_after, "next", None):
                    break

            return {
                "workflow_run_id": workflow_run_id,
                "state": state,
                "status": self._get_workflow_status(state),
            }

    # ==================== 公开 API ====================

    async def start(
        self,
        user_input: str,
        workflow_definition_id: str | None = None,
        workflow_version_id: str | None = None,
        workspace_id: str | None = None,
        user_id: str | None = None,
        model_provider_id: str | None = None,
        model_name: str | None = None,
    ) -> dict:
        """启动新的工作流，并在后台逐节点推进。"""
        metadata = {}
        if workspace_id:
            metadata["workspace_id"] = workspace_id
        if user_id:
            metadata["user_id"] = user_id
        if model_provider_id:
            metadata["model_provider_id"] = model_provider_id
        if model_name:
            metadata["model_name"] = model_name

        workflow_run = WorkflowRun(
            user_input=user_input,
            status=WorkflowRunStatus.RUNNING,
            workflow_definition_id=workflow_definition_id,
            workflow_version_id=workflow_version_id,
            metadata=metadata,
        )
        await self.store.create_workflow_run(workflow_run)

        initial_state = await self._build_initial_state(workflow_run)
        self._schedule_drive(workflow_run.id, initial_state=initial_state)

        return {
            "workflow_run_id": workflow_run.id,
            "state": {**initial_state, "current_node": "parse_intent"},
            "status": "running",
        }

    async def resume(self, workflow_run_id: str, user_input: dict) -> dict:
        """
        恢复暂停的工作流

        Args:
            workflow_run_id: 工作流运行ID
            user_input: 用户输入（审批决策、澄清回答等）

        Returns:
            更新后的工作流状态
        """
        base_config = self._base_config(workflow_run_id)
        snapshot = await self._safe_get_state(base_config)

        if snapshot is None:
            workflow_run = await self.store.get_workflow_run(workflow_run_id)
            if workflow_run is None:
                raise ValueError(f"WorkflowRun not found: {workflow_run_id}")
            initial_state = await self._build_initial_state(workflow_run, user_input)
            return await self._drive_workflow(
                workflow_run_id,
                initial_state=initial_state,
            )

        updated_config = await self.graph.aupdate_state(base_config, user_input)
        return await self._drive_workflow(
            workflow_run_id,
            config=updated_config,
            emit_resumed=True,
        )

    async def rerun_from_node(
        self,
        workflow_run_id: str,
        *,
        from_node: str,
        preserved_state: dict,
    ) -> dict:
        """创建新运行后，从指定节点继续执行而不是回到图入口。"""
        workflow_run = await self.store.get_workflow_run(workflow_run_id)
        if workflow_run is None:
            raise ValueError(f"WorkflowRun not found: {workflow_run_id}")

        initial_state = await self._build_initial_state(
            workflow_run,
            {
                **preserved_state,
                "rerun_from_node": from_node,
            },
        )

        if from_node == "parse_intent":
            return await self._drive_workflow(
                workflow_run_id,
                initial_state=initial_state,
                emit_resumed=True,
            )

        predecessor_by_node = {
            "clarify_intent": "parse_intent",
            "generate_outline": "parse_intent",
            "approve_outline": "generate_outline",
            "generate_content": "approve_outline",
            "self_refine": "generate_content",
            "check_facts": "self_refine",
            "approve_fact_check": "check_facts",
            "finalize": "check_facts",
        }
        predecessor = predecessor_by_node.get(from_node)
        if predecessor is None:
            raise ValueError(f"Unsupported rerun node: {from_node}")

        updated_config = await self.graph.aupdate_state(
            self._base_config(workflow_run_id),
            initial_state,
            as_node=predecessor,
        )
        return await self._drive_workflow(
            workflow_run_id,
            config=updated_config,
            emit_resumed=True,
        )

    async def _resume_from_node(
        self,
        workflow_run_id: str,
        user_input: dict,
        *,
        as_node: str,
    ) -> dict:
        """从指定 Gate 前置节点恢复，让 LangGraph 正确进入对应审批节点。"""
        base_config = self._base_config(workflow_run_id)
        snapshot = await self._safe_get_state(base_config)

        if snapshot is None:
            workflow_run = await self.store.get_workflow_run(workflow_run_id)
            if workflow_run is None:
                raise ValueError(f"WorkflowRun not found: {workflow_run_id}")
            initial_state = await self._build_initial_state(workflow_run, user_input)
            return await self._drive_workflow(
                workflow_run_id,
                initial_state=initial_state,
            )

        updated_config = await self.graph.aupdate_state(base_config, user_input, as_node=as_node)
        return await self._drive_workflow(
            workflow_run_id,
            config=updated_config,
            emit_resumed=True,
        )

    async def pause(self, workflow_run_id: str, reason: str = "") -> dict:
        """请求手动暂停，当前节点完成后停在下一份 checkpoint。"""
        workflow_run = await self.store.get_workflow_run(workflow_run_id)
        if workflow_run is None:
            raise ValueError(f"WorkflowRun not found: {workflow_run_id}")

        workflow_run.status = WorkflowRunStatus.PAUSED
        metadata = dict(workflow_run.metadata or {})
        metadata["pause_reason"] = reason
        workflow_run.metadata = metadata
        await self.store.update_workflow_run(workflow_run)

        state = {}
        if not self._is_task_running(workflow_run_id):
            snapshot = await self._safe_get_state(self._base_config(workflow_run_id))
            if snapshot is not None:
                updated_config = await self.graph.aupdate_state(
                    self._base_config(workflow_run_id),
                    {"is_paused": True, "pause_reason": reason},
                )
                paused_snapshot = await self._safe_get_state(updated_config)
                if paused_snapshot is not None:
                    state = paused_snapshot.values
                    await self._sync_workflow_run(
                        workflow_run_id,
                        state,
                        paused_snapshot,
                    )
        else:
            snapshot = await self._safe_get_state(self._base_config(workflow_run_id))
            if snapshot is not None:
                state = dict(snapshot.values)

        state = {**state, "is_paused": True, "pause_reason": reason}
        return {
            "workflow_run_id": workflow_run_id,
            "state": state,
            "status": self._get_workflow_status(state),
        }

    async def resume_paused(self, workflow_run_id: str) -> dict:
        """恢复用户手动暂停的工作流。"""
        workflow_run = await self.store.get_workflow_run(workflow_run_id)
        if workflow_run is None:
            raise ValueError(f"WorkflowRun not found: {workflow_run_id}")

        workflow_run.status = WorkflowRunStatus.RUNNING
        metadata = dict(workflow_run.metadata or {})
        metadata["pause_reason"] = None
        workflow_run.metadata = metadata
        await self.store.update_workflow_run(workflow_run)

        base_config = self._base_config(workflow_run_id)
        snapshot = await self._safe_get_state(base_config)
        if snapshot is None:
            initial_state = await self._build_initial_state(workflow_run)
            self._schedule_drive(
                workflow_run_id,
                initial_state=initial_state,
                emit_resumed=True,
            )
            return {
                "workflow_run_id": workflow_run_id,
                "state": {**initial_state, "current_node": "parse_intent"},
                "status": "running",
            }

        updated_config = await self.graph.aupdate_state(
            base_config,
            {"is_paused": False, "pause_reason": None},
        )
        updated_snapshot = await self._safe_get_state(updated_config)
        state = updated_snapshot.values if updated_snapshot is not None else {}
        self._schedule_drive(
            workflow_run_id,
            config=updated_config,
            emit_resumed=True,
        )
        return {
            "workflow_run_id": workflow_run_id,
            "state": state,
            "status": self._get_workflow_status(state),
        }

    async def approve_outline(
        self,
        workflow_run_id: str,
        action: str,
        feedback: str = "",
        modified_outline: dict | None = None,
    ) -> dict:
        """
        处理提纲审批

        Args:
            workflow_run_id: 工作流运行ID
            action: "approve" | "modify" | "regenerate"
            feedback: 用户反馈
            modified_outline: 修改后的提纲（action 为 modify 时）
        """
        user_decision = {"action": action, "feedback": feedback}
        if modified_outline:
            user_decision["modified_outline"] = modified_outline

        return await self._resume_from_node(
            workflow_run_id,
            {"user_decision": user_decision, "awaiting_outline_approval": False},
            as_node="generate_outline",
        )

    async def approve_fact_check(
        self,
        workflow_run_id: str,
        decisions: dict[str, str],
        manual_corrections: dict[str, str] | None = None,
    ) -> dict:
        """处理事实核查审批，并从事实核查节点恢复到审批节点。"""
        return await self._resume_from_node(
            workflow_run_id,
            {
                "fact_check_decisions": decisions,
                "manual_corrections": manual_corrections or {},
                "awaiting_fact_check_approval": False,
            },
            as_node="check_facts",
        )

    def _get_workflow_status(self, state: dict) -> str:
        """获取工作流当前状态"""
        if state.get("needs_clarification"):
            return "needs_clarification"
        if state.get("awaiting_outline_approval"):
            return "awaiting_outline_approval"
        if state.get("awaiting_fact_check_approval"):
            return "awaiting_fact_check_approval"
        if state.get("is_paused"):
            return "paused"
        if state.get("error"):
            return "failed"
        if state.get("final_content"):
            return "completed"
        return "running"


# ==================== 全局单例 ====================

_workflow: ContentGenerationWorkflow | None = None


def get_workflow() -> ContentGenerationWorkflow:
    """获取工作流执行器单例"""
    global _workflow
    if _workflow is None:
        _workflow = ContentGenerationWorkflow()
    return _workflow
