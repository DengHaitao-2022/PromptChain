"""Autonomous Agent Runtime 编排服务。"""

from __future__ import annotations

from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from core.config import get_settings
from core.time import utc_now_naive
from models.artifact import ArtifactType, NodeRun, NodeRunStatus, WorkflowRun, WorkflowRunStatus
from models.autonomous_agent import (
    AgentPlan,
    AgentPlanStatus,
    AgentRun,
    AgentRunStatus,
    AgentStep,
    AgentStepStatus,
    AgentStepType,
    MemoryType,
    PlanGraph,
    PlanNode,
    ReplanRecord,
    ToolCallStatus,
)
from services.artifact_store import ArtifactStore
from services.autonomous_agent_evaluation import AgentEvaluator, AgentReflector, MemoryManager
from services.autonomous_agent_planner import AutonomousPlanner
from services.autonomous_agent_store import AutonomousAgentStore
from services.autonomous_agent_tools import ToolExecutor, build_default_tool_registry
from services.llm_provider import get_current_model_info_for_workspace, get_llm_for_workspace
from services.llm_retry import invoke_with_llm_retry
from services.llm_usage import ensure_usage_metadata, extract_usage_metadata

AGENT_GENERATION_PROMPT = """你是 PromptChain 的 Autonomous Agent Generation 节点。

请基于目标卡、动态计划图、上下文窗口和已收集证据生成可交付内容。

## 用户目标
{goal}

## GoalCard
{goal_card}

## 动态计划图
{plan_graph}

## 当前上下文窗口
{context_window}

## 节点验收标准
{acceptance_criteria}

## 生成要求
1. 直接生成完整主体内容，不要只复述计划。
2. 内容必须覆盖 GoalCard 中的 deliverables、constraints、success_criteria。
3. 若上下文或证据不足，明确标注“不确定/证据不足”，不要编造事实。
4. 使用清晰标题和分节结构，适合后续 fact_check、evaluate 和 finalize 复用。
5. 默认使用中文输出。
"""


