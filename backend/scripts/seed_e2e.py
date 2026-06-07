"""为 Playwright E2E 准备确定性的测试账号和 Agent 运行数据。"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy import delete, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.time import utc_now_naive
from db.postgres_store import NodeRunORM, WorkflowRunORM, get_postgres_store
from models.admin_orm import LoginAttemptORM, ModelProviderORM
from models.auth_models import MemberRole, UserStatus
from models.auth_orm import MembershipORM, UserORM, WorkspaceORM
from models.autonomous_agent import (
    AgentPlan,
    AgentPlanStatus,
    AgentRun,
    AgentRunStatus,
    AgentStep,
    AgentStepStatus,
    AgentStepType,
    GoalCard,
    PlanGraph,
    PlanNode,
    ToolCall,
    ToolCallStatus,
    ToolRiskLevel,
)
from orm.autonomous_agent_orm import (
    AgentPlanORM,
    AgentRunORM,
    AgentStepORM,
    EvalResultORM,
    MemoryRecordORM,
    ToolCallORM,
)
from services.auth_service import hash_password, normalize_email

E2E_USER_ID = os.getenv("E2E_USER_ID", "00000000-0000-4000-8000-000000000001")
E2E_WORKSPACE_ID = os.getenv("E2E_WORKSPACE_ID", "00000000-0000-4000-8000-000000000002")
E2E_PROVIDER_ID = os.getenv("E2E_PROVIDER_ID", "00000000-0000-4000-8000-000000000003")
E2E_EMAIL = normalize_email(os.getenv("E2E_TEST_EMAIL", "e2e-owner@example.com"))
E2E_PASSWORD = os.getenv("E2E_TEST_PASSWORD", "E2ePassword123!")

RUNNING_RUN_ID = "00000000-0000-4000-8000-000000000101"
PAUSED_RUN_ID = "00000000-0000-4000-8000-000000000102"
GATE_RUN_ID = "00000000-0000-4000-8000-000000000103"
SEEDED_RUN_IDS = (RUNNING_RUN_ID, PAUSED_RUN_ID, GATE_RUN_ID)


def _goal_card(goal: str) -> GoalCard:
    return GoalCard(
        goal=goal,
        task_type="e2e_smoke",
        constraints=["仅用于浏览器端到端测试", "禁止访问外部模型服务"],
        deliverables=["E2E 验证记录"],
        risk_boundaries=["中风险导出操作必须经过 Gate 审批"],
        success_criteria=["登录、运行台、详情页、暂停恢复和 Gate 审批均可操作"],
        quality_dimensions=["可重复", "确定性", "权限真实"],
    )


def _plan_graph(*, gate_node_status: AgentStepStatus | None = None) -> PlanGraph:
    export_status = gate_node_status or AgentStepStatus.PENDING
    return PlanGraph(
        nodes=[
            PlanNode(
                id="collect-context",
                title="收集上下文",
                step_type=AgentStepType.MEMORY_RETRIEVAL,
                description="读取测试工作空间中的上下文证据。",
                expected_output="上下文摘要",
                acceptance_criteria=["可以进入详情页查看计划图"],
                status=AgentStepStatus.COMPLETED,
            ),
            PlanNode(
                id="approve-export",
                title="准备导出审批",
                step_type=AgentStepType.TOOL_CALL,
                description="模拟中风险 DOCX 导出工具调用，覆盖 Gate 审批流程。",
                depends_on=["collect-context"],
                tool_name="export_docx",
                input={"artifact_id": "e2e-artifact"},
                expected_output="导出准备完成",
                acceptance_criteria=["审批通过后工具调用完成"],
                risk_level=ToolRiskLevel.MEDIUM,
                status=export_status,
            ),
        ],
        edges=[{"source": "collect-context", "target": "approve-export"}],
        quality_gates=[{"id": "export-approval", "tool_name": "export_docx"}],
        max_steps=4,
        max_replans=0,
    )


def _agent_run(
    *,
    run_id: str,
    goal: str,
    status: AgentRunStatus,
    plan_id: str,
    gate: dict | None = None,
    current_step_id: str | None = None,
) -> AgentRun:
    return AgentRun(
        id=run_id,
        user_id=E2E_USER_ID,
        workspace_id=E2E_WORKSPACE_ID,
        goal=goal,
        status=status,
        autonomy_level="supervised",
        budget_limit={"max_steps": 4, "max_replans": 0, "max_retries": 0},
        current_plan_id=plan_id,
        current_step_id=current_step_id,
        gate=gate,
        queue_status="idle",
        metadata={
            "source": "playwright_e2e_seed",
            "allowed_tool_permissions": [
                "workflow:execute",
                "workflow_run:create",
                "workflow_run:export",
                "workflow_run:read",
            ],
            "goal_card": _goal_card(goal).model_dump(mode="json"),
            "plan_version": 1,
        },
    )


def _agent_plan(run_id: str, plan_id: str, goal: str, plan_graph: PlanGraph) -> AgentPlan:
    return AgentPlan(
        id=plan_id,
        run_id=run_id,
        version=1,
        status=AgentPlanStatus.ACTIVE,
        plan_graph=plan_graph,
        goal_card=_goal_card(goal),
        created_by="e2e_seed",
        reason="playwright_seed",
        metadata={"source": "playwright_e2e_seed"},
    )


async def _upsert_identity(session) -> None:
    user = await session.get(UserORM, E2E_USER_ID)
    if user is None:
        session.add(
            UserORM(
                id=E2E_USER_ID,
                email=E2E_EMAIL,
                username="e2e-owner",
                display_name="E2E Owner",
                password_hash=hash_password(E2E_PASSWORD),
                status=UserStatus.ACTIVE.value,
                email_verified=True,
            )
        )
    else:
        user.email = E2E_EMAIL
        user.username = "e2e-owner"
        user.display_name = "E2E Owner"
        user.password_hash = hash_password(E2E_PASSWORD)
        user.status = UserStatus.ACTIVE.value
        user.email_verified = True
        user.updated_at = utc_now_naive()

    workspace = await session.get(WorkspaceORM, E2E_WORKSPACE_ID)
    if workspace is None:
        session.add(
            WorkspaceORM(
                id=E2E_WORKSPACE_ID,
                name="E2E 自动化工作空间",
                owner_id=E2E_USER_ID,
                description="Playwright E2E 专用种子工作空间",
            )
        )
    else:
        workspace.name = "E2E 自动化工作空间"
        workspace.owner_id = E2E_USER_ID
        workspace.updated_at = utc_now_naive()

    result = await session.execute(
        select(MembershipORM).where(
            MembershipORM.user_id == E2E_USER_ID,
            MembershipORM.workspace_id == E2E_WORKSPACE_ID,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        session.add(
            MembershipORM(
                id="00000000-0000-4000-8000-000000000004",
                user_id=E2E_USER_ID,
                workspace_id=E2E_WORKSPACE_ID,
                role=MemberRole.OWNER.value,
                invited_by=E2E_USER_ID,
            )
        )
    else:
        membership.role = MemberRole.OWNER.value
        membership.invited_by = E2E_USER_ID

    provider = await session.get(ModelProviderORM, E2E_PROVIDER_ID)
    provider_config = {
        "_runtime_default": True,
        "model": "fake-smoke-model",
    }
    if provider is None:
        session.add(
            ModelProviderORM(
                id=E2E_PROVIDER_ID,
                workspace_id=E2E_WORKSPACE_ID,
                provider="fake",
                name="E2E Fake Provider",
                description="端到端测试专用确定性模型供应商",
                enabled=True,
                config=provider_config,
                created_by=E2E_USER_ID,
            )
        )
    else:
        provider.workspace_id = E2E_WORKSPACE_ID
        provider.provider = "fake"
        provider.name = "E2E Fake Provider"
        provider.enabled = True
        provider.config = provider_config
        provider.created_by = E2E_USER_ID
        provider.updated_at = utc_now_naive()

    await session.execute(delete(LoginAttemptORM).where(LoginAttemptORM.email == E2E_EMAIL))
    await session.commit()


async def _clear_seeded_runs(session) -> None:
    await session.execute(delete(MemoryRecordORM).where(MemoryRecordORM.run_id.in_(SEEDED_RUN_IDS)))
    await session.execute(delete(EvalResultORM).where(EvalResultORM.run_id.in_(SEEDED_RUN_IDS)))
    await session.execute(delete(ToolCallORM).where(ToolCallORM.run_id.in_(SEEDED_RUN_IDS)))
    await session.execute(delete(AgentStepORM).where(AgentStepORM.run_id.in_(SEEDED_RUN_IDS)))
    await session.execute(delete(AgentPlanORM).where(AgentPlanORM.run_id.in_(SEEDED_RUN_IDS)))
    await session.execute(delete(NodeRunORM).where(NodeRunORM.workflow_run_id.in_(SEEDED_RUN_IDS)))
    await session.execute(delete(WorkflowRunORM).where(WorkflowRunORM.id.in_(SEEDED_RUN_IDS)))
    await session.execute(delete(AgentRunORM).where(AgentRunORM.id.in_(SEEDED_RUN_IDS)))
    await session.commit()


async def _seed_runs(session) -> None:
    now = utc_now_naive()
    running_plan_id = "00000000-0000-4000-8000-000000000201"
    paused_plan_id = "00000000-0000-4000-8000-000000000202"
    gate_plan_id = "00000000-0000-4000-8000-000000000203"
    paused_collect_step_id = "00000000-0000-4000-8000-000000000302"
    gate_step_id = "00000000-0000-4000-8000-000000000303"
    gate_collect_step_id = "00000000-0000-4000-8000-000000000304"
    gate_final_step_id = "00000000-0000-4000-8000-000000000305"
    gate_tool_call_id = "00000000-0000-4000-8000-000000000403"
    gate = {
        "gate_type": "tool_risk_approval",
        "tool_call_id": gate_tool_call_id,
        "tool_name": "export_docx",
        "risk_level": ToolRiskLevel.MEDIUM.value,
        "reason": "工具 export_docx 风险等级为 medium，需要 E2E 审批。",
        "opened_at": now.isoformat(),
    }
    scenarios = [
        (
            _agent_run(
                run_id=RUNNING_RUN_ID,
                goal="E2E 暂停流程目标",
                status=AgentRunStatus.RUNNING,
                plan_id=running_plan_id,
            ),
            _agent_plan(
                RUNNING_RUN_ID,
                running_plan_id,
                "E2E 暂停流程目标",
                _plan_graph(),
            ),
        ),
        (
            _agent_run(
                run_id=PAUSED_RUN_ID,
                goal="E2E 恢复流程目标",
                status=AgentRunStatus.PAUSED,
                plan_id=paused_plan_id,
            ),
            _agent_plan(
                PAUSED_RUN_ID,
                paused_plan_id,
                "E2E 恢复流程目标",
                _plan_graph(),
            ),
        ),
        (
            _agent_run(
                run_id=GATE_RUN_ID,
                goal="E2E Gate 审批流程目标",
                status=AgentRunStatus.AWAITING_GATE,
                plan_id=gate_plan_id,
                gate=gate,
                current_step_id=gate_step_id,
            ),
            _agent_plan(
                GATE_RUN_ID,
                gate_plan_id,
                "E2E Gate 审批流程目标",
                _plan_graph(gate_node_status=AgentStepStatus.BLOCKED),
            ),
        ),
    ]

    for run, _ in scenarios:
        workflow_status = "paused" if run.status != AgentRunStatus.RUNNING else "running"
        session.add(
            WorkflowRunORM(
                id=run.id,
                workflow_name="autonomous_agent",
                workflow_version="1.0.0",
                status=workflow_status,
                current_node=run.current_step_id or "collect-context",
                user_input=run.goal,
                metadata_json={
                    "runtime_type": "autonomous_agent",
                    "agent_run_id": run.id,
                    "user_id": run.user_id,
                    "workspace_id": run.workspace_id,
                    "agent_status": run.status.value,
                    "last_public_status": workflow_status,
                    "gate": run.gate,
                    "goal_card": run.metadata.get("goal_card"),
                    "plan_version": run.metadata.get("plan_version"),
                    "source": "playwright_e2e_seed",
                },
            )
        )

    for run, _ in scenarios:
        session.add(AgentRunORM.from_model(run))

    await session.flush()

    for _, plan in scenarios:
        session.add(AgentPlanORM.from_model(plan))

    completed_context_steps = [
        (
            paused_collect_step_id,
            PAUSED_RUN_ID,
            paused_plan_id,
            "E2E 恢复流程目标",
        ),
        (
            gate_collect_step_id,
            GATE_RUN_ID,
            gate_plan_id,
            "E2E Gate 审批流程目标",
        ),
    ]
    for step_id, run_id, plan_id, goal in completed_context_steps:
        session.add(
            NodeRunORM(
                id=step_id,
                workflow_run_id=run_id,
                node_name="collect-context",
                node_type="agent_memory_retrieval",
                started_at=now,
                completed_at=now,
                duration_ms=0,
                status="completed",
                input_artifact_ids=[],
                output_artifact_ids=[],
                llm_calls=[],
                retry_count=0,
                is_rerun=False,
            )
        )
        session.add(
            AgentStepORM.from_model(
                AgentStep(
                    id=step_id,
                    run_id=run_id,
                    plan_id=plan_id,
                    node_id="collect-context",
                    step_type=AgentStepType.MEMORY_RETRIEVAL,
                    title="收集上下文",
                    description="E2E 预置的已完成上下文步骤。",
                    status=AgentStepStatus.COMPLETED,
                    input={"goal": goal},
                    output={"summary": "E2E 已完成上下文收集"},
                    started_at=now,
                    ended_at=now,
                    metadata={"source": "playwright_e2e_seed"},
                )
            )
        )

    session.add(
        NodeRunORM(
            id=gate_step_id,
            workflow_run_id=GATE_RUN_ID,
            node_name="approve-export",
            node_type="agent_tool_call",
            started_at=now,
            completed_at=now,
            duration_ms=0,
            status="interrupted",
            input_artifact_ids=[],
            output_artifact_ids=[],
            llm_calls=[],
            retry_count=0,
            is_rerun=False,
        )
    )
    session.add(
        AgentStepORM.from_model(
            AgentStep(
                id=gate_step_id,
                run_id=GATE_RUN_ID,
                plan_id=gate_plan_id,
                node_id="approve-export",
                step_type=AgentStepType.TOOL_CALL,
                title="准备导出审批",
                description="等待人工批准中风险 DOCX 导出工具调用。",
                status=AgentStepStatus.BLOCKED,
                input={"artifact_id": "e2e-artifact"},
                output={"gate": gate},
                started_at=now,
                ended_at=now,
                metadata={"source": "playwright_e2e_seed"},
            )
        )
    )
    session.add(
        ToolCallORM.from_model(
            ToolCall(
                id=gate_tool_call_id,
                run_id=GATE_RUN_ID,
                step_id=gate_step_id,
                tool_name="export_docx",
                input={"artifact_id": "e2e-artifact"},
                output={
                    "gate_required": True,
                    "reason": "工具 export_docx 风险等级为 medium",
                },
                status=ToolCallStatus.AWAITING_GATE,
                risk_level=ToolRiskLevel.MEDIUM,
                completed_at=now,
                metadata={
                    "permission": "workflow_run:export",
                    "idempotent": True,
                    "source": "playwright_e2e_seed",
                },
            )
        )
    )
    session.add(
        NodeRunORM(
            id=gate_final_step_id,
            workflow_run_id=GATE_RUN_ID,
            node_name="finalize",
            node_type="agent_finalization",
            started_at=now,
            completed_at=now,
            duration_ms=0,
            status="completed",
            input_artifact_ids=[],
            output_artifact_ids=["e2e-artifact"],
            llm_calls=[],
            retry_count=0,
            is_rerun=False,
        )
    )
    session.add(
        AgentStepORM.from_model(
            AgentStep(
                id=gate_final_step_id,
                run_id=GATE_RUN_ID,
                plan_id=gate_plan_id,
                node_id="finalize",
                step_type=AgentStepType.FINALIZATION,
                title="最终收口",
                description="E2E 预置的最终交付步骤，确保 Gate 审批后可完成收口。",
                status=AgentStepStatus.COMPLETED,
                input={"goal": "E2E Gate 审批流程目标"},
                output={
                    "summary": "E2E Gate 审批流程目标 已完成，Gate 审批通过并生成 E2E 验证记录。",
                    "artifact_id": "e2e-artifact",
                },
                artifact_ids=["e2e-artifact"],
                started_at=now,
                ended_at=now,
                metadata={"source": "playwright_e2e_seed"},
            )
        )
    )
    await session.commit()


async def main() -> None:
    store = get_postgres_store()
    await store.ensure_initialized()
    async with store.async_session() as session:
        await _upsert_identity(session)
        await _clear_seeded_runs(session)
        await _seed_runs(session)
    print(
        "E2E seed ready: "
        f"email={E2E_EMAIL} workspace_id={E2E_WORKSPACE_ID} "
        f"runs={','.join(SEEDED_RUN_IDS)}"
    )


if __name__ == "__main__":
    asyncio.run(main())
