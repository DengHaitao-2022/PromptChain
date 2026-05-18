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

from core.time import utc_now_iso
from graph.builder import build_content_generation_graph
from graph.runtime_plan import compile_workflow_runtime_plan
from graph.state import GraphState
from models import ArtifactType, FactCheckReport, WorkflowRun, WorkflowRunStatus
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

    def _require_bound_workflow_context(
        self,
        workflow_run: WorkflowRun,
        workflow_context: dict | None,
    ) -> None:
        """显式绑定发布工作流时，禁止静默退回默认链路。"""
        if not workflow_run.workflow_definition_id and not workflow_run.workflow_version_id:
            return
        if not workflow_context or not workflow_context.get("workflow_version_id"):
            raise ValueError("指定的工作流尚未发布或版本不存在，无法启动运行。")
        if not isinstance(workflow_context.get("nodes"), list):
            raise ValueError("指定的工作流版本缺少节点快照，无法启动运行。")

    async def _build_initial_state(
        self,
        workflow_run: WorkflowRun,
        overrides: dict | None = None,
    ) -> GraphState:
        workflow_context = await self._load_workflow_context(workflow_run)
        self._require_bound_workflow_context(workflow_run, workflow_context)
        metadata_runtime_plan = (workflow_run.metadata or {}).get("runtime_plan")
        runtime_plan = (
            metadata_runtime_plan
            if isinstance(metadata_runtime_plan, dict) and workflow_context is None
            else compile_workflow_runtime_plan(workflow_context)
        )
        actual_workflow_definition_id = (
            workflow_context.get("workflow_definition_id")
            if isinstance(workflow_context, dict)
            else workflow_run.workflow_definition_id
        )
        actual_workflow_version_id = (
            workflow_context.get("workflow_version_id")
            if isinstance(workflow_context, dict)
            else workflow_run.workflow_version_id
        )
        state: GraphState = {
            "user_input": workflow_run.user_input,
            "workflow_run_id": workflow_run.id,
            "workspace_id": (workflow_run.metadata or {}).get("workspace_id"),
            "user_id": (workflow_run.metadata or {}).get("user_id"),
            "model_provider_id": (workflow_run.metadata or {}).get("model_provider_id"),
            "model_provider_name": (workflow_run.metadata or {}).get("model_provider_name"),
            "model_name": (workflow_run.metadata or {}).get("model_name"),
            "workflow_definition_id": actual_workflow_definition_id,
            "workflow_version_id": actual_workflow_version_id,
            "workflow_context": workflow_context,
            "runtime_plan": runtime_plan,
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
            if "runtime_plan" not in overrides:
                state["runtime_plan"] = runtime_plan

        metadata = dict(workflow_run.metadata or {})
        metadata["workflow_context_loaded"] = bool(workflow_context)
        metadata["runtime_plan"] = state.get("runtime_plan")
        workflow_run.workflow_definition_id = actual_workflow_definition_id
        workflow_run.workflow_version_id = actual_workflow_version_id
        workflow_run.metadata = metadata
        await self.store.update_workflow_run(workflow_run)
        return state

    # ==================== 实时事件推送 ====================

    async def _publish_stream_event(
        self,
        workflow_run_id: str,
        event_type: str,
        data: dict,
    ) -> None:
        try:
            from services.workflow_event_bus import get_workflow_event_bus

            await get_workflow_event_bus().publish(workflow_run_id, event_type, data)
        except Exception:
            return

    @staticmethod
    def _coerce_event_mapping(value: Any) -> dict[str, Any]:
        """将事件载荷中的 Pydantic 模型统一转为可序列化字典。"""
        if hasattr(value, "model_dump"):
            value = value.model_dump()
        return value if isinstance(value, dict) else {}

    @classmethod
    def _coerce_event_list(cls, value: Any) -> list[dict[str, Any]]:
        """将事件载荷中的模型列表统一转为字典列表。"""
        if not isinstance(value, list):
            return []
        return [item_payload for item in value if (item_payload := cls._coerce_event_mapping(item))]

    @staticmethod
    def _get_gate_metadata(workflow_run: WorkflowRun | None) -> dict[str, Any]:
        """读取当前运行记录上的 Gate 元数据。"""
        if workflow_run is None or not isinstance(workflow_run.metadata, dict):
            return {}
        gate = workflow_run.metadata.get("gate")
        return gate if isinstance(gate, dict) else {}

    @staticmethod
    def _map_clarification_priority(value: Any) -> str:
        """把澄清问题内部优先级映射为前端稳定枚举。"""
        if isinstance(value, str) and value in {"high", "medium", "low"}:
            return value
        try:
            priority = int(value)
        except (TypeError, ValueError):
            priority = 5
        if priority <= 2:
            return "high"
        if priority == 3:
            return "medium"
        return "low"

    @classmethod
    def _normalize_clarification_gate_questions(cls, questions: Any) -> list[dict[str, Any]]:
        """统一澄清 Gate 事件的问题结构，避免泄漏内部数值枚举。"""
        normalized: list[dict[str, Any]] = []
        for question in cls._coerce_event_list(questions):
            normalized.append(
                {
                    "field": question.get("field"),
                    "question": question.get("question"),
                    "priority": cls._map_clarification_priority(question.get("priority", 5)),
                    "default_assumption": question.get("default_assumption"),
                }
            )
        return normalized

    @classmethod
    def _build_outline_gate_questions(cls, outline: Any) -> list[dict[str, Any]]:
        """构建提纲审批事件中的问题列表，保持与公开 Gate 契约一致。"""
        outline_payload = cls._coerce_event_mapping(outline)
        sections = outline_payload.get("sections")
        question: dict[str, Any] = {
            "question": "请确认当前提纲是否可以进入正文生成。",
            "action_options": ["approve", "modify", "regenerate"],
        }
        if isinstance(sections, list):
            question["section_count"] = len(sections)
        if isinstance(outline_payload.get("total_target_words"), int):
            question["target_words"] = outline_payload["total_target_words"]
        return [question]

    @classmethod
    def _build_fact_check_gate_questions(cls, report: Any) -> list[dict[str, Any]]:
        """只把高风险事实核查项作为人工 Gate 问题发给前端。"""
        report_payload = cls._coerce_event_mapping(report)
        results = report_payload.get("results")
        if not isinstance(results, list):
            return []

        questions: list[dict[str, Any]] = []
        for result in results:
            result_payload = cls._coerce_event_mapping(result)
            if result_payload.get("risk_level") != "high":
                continue
            questions.append(
                {
                    "claim_id": result_payload.get("claim_id"),
                    "question": result_payload.get("verification_question"),
                    "risk_level": result_payload.get("risk_level"),
                    "suggested_correction": result_payload.get("suggested_correction"),
                }
            )
        return questions

    async def _emit_node_status(
        self,
        workflow_run_id: str,
        node_id: str,
        status: str,
        data: dict | None = None,
    ) -> None:
        event_type = f"node_{status}"
        payload = {"type": event_type, "node_id": node_id, "data": data or {}}
        await self._publish_stream_event(workflow_run_id, event_type, payload)

        try:
            from routes.websocket_routes import emit_node_status

            await emit_node_status(workflow_run_id, node_id, status, payload["data"])
        except Exception:
            return

    async def _emit_workflow_status(
        self,
        workflow_run_id: str,
        status: str,
        data: dict | None = None,
    ) -> None:
        event_type = f"workflow_{status}"
        payload = {"type": event_type, "data": data or {}}
        await self._publish_stream_event(workflow_run_id, event_type, payload)

        try:
            from routes.websocket_routes import emit_workflow_status

            await emit_workflow_status(workflow_run_id, status, payload["data"])
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
        if isinstance(state.get("runtime_plan"), dict):
            metadata["runtime_plan"] = state.get("runtime_plan")
        workflow_run.metadata = metadata

        await self._refresh_workflow_stats(workflow_run)
        await self.store.update_workflow_run(workflow_run)
        return workflow_run

    async def _refresh_workflow_stats(self, workflow_run: WorkflowRun) -> None:
        """刷新运行态统计，避免 Gate/失败态顶部摘要长期停留在 0。"""
        node_runs = await self.store.get_node_runs_by_workflow(workflow_run.id)

        workflow_run.total_node_runs = len(node_runs)
        workflow_run.total_llm_calls = sum(len(node.llm_calls) for node in node_runs)
        workflow_run.total_tokens = sum(
            call.total_tokens for node in node_runs for call in node.llm_calls
        )

        # 这里使用节点耗时之和，避免把 Gate 等待时间也计入运行耗时。
        workflow_run.total_duration_ms = sum(node.duration_ms or 0 for node in node_runs)
        metadata = dict(workflow_run.metadata or {})
        metadata["quality_metrics"] = await self._build_quality_metrics(workflow_run, node_runs)
        workflow_run.metadata = metadata

    async def _build_quality_metrics(
        self,
        workflow_run: WorkflowRun,
        node_runs: list[Any],
    ) -> dict[str, Any]:
        """汇总当前运行的质量、事实核查和模型调用指标。"""
        artifacts = await self.store.get_artifacts_by_workflow(workflow_run.id)
        latest_fact_report = max(
            (artifact for artifact in artifacts if artifact.type == ArtifactType.FACT_CHECK_REPORT),
            key=lambda artifact: artifact.created_at,
            default=None,
        )
        final_artifact = (
            await self.store.get_artifact(workflow_run.final_artifact_id)
            if workflow_run.final_artifact_id
            else None
        )

        quality_scores: list[float] = []
        revisions_requested = 0
        for artifact in artifacts:
            if artifact.type != ArtifactType.REFINEMENT_FEEDBACK:
                continue
            content = artifact.content if isinstance(artifact.content, dict) else {}
            feedback = content.get("feedback") if isinstance(content.get("feedback"), dict) else {}
            score = feedback.get("quality_score")
            if isinstance(score, int | float):
                quality_scores.append(float(score))
            if feedback.get("needs_revision") is True:
                revisions_requested += 1

        fact_check_metrics = (
            self._extract_fact_check_metrics(latest_fact_report.content)
            if latest_fact_report
            else None
        )
        llm_calls = [call for node in node_runs for call in node.llm_calls]
        total_latency_ms = sum(call.latency_ms for call in llm_calls)
        average_latency_ms = round(total_latency_ms / len(llm_calls)) if llm_calls else None

        return {
            "average_quality_score": (
                round(sum(quality_scores) / len(quality_scores), 2) if quality_scores else None
            ),
            "quality_score_count": len(quality_scores),
            "revisions_requested": revisions_requested,
            "fact_check": fact_check_metrics,
            "tokens": {
                "total": workflow_run.total_tokens,
                "llm_call_count": workflow_run.total_llm_calls,
            },
            "latency": {
                "total_node_duration_ms": workflow_run.total_duration_ms,
                "average_llm_latency_ms": average_latency_ms,
            },
            "final_artifact_id": workflow_run.final_artifact_id,
            "final_content_hash": getattr(final_artifact, "content_hash", None),
        }

    @staticmethod
    def _extract_fact_check_metrics(content: Any) -> dict[str, Any]:
        """从事实核查 Artifact 中提取稳定指标。"""
        try:
            report = FactCheckReport.model_validate(content)
        except Exception:
            return {}
        report.compute_stats()
        return {
            "total_claims": report.total_claims,
            "verified_count": report.verified_count,
            "unverified_count": report.unverified_count,
            "high_risk_count": report.high_risk_count,
        }

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
                    gate_metadata = self._get_gate_metadata(workflow_run)
                    questions = self._normalize_clarification_gate_questions(
                        gate_metadata.get("questions")
                    )
                    if not questions:
                        questions = self._normalize_clarification_gate_questions(
                            state.get("clarification_questions", [])
                        )
                    await self._emit_workflow_status(
                        workflow_run_id,
                        "gate_waiting",
                        {
                            "gate_type": "clarification",
                            "questions": questions,
                            "opened_at": gate_metadata.get("opened_at"),
                            "trigger_reason": gate_metadata.get("trigger_reason"),
                            "current_node": workflow_run.current_node,
                        },
                    )
                    break
                if public_status == "awaiting_outline_approval":
                    gate_metadata = self._get_gate_metadata(workflow_run)
                    outline = self._coerce_event_mapping(state.get("outline"))
                    questions = self._coerce_event_list(gate_metadata.get("questions"))
                    if not questions:
                        questions = self._build_outline_gate_questions(outline)
                    await self._emit_workflow_status(
                        workflow_run_id,
                        "gate_waiting",
                        {
                            "gate_type": "outline_approval",
                            "questions": questions,
                            "outline": outline,
                            "opened_at": gate_metadata.get("opened_at"),
                            "trigger_reason": gate_metadata.get("trigger_reason"),
                            "current_node": workflow_run.current_node,
                        },
                    )
                    break
                if public_status == "awaiting_fact_check_approval":
                    gate_metadata = self._get_gate_metadata(workflow_run)
                    report = self._coerce_event_mapping(state.get("fact_check_report"))
                    questions = self._coerce_event_list(gate_metadata.get("questions"))
                    if not questions:
                        questions = self._build_fact_check_gate_questions(report)
                    await self._emit_workflow_status(
                        workflow_run_id,
                        "gate_waiting",
                        {
                            "gate_type": "fact_check",
                            "questions": questions,
                            "fact_check_report": report,
                            "opened_at": gate_metadata.get("opened_at"),
                            "trigger_reason": gate_metadata.get("trigger_reason"),
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
        from services.llm_provider import get_workspace_runtime_model_config

        # 启动前先校验显式模型供应商，避免后台节点静默切换到其他模型。
        runtime_model_config = await get_workspace_runtime_model_config(
            workspace_id,
            model_name,
            model_provider_id,
        )
        metadata = {}
        if workspace_id:
            metadata["workspace_id"] = workspace_id
        if user_id:
            metadata["user_id"] = user_id
        if model_provider_id:
            metadata["requested_model_provider_id"] = model_provider_id
        if model_name:
            metadata["requested_model_name"] = model_name
        metadata["runtime_model"] = {
            "provider": runtime_model_config.provider,
            "model": runtime_model_config.model,
            "provider_id": runtime_model_config.provider_id,
            "provider_name": runtime_model_config.provider_name,
            "source": runtime_model_config.source,
            "structured_output_method": runtime_model_config.structured_output_method,
        }
        if runtime_model_config.provider_id:
            metadata["model_provider_id"] = runtime_model_config.provider_id
        if model_provider_id:
            metadata.setdefault("model_provider_id", model_provider_id)
        metadata["model_provider_name"] = runtime_model_config.provider
        metadata["model_name"] = runtime_model_config.model

        workflow_run = WorkflowRun(
            user_input=user_input,
            status=WorkflowRunStatus.RUNNING,
            workflow_definition_id=workflow_definition_id,
            workflow_version_id=workflow_version_id,
            metadata=metadata,
        )

        # 显式选择发布工作流时先做上下文校验，避免创建后才发现无法执行。
        workflow_context = await self._load_workflow_context(workflow_run)
        self._require_bound_workflow_context(workflow_run, workflow_context)
        if isinstance(workflow_context, dict):
            workflow_run.workflow_definition_id = (
                workflow_context.get("workflow_definition_id")
                or workflow_run.workflow_definition_id
            )
            workflow_run.workflow_version_id = (
                workflow_context.get("workflow_version_id") or workflow_run.workflow_version_id
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

        initial_state, updated_config = await self._prepare_rerun_target(
            workflow_run,
            from_node=from_node,
            preserved_state=preserved_state,
        )
        if updated_config is None:
            return await self._drive_workflow(
                workflow_run_id,
                initial_state=initial_state,
                emit_resumed=True,
            )
        return await self._drive_workflow(
            workflow_run_id,
            config=updated_config,
            emit_resumed=True,
        )

    async def start_rerun_from_node(
        self,
        workflow_run_id: str,
        *,
        from_node: str,
        preserved_state: dict,
    ) -> dict:
        """后台启动重跑，避免 HTTP 请求被节点执行时间阻塞。"""
        workflow_run = await self.store.get_workflow_run(workflow_run_id)
        if workflow_run is None:
            raise ValueError(f"WorkflowRun not found: {workflow_run_id}")

        initial_state, updated_config = await self._prepare_rerun_target(
            workflow_run,
            from_node=from_node,
            preserved_state=preserved_state,
        )

        # 先把目标节点写回运行态，详情页可立即进入轮询/SSE，而不是等待节点跑完。
        workflow_run.current_node = from_node
        metadata = dict(workflow_run.metadata or {})
        metadata["last_public_status"] = "running"
        metadata.pop("error", None)
        workflow_run.metadata = metadata
        await self.store.update_workflow_run(workflow_run)

        if updated_config is None:
            self._schedule_drive(
                workflow_run_id,
                initial_state=initial_state,
            )
        else:
            self._schedule_drive(
                workflow_run_id,
                config=updated_config,
            )

        return {
            "workflow_run_id": workflow_run_id,
            "state": {**initial_state, "current_node": from_node},
            "status": "running",
        }

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

    async def _prepare_rerun_target(
        self,
        workflow_run: WorkflowRun,
        *,
        from_node: str,
        preserved_state: dict,
    ) -> tuple[dict, dict | None]:
        """统一构建重跑入口状态，供同步 rerun 和后台 rerun 复用。"""
        initial_state = await self._build_initial_state(
            workflow_run,
            {
                **preserved_state,
                "rerun_from_node": from_node,
            },
        )

        if from_node == "parse_intent":
            return initial_state, None

        planned_steps = [
            step.get("id")
            for step in (initial_state.get("runtime_plan") or {}).get("steps", [])
            if isinstance(step, dict) and step.get("id")
        ]
        predecessor_by_node = {
            node_id: planned_steps[index - 1]
            for index, node_id in enumerate(planned_steps)
            if index > 0
        }
        predecessor_by_node.setdefault("clarify_intent", "parse_intent")
        predecessor = predecessor_by_node.get(from_node)
        if predecessor is None:
            raise ValueError(f"Unsupported rerun node for this workflow runtime plan: {from_node}")

        updated_config = await self.graph.aupdate_state(
            self._base_config(workflow_run.id),
            initial_state,
            as_node=predecessor,
        )
        return initial_state, updated_config

    async def pause(self, workflow_run_id: str, reason: str = "") -> dict:
        """请求手动暂停，当前节点完成后停在下一份 checkpoint。"""
        workflow_run = await self.store.get_workflow_run(workflow_run_id)
        if workflow_run is None:
            raise ValueError(f"WorkflowRun not found: {workflow_run_id}")

        workflow_run.status = WorkflowRunStatus.PAUSED
        metadata = dict(workflow_run.metadata or {})
        previous_pause = metadata.get("pause") if isinstance(metadata.get("pause"), dict) else {}
        paused_at = previous_pause.get("paused_at")
        if paused_at is None or previous_pause.get("resumed_at") is not None:
            paused_at = utc_now_iso()
        metadata["pause"] = {
            "reason": reason,
            "paused_at": paused_at,
            "resumed_at": None,
            "source": previous_pause.get("source") or "user",
        }
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
        previous_pause = metadata.get("pause") if isinstance(metadata.get("pause"), dict) else {}
        metadata["pause"] = {
            "reason": previous_pause.get("reason"),
            "paused_at": previous_pause.get("paused_at") or utc_now_iso(),
            "resumed_at": utc_now_iso(),
            "source": previous_pause.get("source") or "user",
        }
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