class AutonomousAgentRuntime:
    """执行 Plan-Act-Observe-Evaluate-Reflect-Replan 循环。"""

    def __init__(
        self,
        *,
        store: AutonomousAgentStore,
        artifact_store: ArtifactStore,
        planner: AutonomousPlanner | None = None,
        evaluator: AgentEvaluator | None = None,
        reflector: AgentReflector | None = None,
    ):
        self.store = store
        self.artifact_store = artifact_store
        self.planner = planner or AutonomousPlanner()
        self.evaluator = evaluator or AgentEvaluator()
        self.reflector = reflector or AgentReflector()
        self.memory = MemoryManager(store)
        registry = build_default_tool_registry(
            artifact_store=artifact_store,
            agent_store=store,
        )
        self.tool_executor = ToolExecutor(registry=registry, store=store)

    async def start(
        self,
        *,
        goal: str,
        user_id: str,
        workspace_id: str,
        autonomy_level: str = "supervised",
        budget_limit: dict[str, Any] | None = None,
        auto_execute: bool = True,
        allowed_tool_permissions: list[str] | None = None,
        planner_mode: str | None = None,
        generation_mode: str | None = None,
        fact_check_mode: str | None = None,
        inline_execute: bool = True,
        model_provider_id: str | None = None,
        model_provider_name: str | None = None,
        model_name: str | None = None,
    ) -> AgentRun:
        """创建 AgentRun，并按调用方选择同步执行或交给后台 worker。"""
        metadata: dict[str, Any] = {
            "auto_execute": auto_execute,
            **(
                {"allowed_tool_permissions": allowed_tool_permissions}
                if allowed_tool_permissions is not None
                else {}
            ),
        }
        for key, value in {
            "planner_mode": planner_mode,
            "generation_mode": generation_mode,
            "fact_check_mode": fact_check_mode,
            "model_provider_id": model_provider_id,
            "model_provider_name": model_provider_name,
            "model_name": model_name,
        }.items():
            if value:
                metadata[key] = value
        run = AgentRun(
            user_id=user_id,
            workspace_id=workspace_id,
            goal=goal,
            autonomy_level=autonomy_level,
            budget_limit=budget_limit or {"max_steps": 14, "max_replans": 2},
            metadata=metadata,
        )
        await self.store.create_run(run)
        await self.artifact_store.create_workflow_run(
            WorkflowRun(
                id=run.id,
                workflow_name="autonomous_agent",
                workflow_version="1.0.0",
                user_input=goal,
                current_node="goal_interpretation",
                metadata={
                    "runtime_type": "autonomous_agent",
                    "agent_run_id": run.id,
                    "user_id": user_id,
                    "workspace_id": workspace_id,
                    "autonomy_level": autonomy_level,
                },
            )
        )

        try:
            memories = await self.memory.retrieve(workspace_id, goal)
            memory_payload = [memory.model_dump(mode="json") for memory in memories]
            plan = await self.planner.create_initial_plan(
                run,
                memory_payload,
                tool_definitions=self._tool_definitions_payload(),
            )
        except ValueError as exc:
            run.status = AgentRunStatus.AWAITING_GATE
            run.gate = self._planner_clarification_gate(str(exc))
            run.error_message = str(exc)
            run.updated_at = utc_now_naive()
            await self.store.update_run(run)
            await self._sync_workflow_run(run)
            return run
        plan_artifact_id = await self._record_plan_artifact(run, plan)
        plan.metadata["artifact_id"] = plan_artifact_id
        await self.store.create_plan(plan)
        run.current_plan_id = plan.id
        run.status = AgentRunStatus.RUNNING if auto_execute else AgentRunStatus.PLANNING
        run.metadata["goal_card"] = plan.goal_card.model_dump(mode="json")
        run.metadata["plan_version"] = plan.version
        run.updated_at = utc_now_naive()
        await self.store.update_run(run)
        await self._sync_workflow_run(run)

        if auto_execute:
            if inline_execute:
                run = await self.execute_until_stop(run.id)
            else:
                run.metadata["queued_at"] = utc_now_naive().isoformat()
                await self.store.update_run(run)
                run = await self.store.enqueue_run(run.id) or run
                await self._sync_workflow_run(run)
        return run

    async def clarify_goal(
        self,
        run_id: str,
        clarification: str,
        *,
        inline_execute: bool = True,
    ) -> AgentRun:
        """补充 Planner 所需目标信息，并重新进入规划/执行流程。"""
        run = await self._require_run(run_id)
        if run.status != AgentRunStatus.AWAITING_GATE:
            raise ValueError("当前 AgentRun 不处于 Planner 澄清状态")
        gate_type = (run.gate or {}).get("gate_type")
        if gate_type != "planner_clarification":
            raise ValueError("当前 Gate 不是目标澄清 Gate")
        if not clarification.strip():
            raise ValueError("补充目标不能为空")

        run.goal = f"{run.goal}\n\n补充说明：{clarification.strip()}".strip()
        run.gate = None
        run.error_message = None
        run.status = AgentRunStatus.PLANNING
        run.updated_at = utc_now_naive()
        await self.store.update_run(run)
        await self._sync_workflow_run(run)

        memories = await self.memory.retrieve(run.workspace_id, run.goal)
        plan = await self.planner.create_initial_plan(
            run,
            [memory.model_dump(mode="json") for memory in memories],
            tool_definitions=self._tool_definitions_payload(),
        )
        plan_artifact_id = await self._record_plan_artifact(run, plan)
        plan.metadata["artifact_id"] = plan_artifact_id
        await self.store.create_plan(plan)

        run.current_plan_id = plan.id
        run.status = (
            AgentRunStatus.RUNNING
            if run.metadata.get("auto_execute", True)
            else AgentRunStatus.PLANNING
        )
        run.metadata["goal_card"] = plan.goal_card.model_dump(mode="json")
        run.metadata["plan_version"] = plan.version
        run.updated_at = utc_now_naive()
        await self.store.update_run(run)
        await self._sync_workflow_run(run)

        if run.metadata.get("auto_execute", True):
            if inline_execute:
                return await self.execute_until_stop(run.id)
            run.metadata["queued_at"] = utc_now_naive().isoformat()
            await self.store.update_run(run)
            run = await self.store.enqueue_run(run.id) or run
            await self._sync_workflow_run(run)
        return run

    async def prepare_for_worker(
        self,
        run_id: str,
        *,
        reason: str = "queued",
        run: AgentRun | None = None,
    ) -> AgentRun:
        """把可继续执行的运行标记为后台 worker 待执行。"""
        run = run or await self._require_run(run_id)
        if run.status in {
            AgentRunStatus.COMPLETED,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        }:
            raise ValueError("当前 AgentRun 已结束，无法继续执行")
        if run.status == AgentRunStatus.AWAITING_GATE:
            raise ValueError("当前 AgentRun 正在等待 Gate 审批")
        if run.status == AgentRunStatus.PAUSED:
            run.metadata["resumed_at"] = utc_now_naive().isoformat()
        run.status = AgentRunStatus.RUNNING
        run.metadata["queued_at"] = utc_now_naive().isoformat()
        run.metadata["queue_reason"] = reason
        run.updated_at = utc_now_naive()
        await self.store.update_run(run)
        run = await self.store.enqueue_run(run.id) or run
        await self._sync_workflow_run(run)
        return run

    def _planner_clarification_gate(self, reason: str) -> dict[str, Any]:
        """生成 Planner 失败时的人机澄清 Gate。"""
        return {
            "gate_type": "planner_clarification",
            "reason": reason,
            "questions": [
                {
                    "field": "goal",
                    "question": "请补充任务目标、交付物、受众或质量标准后继续规划。",
                    "priority": "high",
                }
            ],
            "opened_at": utc_now_naive().isoformat(),
        }

    def _tool_definitions_payload(self) -> list[dict[str, Any]]:
        """把 Tool Registry 暴露给 Planner，确保 LLM 只能选择已注册工具。"""
        return [
            tool.model_dump(mode="json") for tool in self.tool_executor.registry.list_definitions()
        ]

    async def replace_plan(
        self,
        run_id: str,
        *,
        plan_graph_payload: dict[str, Any],
        reason: str = "human_plan_edit",
    ) -> AgentRun:
        """人工修改规划中的 Plan Graph，生成新的计划版本。"""
        run = await self._require_run(run_id)
        if run.status != AgentRunStatus.PLANNING:
            raise ValueError("只有 planning 状态的 AgentRun 可以修改计划")
        if not run.current_plan_id:
            raise ValueError("AgentRun 缺少 current_plan_id")

        previous_plan = await self._require_plan(run.current_plan_id)
        plan_graph = PlanGraph(**plan_graph_payload)
        if not plan_graph.nodes:
            raise ValueError("PlanGraph 至少需要包含一个节点")

        await self.store.update_plan_status(previous_plan.id, AgentPlanStatus.SUPERSEDED)
        next_version = await self.store.next_plan_version(run.id)
        new_plan = AgentPlan(
            run_id=run.id,
            version=next_version,
            status=AgentPlanStatus.ACTIVE,
            plan_graph=plan_graph,
            goal_card=previous_plan.goal_card,
            created_by="human",
            reason=reason or "human_plan_edit",
            metadata={
                "edited_from_plan_id": previous_plan.id,
                "selected_template": "human_edited",
            },
        )
        plan_artifact_id = await self._record_plan_artifact(run, new_plan)
        new_plan.metadata["artifact_id"] = plan_artifact_id
        await self.store.create_plan(new_plan)

        run.current_plan_id = new_plan.id
        run.metadata["plan_version"] = new_plan.version
        run.updated_at = utc_now_naive()
        await self.store.update_run(run)
        await self._sync_workflow_run(run)
        return run

    async def _record_plan_artifact(self, run: AgentRun, plan: AgentPlan) -> str:
        """将 Planner 输出写入版本化 Artifact，并纳入现有 Trace 回放链路。"""
        planner_node_run = NodeRun(
            workflow_run_id=run.id,
            node_name="agent_planner",
            node_type="agent_planning",
            status=NodeRunStatus.RUNNING,
            input_artifact_ids=[],
        )
        await self.artifact_store.create_node_run(planner_node_run)
        artifact = await self.artifact_store.create_artifact(
            artifact_type=ArtifactType.AGENT_PLAN,
            content={
                "goal_card": plan.goal_card.model_dump(mode="json"),
                "plan_graph": plan.plan_graph.model_dump(mode="json"),
                "reason": plan.reason,
                "version": plan.version,
            },
            workflow_run_id=run.id,
            node_run_id=planner_node_run.id,
            metadata={
                "source": "autonomous_agent_planner",
                "agent_run_id": run.id,
                "agent_plan_id": plan.id,
            },
        )
        planner_node_run.output_artifact_ids.append(artifact.id)
        planner_node_run.complete(NodeRunStatus.COMPLETED)
        await self.artifact_store.update_node_run(planner_node_run)
        return artifact.id

    async def execute_until_stop(self, run_id: str) -> AgentRun:
        """持续执行直到完成、失败或 Gate 等待。"""
        run = await self._require_run(run_id)
        if run.status == AgentRunStatus.PAUSED:
            await self._sync_workflow_run(run)
            # 暂停只能由 resume/prepare_for_worker 显式恢复，避免 worker 绕过人工暂停。
            return run
        if not run.current_plan_id:
            raise ValueError("AgentRun 缺少 current_plan_id")

        plan = await self._require_plan(run.current_plan_id)
        max_steps = int(run.budget_limit.get("max_steps") or plan.plan_graph.max_steps)
        max_replans = int(run.budget_limit.get("max_replans") or plan.plan_graph.max_replans)
        executed_steps = len(await self.store.list_steps(run.id))

        while executed_steps < max_steps:
            run = await self._require_run(run.id)
            budget_error = await self._budget_violation(run)
            if budget_error:
                return await self._fail_run(run, budget_error)
            if run.status == AgentRunStatus.PAUSED:
                await self._sync_workflow_run(run)
                return run
            if run.status == AgentRunStatus.CANCELLED:
                await self._sync_workflow_run(run)
                return run

            next_node = await self._select_next_node(run, plan)
            if next_node is None:
                return await self._finalize_run(run, plan)

            step = await self._execute_node(run, plan, next_node)
            executed_steps += 1
            # 节点执行可能较久，期间 pause/cancel 会更新持久态；这里必须重读，避免旧 run 覆盖控制面状态。
            run = await self._require_run(run.id)
            run.current_step_id = step.id
            run.metadata["current_node_id"] = step.node_id
            run.metadata["executed_step_count"] = executed_steps
            run.updated_at = utc_now_naive()
            await self.store.update_run(run)
            await self._sync_workflow_run(run)
            if run.status in {AgentRunStatus.PAUSED, AgentRunStatus.CANCELLED}:
                return run

            if step.status == AgentStepStatus.BLOCKED:
                run.status = AgentRunStatus.AWAITING_GATE
                run.gate = step.output.get("gate")
                run.updated_at = utc_now_naive()
                await self.store.update_run(run)
                await self._sync_workflow_run(run)
                return run

            eval_result = self.evaluator.evaluate_step(run, step)
            await self.store.create_eval_result(eval_result)
            if not eval_result.passed:
                if await self._can_replan(run.id, max_replans):
                    reflection = self.reflector.reflect(
                        run=run,
                        step=step,
                        eval_result=eval_result,
                    )
                    plan = await self._replan(run, plan, step, reflection)
                    run.current_plan_id = plan.id
                    run.metadata["plan_version"] = plan.version
                    run.updated_at = utc_now_naive()
                    await self.store.update_run(run)
                    await self._sync_workflow_run(run)
                    continue

                run.status = AgentRunStatus.FAILED
                run.error_message = f"步骤 {step.title} 未通过评估且已达到重规划上限"
                run.updated_at = utc_now_naive()
                run.completed_at = utc_now_naive()
                await self.store.update_run(run)
                await self._sync_workflow_run(run)
                return run

        return await self._fail_run(run, "达到最大步骤数，任务未完成")

    async def pause_run(self, run_id: str, reason: str = "") -> AgentRun:
        """人工暂停长程 AgentRun，保留后续恢复所需状态。"""
        run = await self._require_run(run_id)
        if run.status in {
            AgentRunStatus.COMPLETED,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        }:
            raise ValueError("当前 AgentRun 已结束，无法暂停")
        if run.status == AgentRunStatus.AWAITING_GATE:
            raise ValueError("当前 AgentRun 正在等待 Gate 审批，不能改为普通暂停")
        run.status = AgentRunStatus.PAUSED
        run.queue_status = "idle"
        run.worker_id = None
        run.lease_token = None
        run.lease_expires_at = None
        run.metadata["pause"] = {
            "reason": reason or "人工暂停",
            "paused_at": utc_now_naive().isoformat(),
        }
        run.updated_at = utc_now_naive()
        await self.store.update_run(run)
        await self._sync_workflow_run(run)
        return run

    async def cancel_run(self, run_id: str, reason: str = "") -> AgentRun:
        """取消未完成 AgentRun，作为高风险或目标废弃时的显式收口。"""
        run = await self._require_run(run_id)
        if run.status in {
            AgentRunStatus.COMPLETED,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        }:
            raise ValueError("当前 AgentRun 已结束，无法取消")
        run.status = AgentRunStatus.CANCELLED
        run.error_message = reason or "用户取消 Autonomous Agent 运行"
        run.queue_status = "terminal"
        run.metadata["cancelled_at"] = utc_now_naive().isoformat()
        run.updated_at = utc_now_naive()
        run.completed_at = utc_now_naive()
        await self.store.update_run(run)
        await self._sync_workflow_run(run)
        return run

    async def skip_node(self, run_id: str, node_id: str, reason: str = "") -> AgentStep:
        """人工跳过未执行节点，使动态 Plan Graph 可在运行中裁剪。"""
        run = await self._require_run(run_id)
        if run.status in {
            AgentRunStatus.COMPLETED,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
            AgentRunStatus.AWAITING_GATE,
        }:
            raise ValueError("当前 AgentRun 状态不允许跳过节点")
        if not run.current_plan_id:
            raise ValueError("AgentRun 缺少 current_plan_id")

        plan = await self._require_plan(run.current_plan_id)
        node = next((item for item in plan.plan_graph.nodes if item.id == node_id), None)
        if not node:
            raise ValueError("指定节点不属于当前计划")

        existing_steps = await self.store.list_steps(run.id)
        existing_step = next(
            (
                step
                for step in existing_steps
                if step.plan_id == plan.id
                and step.node_id == node_id
                and step.status
                in {
                    AgentStepStatus.COMPLETED,
                    AgentStepStatus.RUNNING,
                    AgentStepStatus.BLOCKED,
                    AgentStepStatus.SKIPPED,
                }
            ),
            None,
        )
        if existing_step:
            raise ValueError("该节点已有执行记录，不能重复跳过")

        now = utc_now_naive()
        step = AgentStep(
            run_id=run.id,
            plan_id=plan.id,
            node_id=node.id,
            step_type=node.step_type,
            title=node.title,
            description=node.description,
            status=AgentStepStatus.SKIPPED,
            input={
                "node": node.model_dump(mode="json"),
                "goal": run.goal,
                "skip_reason": reason or "人工跳过",
            },
            output={"skipped": True, "reason": reason or "人工跳过"},
            started_at=now,
            ended_at=now,
            metadata={"skip_reason": reason or "人工跳过"},
        )
        await self.store.create_step(step)
        node_run = NodeRun(
            id=step.id,
            workflow_run_id=run.id,
            node_name=node.id,
            node_type=f"agent_{node.step_type.value}",
            status=NodeRunStatus.INTERRUPTED,
            input_artifact_ids=[],
            completed_at=now,
            duration_ms=0,
            error_message=reason or "人工跳过",
        )
        await self.artifact_store.create_node_run(node_run)

        run.current_step_id = step.id
        run.metadata["current_node_id"] = step.node_id
        run.metadata["last_skipped_node"] = {
            "node_id": node_id,
            "reason": reason or "人工跳过",
            "skipped_at": now.isoformat(),
        }
        run.updated_at = utc_now_naive()
        await self.store.update_run(run)
        await self._sync_workflow_run(run)
        return step

    async def approve_gate(
        self,
        run_id: str,
        approved: bool,
        note: str = "",
        *,
        inline_execute: bool = True,
    ) -> AgentRun:
        """审批 Gate 后继续或终止运行。"""
        run = await self._require_run(run_id)
        if run.status != AgentRunStatus.AWAITING_GATE:
            raise ValueError("当前 AgentRun 不处于 Gate 等待状态")
        gate = run.gate or {}
        gate["approved"] = approved
        gate["handled_note"] = note
        gate["handled_at"] = utc_now_naive().isoformat()
        run.gate = gate
        if not approved:
            run.status = AgentRunStatus.CANCELLED
            run.error_message = note or "高风险工具调用被拒绝"
            run.completed_at = utc_now_naive()
            run.updated_at = utc_now_naive()
            await self.store.update_run(run)
            await self._sync_workflow_run(run)
            return run

        await self._complete_approved_gate(run)
        run.metadata["last_gate_decision"] = gate
        run.status = AgentRunStatus.RUNNING
        run.gate = None
        run.updated_at = utc_now_naive()
        await self.store.update_run(run)
        await self._sync_workflow_run(run)
        if not inline_execute:
            run.metadata["queued_at"] = utc_now_naive().isoformat()
            await self.store.update_run(run)
            run = await self.store.enqueue_run(run.id) or run
            await self._sync_workflow_run(run)
            return run
        return await self.execute_until_stop(run.id)

    async def get_detail(self, run_id: str) -> dict[str, Any]:
        """返回前端详情页可直接消费的完整运行快照。"""
        run = await self._require_run(run_id)
        plans = await self.store.list_plans(run_id)
        steps = await self.store.list_steps(run_id)
        tool_calls = await self.store.list_tool_calls(run_id)
        eval_results = await self.store.list_eval_results(run_id)
        replans = await self.store.list_replan_records(run_id)
        memories = await self.store.list_memories(run.workspace_id, limit=20)
        return {
            "run": run.model_dump(mode="json"),
            "plans": [plan.model_dump(mode="json") for plan in plans],
            "steps": [step.model_dump(mode="json") for step in steps],
            "tool_calls": [tool_call.model_dump(mode="json") for tool_call in tool_calls],
            "eval_results": [result.model_dump(mode="json") for result in eval_results],
            "replan_records": [record.model_dump(mode="json") for record in replans],
            "memories": [
                memory.model_dump(mode="json")
                for memory in memories
                if memory.run_id in {None, run_id}
            ],
            "tool_definitions": [
                definition.model_dump(mode="json")
                for definition in self.tool_executor.registry.list_definitions()
            ],
        }

    async def _execute_node(
        self,
        run: AgentRun,
        plan: AgentPlan,
        node: PlanNode,
    ) -> AgentStep:
        step = AgentStep(
            run_id=run.id,
            plan_id=plan.id,
            node_id=node.id,
            step_type=node.step_type,
            title=node.title,
            description=node.description,
            status=AgentStepStatus.RUNNING,
            input={
                "node": node.model_dump(mode="json"),
                "goal": run.goal,
                "goal_card": plan.goal_card.model_dump(mode="json"),
            },
            started_at=utc_now_naive(),
        )
        await self.store.create_step(step)
        await self.artifact_store.create_node_run(
            NodeRun(
                id=step.id,
                workflow_run_id=run.id,
                node_name=node.id,
                node_type=f"agent_{node.step_type.value}",
                status=NodeRunStatus.RUNNING,
                input_artifact_ids=[],
            )
        )

        try:
            output = await self._dispatch_node(run, plan, node, step)
            step.output = output
            step.status = (
                AgentStepStatus.BLOCKED if output.get("gate") else AgentStepStatus.COMPLETED
            )
            if artifact_id := output.get("artifact_id"):
                step.artifact_ids.append(str(artifact_id))
        except Exception as exc:
            retry_limit = int(run.budget_limit.get("max_retries") or 0)
            retry_count = int(step.metadata.get("retry_count") or 0)
            while retry_count < retry_limit:
                retry_count += 1
                step.metadata["retry_count"] = retry_count
                try:
                    output = await self._dispatch_node(run, plan, node, step)
                    step.output = output
                    step.error_message = None
                    step.status = (
                        AgentStepStatus.BLOCKED if output.get("gate") else AgentStepStatus.COMPLETED
                    )
                    if artifact_id := output.get("artifact_id"):
                        step.artifact_ids.append(str(artifact_id))
                    break
                except Exception as retry_exc:
                    step.error_message = str(retry_exc)
                    step.output = {
                        "error": str(retry_exc),
                        "retry_count": retry_count,
                    }
            else:
                step.status = AgentStepStatus.FAILED
                step.error_message = str(exc) if not step.error_message else step.error_message
                step.output = step.output or {"error": step.error_message}
        finally:
            step.ended_at = utc_now_naive()
            await self.store.update_step(step)
            await self._sync_node_run(step)
        return step

    async def _dispatch_node(
        self,
        run: AgentRun,
        plan: AgentPlan,
        node: PlanNode,
        step: AgentStep,
    ) -> dict[str, Any]:
        if node.step_type == AgentStepType.GOAL_INTERPRETATION:
            return {"goal_card": plan.goal_card.model_dump(mode="json")}
        if node.step_type == AgentStepType.MEMORY_RETRIEVAL:
            tool_call = await self.tool_executor.execute(
                run_id=run.id,
                tool_name="retrieve_memory",
                payload={
                    "workspace_id": run.workspace_id,
                    "user_id": run.user_id,
                    "workflow_run_id": run.id,
                    "node_run_id": step.id,
                    "query": run.goal,
                },
                step=step,
                allowed_permissions=self._allowed_tool_permissions(run),
            )
            self._raise_failed_tool_call(tool_call)
            return {"tool_call_id": tool_call.id, **tool_call.output}
        if node.step_type == AgentStepType.PLANNING:
            return {"plan_graph": plan.plan_graph.model_dump(mode="json")}
        if node.step_type == AgentStepType.TOOL_CALL and node.tool_name:
            payload = {
                **node.input,
                "workspace_id": run.workspace_id,
                "user_id": run.user_id,
                "workflow_run_id": run.id,
                "goal": run.goal,
                "model_provider_id": self._metadata_str(run, "model_provider_id"),
                "model_provider_name": self._metadata_str(run, "model_provider_name"),
                "model_name": self._metadata_str(run, "model_name"),
            }
            if node.tool_name == "fact_check" and "text" not in payload:
                payload["text"] = await self._latest_step_text(run.id)
            if node.tool_name == "fact_check":
                run_fact_check_mode = self._fact_check_mode(run)
                if not payload.get("mode") or run_fact_check_mode != "auto":
                    payload["mode"] = run_fact_check_mode
                payload.setdefault(
                    "evidence_context",
                    await self._fact_check_evidence_context(run.id),
                )
            tool_call = await self.tool_executor.execute(
                run_id=run.id,
                tool_name=node.tool_name,
                payload=payload,
                step=step,
                allowed_permissions=self._allowed_tool_permissions(run),
            )
            self._raise_failed_tool_call(tool_call)
            return self._tool_output(tool_call)
        if node.step_type == AgentStepType.GENERATION:
            context_window = await self.memory.build_context_window(run=run)
            content = await self._build_generation_payload(run, plan, node, context_window)
            tool_call = await self.tool_executor.execute(
                run_id=run.id,
                tool_name=node.tool_name or "write_artifact",
                payload={
                    "content": content,
                    "metadata": {
                        "agent_node_id": node.id,
                        "deliverables": plan.goal_card.deliverables,
                    },
                },
                step=step,
                allowed_permissions=self._allowed_tool_permissions(run),
            )
            self._raise_failed_tool_call(tool_call)
            output = self._tool_output(tool_call)
            if artifact := output.get("artifact"):
                output["artifact_id"] = artifact.get("id")
            return output
        if node.step_type == AgentStepType.EVALUATION:
            return {"evaluation_focus": plan.goal_card.quality_dimensions}
        if node.step_type == AgentStepType.REFLECTION:
            return {"decision": "continue_to_finalize", "reason": "当前计划执行可进入最终收口"}
        if node.step_type == AgentStepType.FINALIZATION:
            final_payload = await self._build_final_payload(run, plan)
            tool_call = await self.tool_executor.execute(
                run_id=run.id,
                tool_name=node.tool_name or "write_artifact",
                payload={
                    "content": final_payload,
                    "metadata": {"agent_node_id": node.id, "final": True},
                },
                step=step,
                allowed_permissions=self._allowed_tool_permissions(run),
            )
            self._raise_failed_tool_call(tool_call)
            output = self._tool_output(tool_call)
            if artifact := output.get("artifact"):
                output["artifact_id"] = artifact.get("id")
            return output
        return {"message": "步骤已记录，未定义专用执行器"}

    def _tool_output(self, tool_call) -> dict[str, Any]:
        if tool_call.status == ToolCallStatus.AWAITING_GATE:
            return {
                "gate": {
                    "gate_type": "tool_risk_approval",
                    "tool_call_id": tool_call.id,
                    "tool_name": tool_call.tool_name,
                    "risk_level": tool_call.risk_level.value,
                    "reason": tool_call.output.get("reason"),
                },
                "tool_call_id": tool_call.id,
            }
        return {"tool_call_id": tool_call.id, **tool_call.output}

    def _raise_failed_tool_call(self, tool_call) -> None:
        """将工具失败显式转为步骤失败，避免错误输出被误判为成功。"""
        if tool_call.status == ToolCallStatus.FAILED:
            raise ValueError(tool_call.error_message or f"工具 {tool_call.tool_name} 调用失败")

    async def _select_next_node(self, run: AgentRun, plan: AgentPlan) -> PlanNode | None:
        steps = await self.store.list_steps(run.id)
        replans = await self.store.list_replan_records(run.id)
        replanned_step_ids = {record.failed_step_id for record in replans if record.failed_step_id}
        replanned_node_ids = {
            step.node_id
            for step in steps
            if step.id in replanned_step_ids and step.status == AgentStepStatus.FAILED
        }
        completed_node_ids = {
            step.node_id for step in steps if step.status == AgentStepStatus.COMPLETED
        }
        skipped_node_ids = {
            step.node_id for step in steps if step.status == AgentStepStatus.SKIPPED
        }
        resolved_node_ids = completed_node_ids | replanned_node_ids | skipped_node_ids
        blocked_node_ids = {
            step.node_id
            for step in steps
            if step.plan_id == plan.id and step.status == AgentStepStatus.BLOCKED
        }
        if blocked_node_ids:
            return None
        for node in plan.plan_graph.nodes:
            if node.id in resolved_node_ids:
                continue
            if all(dep in resolved_node_ids for dep in node.depends_on):
                return node
        return None

    async def _finalize_run(self, run: AgentRun, plan: AgentPlan) -> AgentRun:
        steps = await self.store.list_steps(run.id)
        eval_results = await self.store.list_eval_results(run.id)
        replans = await self.store.list_replan_records(run.id)
        replanned_step_ids = {record.failed_step_id for record in replans if record.failed_step_id}
        # 已触发重规划的失败步骤视为被新计划取代，避免旧失败永久阻塞最终验收。
        effective_eval_results = [
            result for result in eval_results if result.step_id not in replanned_step_ids
        ]
        final_eval = self.evaluator.evaluate_final_output(run, steps, effective_eval_results)
        await self.store.create_eval_result(final_eval)
        final_artifact_id = self._latest_artifact_id(steps)

        run.status = AgentRunStatus.COMPLETED if final_eval.passed else AgentRunStatus.FAILED
        run.final_artifact_id = final_artifact_id
        run.error_message = None if final_eval.passed else "最终评估未通过"
        run.queue_status = "terminal"
        run.completed_at = utc_now_naive()
        run.updated_at = utc_now_naive()
        run.metadata["final_eval"] = final_eval.model_dump(mode="json")
        await self.store.update_run(run)
        await self._sync_workflow_run(run)
        await self.store.update_plan_status(
            plan.id,
            AgentPlanStatus.COMPLETED if final_eval.passed else AgentPlanStatus.FAILED,
        )
        await self.memory.remember_run_lesson(
            run=run,
            content=(
                f"目标：{run.goal}\n状态：{run.status.value}\n"
                f"最终评分：{final_eval.score}\n产物：{final_artifact_id or '无'}"
            ),
            memory_type=MemoryType.EPISODIC,
            confidence=0.85 if final_eval.passed else 0.65,
        )
        return run

    async def _complete_approved_gate(self, run: AgentRun) -> None:
        """执行 Gate 已批准的工具调用，并把阻塞步骤推进到终态。"""
        gate = run.gate or {}
        tool_call_id = gate.get("tool_call_id")
        if not tool_call_id:
            return

        tool_call = await self.store.get_tool_call(str(tool_call_id))
        if not tool_call:
            raise ValueError("Gate 关联的工具调用不存在")

        tool_call.metadata = {
            **(tool_call.metadata or {}),
            "gate_decision": gate,
        }
        step = await self.store.get_step(tool_call.step_id) if tool_call.step_id else None
        completed_call = await self.tool_executor.approve_and_execute(
            tool_call=tool_call,
            step=step,
            allowed_permissions=self._allowed_tool_permissions(run),
        )
        if not step:
            return

        step.output = self._tool_output(completed_call)
        step.status = (
            AgentStepStatus.COMPLETED
            if completed_call.status == ToolCallStatus.COMPLETED
            else AgentStepStatus.FAILED
        )
        step.error_message = completed_call.error_message
        if artifact := step.output.get("artifact"):
            step.output["artifact_id"] = artifact.get("id")
        if artifact_id := step.output.get("artifact_id"):
            artifact_id = str(artifact_id)
            if artifact_id not in step.artifact_ids:
                step.artifact_ids.append(artifact_id)
        step.ended_at = utc_now_naive()
        await self.store.update_step(step)
        await self._sync_node_run(step)

    async def _sync_workflow_run(self, run: AgentRun) -> None:
        """同步 AgentRun 到现有 WorkflowRun，复用 Trace/Artifact 回放能力。"""
        workflow_run = await self.artifact_store.get_workflow_run(run.id)
        if not workflow_run:
            return
        status_map = {
            AgentRunStatus.COMPLETED: WorkflowRunStatus.COMPLETED,
            AgentRunStatus.FAILED: WorkflowRunStatus.FAILED,
            AgentRunStatus.CANCELLED: WorkflowRunStatus.FAILED,
            AgentRunStatus.AWAITING_GATE: WorkflowRunStatus.PAUSED,
            AgentRunStatus.PAUSED: WorkflowRunStatus.PAUSED,
        }
        workflow_run.status = status_map.get(run.status, WorkflowRunStatus.RUNNING)
        workflow_run.current_node = run.metadata.get("current_node_id") or run.current_step_id
        workflow_run.final_artifact_id = run.final_artifact_id
        workflow_run.completed_at = run.completed_at
        workflow_run.metadata = {
            **(workflow_run.metadata or {}),
            "agent_status": run.status.value,
            "last_public_status": "paused"
            if run.status in {AgentRunStatus.AWAITING_GATE, AgentRunStatus.PAUSED}
            else run.status.value,
            "gate": run.gate,
            "error": run.error_message,
            "pause": run.metadata.get("pause"),
            "final_eval": run.metadata.get("final_eval"),
            "goal_card": run.metadata.get("goal_card"),
            "plan_version": run.metadata.get("plan_version"),
        }
        await self.artifact_store.update_workflow_run(workflow_run)

    async def _sync_node_run(self, step: AgentStep) -> None:
        """同步 AgentStep 到现有 NodeRun。"""
        node_run = await self.artifact_store.get_node_run(step.id)
        if not node_run:
            return
        status_map = {
            AgentStepStatus.COMPLETED: NodeRunStatus.COMPLETED,
            AgentStepStatus.FAILED: NodeRunStatus.FAILED,
            AgentStepStatus.BLOCKED: NodeRunStatus.INTERRUPTED,
            AgentStepStatus.SKIPPED: NodeRunStatus.INTERRUPTED,
        }
        node_run.status = status_map.get(step.status, NodeRunStatus.RUNNING)
        node_run.output_artifact_ids = step.artifact_ids
        node_run.error_message = step.error_message
        node_run.completed_at = step.ended_at
        if step.started_at and step.ended_at:
            node_run.duration_ms = int((step.ended_at - step.started_at).total_seconds() * 1000)
        await self.artifact_store.update_node_run(node_run)

    async def _replan(
        self,
        run: AgentRun,
        previous_plan: AgentPlan,
        failed_step: AgentStep,
        reflection: dict[str, Any],
    ) -> AgentPlan:
        await self.store.update_plan_status(previous_plan.id, AgentPlanStatus.SUPERSEDED)
        next_version = await self.store.next_plan_version(run.id)
        new_plan = self.planner.create_replan(
            run=run,
            previous_plan=previous_plan,
            failed_node_id=failed_step.node_id,
            reflection=reflection,
            next_version=next_version,
        )
        plan_artifact_id = await self._record_plan_artifact(run, new_plan)
        new_plan.metadata["artifact_id"] = plan_artifact_id
        await self.store.create_plan(new_plan)
        await self.store.create_replan_record(
            ReplanRecord(
                run_id=run.id,
                old_plan_id=previous_plan.id,
                new_plan_id=new_plan.id,
                trigger_reason=reflection.get("summary") or "quality_gate_failed",
                failed_step_id=failed_step.id,
                reflection=reflection,
            )
        )
        return new_plan

    async def _budget_violation(self, run: AgentRun) -> str | None:
        """检查工具调用次数与成本预算，避免长程任务无限消耗资源。"""
        tool_calls = await self.store.list_tool_calls(run.id)
        if (max_tool_calls := run.budget_limit.get("max_tool_calls")) and len(tool_calls) >= int(
            max_tool_calls
        ):
            return "达到最大工具调用次数，任务未完成"

        if max_cost := run.budget_limit.get("max_cost"):
            total_cost = 0.0
            for tool_call in tool_calls:
                amount = tool_call.cost.get("amount", 0) if tool_call.cost else 0
                try:
                    total_cost += float(amount)
                except (TypeError, ValueError):
                    continue
            if total_cost >= float(max_cost):
                return "达到最大成本预算，任务未完成"
        return None

    async def _fail_run(self, run: AgentRun, message: str) -> AgentRun:
        """以统一方式终止失败运行，并同步 Trace 顶层状态。"""
        run.status = AgentRunStatus.FAILED
        run.error_message = message
        run.queue_status = "terminal"
        run.updated_at = utc_now_naive()
        run.completed_at = utc_now_naive()
        await self.store.update_run(run)
        await self._sync_workflow_run(run)
        return run

    def _allowed_tool_permissions(self, run: AgentRun) -> set[str] | None:
        """读取 API 层写入的 actor 工具权限集合，离线运行未提供时保持兼容。"""
        permissions = run.metadata.get("allowed_tool_permissions")
        if not isinstance(permissions, list):
            return None
        return {str(permission) for permission in permissions}

    async def _can_replan(self, run_id: str, max_replans: int) -> bool:
        replans = await self.store.list_replan_records(run_id)
        return len(replans) < max_replans

    async def _build_final_payload(self, run: AgentRun, plan: AgentPlan) -> dict[str, Any]:
        steps = await self.store.list_steps(run.id)
        eval_results = await self.store.list_eval_results(run.id)
        tool_calls = await self.store.list_tool_calls(run.id)
        replans = await self.store.list_replan_records(run.id)
        return {
            "title": f"Autonomous Agent 交付物：{plan.goal_card.task_type}",
            "goal": run.goal,
            "goal_card": plan.goal_card.model_dump(mode="json"),
            "deliverables": plan.goal_card.deliverables,
            "execution_summary": {
                "step_count": len(steps),
                "tool_call_count": len(tool_calls),
                "eval_count": len(eval_results),
                "replan_count": len(replans),
            },
            "sections": [
                {
                    "title": "目标与约束",
                    "content": {
                        "goal": run.goal,
                        "constraints": plan.goal_card.constraints,
                        "risk_boundaries": plan.goal_card.risk_boundaries,
                    },
                },
                {
                    "title": "执行计划",
                    "content": plan.plan_graph.model_dump(mode="json"),
                },
                {
                    "title": "执行证据",
                    "content": [step.output for step in steps if step.output],
                },
                {
                    "title": "压缩上下文",
                    "content": await self.memory.build_context_window(run=run),
                },
                {
                    "title": "质量评估",
                    "content": [result.model_dump(mode="json") for result in eval_results],
                },
                {
                    "title": "重规划记录",
                    "content": [record.model_dump(mode="json") for record in replans],
                },
            ],
        }

    async def _latest_step_text(self, run_id: str) -> str:
        """提取最近一步输出文本，供核查类工具复用。"""
        steps = await self.store.list_steps(run_id)
        for step in reversed(steps):
            if step.output.get("fact_check_mode") is not None:
                continue
            text = self._flatten_text(step.output)
            if text.strip():
                return text
        return ""

    async def _fact_check_evidence_context(self, run_id: str) -> str:
        """把前序证据类步骤压缩为 CoVe 可消费的 Evidence Context。"""
        steps = await self.store.list_steps(run_id)
        evidence_chunks: list[str] = []
        for step in steps:
            if step.node_id not in {"retrieve_memory", "collect_evidence", "collect_trace"}:
                continue
            text = self._flatten_text(step.output).strip()
            if not text:
                continue
            evidence_chunks.append(f"### {step.title}\n{text[:1800]}")
        return "\n\n".join(evidence_chunks[-4:])

    def _flatten_text(self, value: Any) -> str:
        """把嵌套输出压缩为可传给工具的文本。"""
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return " ".join(self._flatten_text(item) for item in value.values())
        if isinstance(value, list):
            return " ".join(self._flatten_text(item) for item in value)
        return str(value)

    async def _build_generation_payload(
        self,
        run: AgentRun,
        plan: AgentPlan,
        node: PlanNode,
        context_window: dict[str, Any],
    ) -> dict[str, Any]:
        """按配置优先使用 LLM 生成主体内容，失败时降级到确定性模板。"""
        if not self._should_use_llm_generation(run):
            return self._build_generated_content(
                run,
                plan,
                context_window,
                generation_mode="template",
            )

        try:
            return await self._generate_content_with_llm(run, plan, node, context_window)
        except Exception as exc:
            content = self._build_generated_content(
                run,
                plan,
                context_window,
                generation_mode="template_fallback",
            )
            content["fallback_reason"] = str(exc)[:1000]
            return content

    async def _generate_content_with_llm(
        self,
        run: AgentRun,
        plan: AgentPlan,
        node: PlanNode,
        context_window: dict[str, Any],
    ) -> dict[str, Any]:
        """调用运行时模型生成真实主体交付物。"""
        model_provider_id = self._metadata_str(run, "model_provider_id")
        model_provider_name = self._metadata_str(run, "model_provider_name")
        model_name = self._metadata_str(run, "model_name")
        llm = await get_llm_for_workspace(
            run.workspace_id,
            model=model_name,
            model_provider_id=model_provider_id,
            model_provider_name=model_provider_name,
            temperature=0.7,
        )
        model_info = await get_current_model_info_for_workspace(
            run.workspace_id,
            model_provider_id=model_provider_id,
            model_provider_name=model_provider_name,
            model=model_name,
        )
        prompt = ChatPromptTemplate.from_template(AGENT_GENERATION_PROMPT)
        chain = prompt | llm
        prompt_payload = {
            "goal": run.goal,
            "goal_card": plan.goal_card.model_dump(mode="json"),
            "plan_graph": plan.plan_graph.model_dump(mode="json"),
            "context_window": context_window,
            "acceptance_criteria": node.acceptance_criteria,
        }
        result = await invoke_with_llm_retry(lambda: chain.ainvoke(prompt_payload))
        generated_text = str(getattr(result, "content", result)).strip()
        usage = ensure_usage_metadata(
            extract_usage_metadata(result),
            prompt_text=str(prompt_payload),
            completion_text=generated_text,
        )
        return {
            "goal": run.goal,
            "title": f"{plan.goal_card.task_type} 自主生成草案",
            "deliverables": plan.goal_card.deliverables,
            "context_window": context_window,
            "body": generated_text,
            "success_criteria": plan.goal_card.success_criteria,
            "generation_mode": "llm",
            "generation_prompt_version": "autonomous-agent-generation-v1",
            "llm_usage": usage,
            "llm_model": model_info,
        }

    def _build_generated_content(
        self,
        run: AgentRun,
        plan: AgentPlan,
        context_window: dict[str, Any],
        *,
        generation_mode: str = "template",
    ) -> dict[str, Any]:
        return {
            "goal": run.goal,
            "title": f"{plan.goal_card.task_type} 自主执行草案",
            "deliverables": plan.goal_card.deliverables,
            "context_window": context_window,
            "outline": [
                "目标理解与范围界定",
                "历史证据与上下文复用",
                "动态任务图与工具执行",
                "评估、反思和重规划",
                "最终交付与后续复用",
            ],
            "body": (
                f"本次 Autonomous Agent 围绕“{run.goal}”生成执行草案。"
                "系统先解析目标卡，再生成动态任务图，随后通过工具调用和评估闭环逐步收口。"
                "每次工具调用、评估结果和重规划记录都会被持久化，便于回放和审计。"
            ),
            "success_criteria": plan.goal_card.success_criteria,
            "generation_mode": generation_mode,
        }

    def _should_use_llm_generation(self, run: AgentRun) -> bool:
        """判断生成节点是否启用真实 LLM；auto 模式失败会自动回退模板。"""
        mode = str(run.metadata.get("generation_mode") or "").strip().lower()
        if mode in {"template", "rule", "disabled", "off"}:
            return False
        if mode in {"llm", "auto"}:
            return True
        env_value = str(
            getattr(get_settings(), "AUTONOMOUS_AGENT_LLM_GENERATION_ENABLED", False)
        ).lower()
        return env_value in {"1", "true", "yes", "on"}

    def _fact_check_mode(self, run: AgentRun) -> str:
        """读取事实核查模式；默认 auto，由工具自行决定 CoVe 或兜底扫描。"""
        mode = str(run.metadata.get("fact_check_mode") or "").strip().lower()
        return mode if mode else "auto"

    def _metadata_str(self, run: AgentRun, key: str) -> str | None:
        """读取可选模型元数据。"""
        value = run.metadata.get(key)
        if value in (None, ""):
            return None
        return str(value)

    def _latest_artifact_id(self, steps: list[AgentStep]) -> str | None:
        for step in reversed(steps):
            if step.artifact_ids:
                return step.artifact_ids[-1]
            if artifact_id := step.output.get("artifact_id"):
                return str(artifact_id)
        return None

    async def _require_run(self, run_id: str) -> AgentRun:
        run = await self.store.get_run(run_id)
        if not run:
            raise ValueError(f"AgentRun not found: {run_id}")
        return run

    async def _require_plan(self, plan_id: str) -> AgentPlan:
        plan = await self.store.get_plan(plan_id)
        if not plan:
            raise ValueError(f"AgentPlan not found: {plan_id}")
        return plan
