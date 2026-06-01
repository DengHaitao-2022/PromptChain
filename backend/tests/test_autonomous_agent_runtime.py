import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ.setdefault("ALLOW_INSECURE_JWT_SECRET", "true")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("AUTONOMOUS_AGENT_LLM_PLANNER_ENABLED", "false")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import get_settings
from db.postgres_store import Base
from models.artifact import ArtifactType
from models.autonomous_agent import (
    AgentRun,
    AgentRunStatus,
    AgentStep,
    AgentStepStatus,
    AgentStepType,
    ToolRiskLevel,
)
from services.artifact_store import ArtifactStore
from services.autonomous_agent_planner import AutonomousPlanner
from services.autonomous_agent_runtime import AutonomousAgentRuntime
from services.autonomous_agent_store import AutonomousAgentStore
from services.autonomous_agent_tools import ToolDefinition


async def _with_runtime(callback):
    import models.auth_orm  # noqa: F401

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        store = AutonomousAgentStore(session)
        artifact_store = ArtifactStore()
        runtime = AutonomousAgentRuntime(store=store, artifact_store=artifact_store)
        result = await callback(runtime, store, artifact_store)

    await engine.dispose()
    return result


def test_autonomous_agent_start_creates_full_runtime_trace():
    async def _scenario(runtime, store, artifact_store):
        run = await runtime.start(
            goal="请围绕当前项目调研 Workflow Agent 到 Autonomous Agent 的技术路线，输出完整报告材料",
            user_id="user-1",
            workspace_id="ws-1",
            auto_execute=True,
        )

        detail = await runtime.get_detail(run.id)

        assert detail["run"]["status"] == AgentRunStatus.COMPLETED.value
        assert detail["run"]["metadata"]["goal_card"]["task_type"] == "research_report"
        assert len(detail["plans"]) >= 1
        assert detail["plans"][0]["plan_graph"]["quality_gates"]
        assert detail["plans"][0]["metadata"]["artifact_id"]
        assert detail["plans"][0]["metadata"]["selected_template"] == "research_report_full_loop"
        assert len(detail["plans"][0]["metadata"]["plan_candidates"]) >= 3
        assert len(detail["steps"]) >= 8
        assert {step["node_id"] for step in detail["steps"]} >= {
            "goal_interpretation",
            "retrieve_memory",
            "draft_plan",
            "collect_evidence",
            "generate_content",
            "fact_check_content",
            "evaluate_output",
            "reflect_or_finalize",
            "finalize",
        }
        assert any(call["tool_name"] == "retrieve_memory" for call in detail["tool_calls"])
        assert any(call["tool_name"] == "write_artifact" for call in detail["tool_calls"])
        assert any(call["tool_name"] == "fact_check" for call in detail["tool_calls"])
        memory_step = next(step for step in detail["steps"] if step["node_id"] == "retrieve_memory")
        assert "knowledge_evidence" in memory_step["output"]
        assert "knowledge_error" in memory_step["output"]
        assert memory_step["output"]["artifact_evidence"]
        assert memory_step["output"]["trace_evidence"]
        assert any(
            item["tool_name"] == "retrieve_memory"
            for item in memory_step["output"]["tool_evidence"]
        )
        evidence_step = next(
            step for step in detail["steps"] if step["node_id"] == "collect_evidence"
        )
        assert evidence_step["output"]["artifact_count"] >= 1
        generated_step = next(
            step for step in detail["steps"] if step["node_id"] == "generate_content"
        )
        assert "context_window" in generated_step["output"]["artifact"]["content"]
        assert any(result["target_type"] == "final_output" for result in detail["eval_results"])
        assert detail["run"]["final_artifact_id"]
        assert await artifact_store.get_artifact(detail["plans"][0]["metadata"]["artifact_id"])
        assert await artifact_store.get_artifact(detail["run"]["final_artifact_id"])
        memories = await store.list_memories("ws-1")
        assert memories

    asyncio.run(_with_runtime(_scenario))


def test_planner_failure_enters_clarification_gate_and_can_resume():
    async def _scenario(runtime, store, _):
        run = await runtime.start(
            goal="   ",
            user_id="user-1",
            workspace_id="ws-1",
            auto_execute=False,
        )

        assert run.status == AgentRunStatus.AWAITING_GATE
        assert run.gate is not None
        assert run.gate["gate_type"] == "planner_clarification"

        clarified = await runtime.clarify_goal(
            run.id,
            "输出一份完整 Autonomous Agent 技术路线报告，覆盖工具调用、记忆和重规划。",
        )
        plans = await store.list_plans(run.id)

        assert clarified.status == AgentRunStatus.PLANNING
        assert clarified.current_plan_id
        assert clarified.error_message is None
        assert plans
        assert plans[0].metadata["artifact_id"]

    asyncio.run(_with_runtime(_scenario))


def test_llm_planner_generates_dynamic_plan_with_fake_provider():
    async def _scenario(runtime, _, __):
        original_provider = os.environ.get("DEFAULT_LLM_PROVIDER")
        original_llm_planner = os.environ.get("AUTONOMOUS_AGENT_LLM_PLANNER_ENABLED")
        os.environ["DEFAULT_LLM_PROVIDER"] = "fake"
        os.environ["AUTONOMOUS_AGENT_LLM_PLANNER_ENABLED"] = "true"
        get_settings.cache_clear()
        try:
            runtime.planner = AutonomousPlanner(enable_llm_planner=True)
            run = await runtime.start(
                goal="请调研 Autonomous Agent 动态规划能力并输出报告",
                user_id="user-1",
                workspace_id="ws-1",
                auto_execute=False,
                model_provider_name="fake",
            )
            detail = await runtime.get_detail(run.id)

            plan = detail["plans"][0]
            assert plan["created_by"] == "llm_planner"
            assert plan["metadata"]["planner_mode"] == "llm"
            assert plan["metadata"]["selected_template"] == "fake_llm_dynamic_plan"
            assert plan["metadata"]["planner_usage"]["total_tokens"] > 0
            assert "collect_trace" in {node["id"] for node in plan["plan_graph"]["nodes"]}
            assert any(
                node["tool_name"] == "retrieve_trace" for node in plan["plan_graph"]["nodes"]
            )
        finally:
            if original_provider is None:
                os.environ.pop("DEFAULT_LLM_PROVIDER", None)
            else:
                os.environ["DEFAULT_LLM_PROVIDER"] = original_provider
            if original_llm_planner is None:
                os.environ.pop("AUTONOMOUS_AGENT_LLM_PLANNER_ENABLED", None)
            else:
                os.environ["AUTONOMOUS_AGENT_LLM_PLANNER_ENABLED"] = original_llm_planner
            get_settings.cache_clear()

    asyncio.run(_with_runtime(_scenario))


def test_generation_node_uses_llm_with_fake_provider():
    async def _scenario(runtime, _, __):
        run = await runtime.start(
            goal="请生成一份 Autonomous Agent 真实生成链路验收材料",
            user_id="user-1",
            workspace_id="ws-1",
            auto_execute=True,
            generation_mode="llm",
            fact_check_mode="lightweight",
            model_provider_name="fake",
        )
        detail = await runtime.get_detail(run.id)
        generated_step = next(
            step for step in detail["steps"] if step["node_id"] == "generate_content"
        )
        content = generated_step["output"]["artifact"]["content"]

        assert content["generation_mode"] == "llm"
        assert "fake provider" in content["body"]
        assert content["llm_usage"]["total_tokens"] > 0
        assert content["llm_model"]["provider"] == "fake"

    asyncio.run(_with_runtime(_scenario))


def test_fact_check_tool_uses_cove_with_fake_provider():
    async def _scenario(runtime, _, __):
        run = await runtime.start(
            goal="验证 CoVe fact_check 工具",
            user_id="user-1",
            workspace_id="ws-1",
            auto_execute=False,
        )
        tool_call = await runtime.tool_executor.execute(
            run_id=run.id,
            tool_name="fact_check",
            payload={
                "text": "PromptChain 在 2026 年支持 Autonomous Agent 运行态。",
                "mode": "cove",
                "model_provider_name": "fake",
                "evidence_context": "PromptChain 已实现 AgentRun、PlanGraph、ToolCall 审计。",
            },
        )

        assert tool_call.status.value == "completed"
        assert tool_call.output["fact_check_mode"] == "cove"
        assert tool_call.output["claim_count"] == 0
        assert tool_call.output["llm_usage"]["total_tokens"] > 0

    asyncio.run(_with_runtime(_scenario))


def test_llm_planner_falls_back_when_schema_is_invalid():
    async def _scenario(runtime, _, __):
        original_provider = os.environ.get("DEFAULT_LLM_PROVIDER")
        os.environ["DEFAULT_LLM_PROVIDER"] = "fake"
        get_settings.cache_clear()
        try:
            planner = AutonomousPlanner(enable_llm_planner=True)
            broken_graph = planner.create_rule_based_initial_plan(
                AgentRun(
                    user_id="user-1",
                    workspace_id="ws-1",
                    goal="构造无效计划",
                )
            ).plan_graph
            broken_graph.nodes[3].tool_name = "missing_tool"

            async def _broken_llm_plan(run, memory_hits, tool_definitions):
                planner._normalize_and_validate_plan_graph(
                    broken_graph,
                    available_tool_names={tool["name"] for tool in tool_definitions},
                )
                raise AssertionError("无效计划不应通过校验")

            planner._create_llm_initial_plan = _broken_llm_plan
            runtime.planner = planner
            run = await runtime.start(
                goal="请调研 Autonomous Agent fallback 能力并输出报告",
                user_id="user-1",
                workspace_id="ws-1",
                auto_execute=False,
                planner_mode="auto",
            )
            detail = await runtime.get_detail(run.id)

            plan = detail["plans"][0]
            assert plan["created_by"] == "planner"
            assert plan["metadata"]["planner_mode"] == "rule_fallback"
            assert "未注册工具" in plan["metadata"]["fallback_reason"]
        finally:
            if original_provider is None:
                os.environ.pop("DEFAULT_LLM_PROVIDER", None)
            else:
                os.environ["DEFAULT_LLM_PROVIDER"] = original_provider
            get_settings.cache_clear()

    asyncio.run(_with_runtime(_scenario))


def test_tool_risk_gate_blocks_medium_risk_tool():
    async def _scenario(runtime, store, _):
        run = await runtime.start(
            goal="导出一份 Autonomous Agent 执行报告",
            user_id="user-1",
            workspace_id="ws-1",
            auto_execute=False,
        )
        plan = await store.get_plan(run.current_plan_id)
        assert plan is not None
        step = await store.create_step(
            AgentStep(
                run_id=run.id,
                plan_id=plan.id,
                node_id="manual_export",
                step_type=AgentStepType.TOOL_CALL,
                title="导出 DOCX",
                description="验证中风险工具 Gate",
                status=AgentStepStatus.RUNNING,
            )
        )

        tool_call = await runtime.tool_executor.execute(
            run_id=run.id,
            tool_name="export_docx",
            payload={"artifact_id": "artifact-1"},
            step=step,
        )

        assert tool_call.status.value == "awaiting_gate"
        assert tool_call.risk_level == ToolRiskLevel.MEDIUM
        assert tool_call.output["gate_required"] is True

    asyncio.run(_with_runtime(_scenario))


def test_tool_permission_denial_is_recorded_as_failed_tool_call():
    async def _scenario(runtime, store, _):
        run = await runtime.start(
            goal="导出一份 Autonomous Agent 执行报告",
            user_id="user-1",
            workspace_id="ws-1",
            allowed_tool_permissions=["workflow_run:read"],
            auto_execute=False,
        )
        plan = await store.get_plan(run.current_plan_id)
        assert plan is not None
        step = await store.create_step(
            AgentStep(
                run_id=run.id,
                plan_id=plan.id,
                node_id="manual_export",
                step_type=AgentStepType.TOOL_CALL,
                title="导出 DOCX",
                description="验证工具权限校验",
                status=AgentStepStatus.RUNNING,
            )
        )

        tool_call = await runtime.tool_executor.execute(
            run_id=run.id,
            tool_name="export_docx",
            payload={"artifact_id": "artifact-1"},
            step=step,
            allowed_permissions=runtime._allowed_tool_permissions(run),
        )

        assert tool_call.status.value == "failed"
        assert "workflow_run:export" in str(tool_call.error_message)

    asyncio.run(_with_runtime(_scenario))


def test_approved_gate_executes_original_tool_call_and_resumes():
    async def _scenario(runtime, store, _):
        run = await runtime.start(
            goal="导出一份 Autonomous Agent 执行报告",
            user_id="user-1",
            workspace_id="ws-1",
            auto_execute=False,
        )
        plan = await store.get_plan(run.current_plan_id)
        assert plan is not None
        step = await store.create_step(
            AgentStep(
                run_id=run.id,
                plan_id=plan.id,
                node_id="manual_export",
                step_type=AgentStepType.TOOL_CALL,
                title="导出 DOCX",
                description="验证 Gate 批准后继续执行",
                status=AgentStepStatus.RUNNING,
            )
        )
        tool_call = await runtime.tool_executor.execute(
            run_id=run.id,
            tool_name="export_docx",
            payload={"artifact_id": "artifact-1"},
            step=step,
        )
        step.output = runtime._tool_output(tool_call)
        step.status = AgentStepStatus.BLOCKED
        await store.update_step(step)
        run.status = AgentRunStatus.AWAITING_GATE
        run.gate = step.output["gate"]
        await store.update_run(run)

        resumed = await runtime.approve_gate(run.id, approved=True, note="允许导出")
        updated_step = await store.get_step(step.id)
        updated_call = await store.get_tool_call(tool_call.id)

        assert updated_step is not None
        assert updated_call is not None
        assert updated_step.status == AgentStepStatus.COMPLETED
        assert updated_call.status.value == "completed"
        assert updated_call.metadata["gate_decision"]["handled_note"] == "允许导出"
        assert resumed.status != AgentRunStatus.AWAITING_GATE

    asyncio.run(_with_runtime(_scenario))


def test_tool_executor_records_payload_validation_failure():
    async def _scenario(runtime, store, _):
        run = await runtime.start(
            goal="导出一份 Autonomous Agent 执行报告",
            user_id="user-1",
            workspace_id="ws-1",
            auto_execute=False,
        )

        tool_call = await runtime.tool_executor.execute(
            run_id=run.id,
            tool_name="export_docx",
            payload={},
        )
        stored_call = await store.get_tool_call(tool_call.id)

        assert stored_call is not None
        assert stored_call.status.value == "failed"
        assert "artifact_id" in (stored_call.error_message or "")

    asyncio.run(_with_runtime(_scenario))


def test_rollback_artifact_tool_creates_new_version_after_gate_approval():
    async def _scenario(runtime, store, artifact_store):
        run = await runtime.start(
            goal="验证 Artifact 局部回滚",
            user_id="user-1",
            workspace_id="ws-1",
            auto_execute=False,
        )
        plan = await store.get_plan(run.current_plan_id)
        assert plan is not None
        source_step = await store.create_step(
            AgentStep(
                run_id=run.id,
                plan_id=plan.id,
                node_id="source_artifact",
                step_type=AgentStepType.TOOL_CALL,
                title="创建源 Artifact",
                description="构造回滚源版本",
                status=AgentStepStatus.COMPLETED,
            )
        )
        source_artifact = await artifact_store.create_artifact(
            artifact_type=ArtifactType.FINAL_CONTENT,
            content={"version": "source"},
            workflow_run_id=run.id,
            node_run_id=source_step.id,
        )
        rollback_step = await store.create_step(
            AgentStep(
                run_id=run.id,
                plan_id=plan.id,
                node_id="rollback_artifact",
                step_type=AgentStepType.TOOL_CALL,
                title="回滚 Artifact",
                description="验证中风险回滚工具",
                status=AgentStepStatus.RUNNING,
            )
        )

        pending_call = await runtime.tool_executor.execute(
            run_id=run.id,
            tool_name="rollback_artifact",
            payload={"artifact_id": source_artifact.id, "workflow_run_id": run.id},
            step=rollback_step,
        )
        assert pending_call.status.value == "awaiting_gate"

        completed_call = await runtime.tool_executor.approve_and_execute(
            tool_call=pending_call,
            step=rollback_step,
        )
        rolled_back = completed_call.output["artifact"]

        assert completed_call.status.value == "completed"
        assert rolled_back["parent_version"] == source_artifact.id
        assert rolled_back["content"] == source_artifact.content

    asyncio.run(_with_runtime(_scenario))


def test_replan_records_are_created_for_failed_step():
    async def _scenario(runtime, store, artifact_store):
        run = await runtime.start(
            goal="短目标",
            user_id="user-1",
            workspace_id="ws-1",
            auto_execute=False,
        )
        plan = await store.get_plan(run.current_plan_id)
        assert plan is not None
        step = await store.create_step(
            AgentStep(
                run_id=run.id,
                plan_id=plan.id,
                node_id="generate_content",
                step_type=AgentStepType.GENERATION,
                title="生成主体产物",
                description="构造低质量输出",
                status=AgentStepStatus.COMPLETED,
                output={},
            )
        )
        eval_result = runtime.evaluator.evaluate_step(run, step)
        reflection = runtime.reflector.reflect(run=run, step=step, eval_result=eval_result)

        new_plan = await runtime._replan(run, plan, step, reflection)
        replans = await store.list_replan_records(run.id)

        assert new_plan.version == 2
        assert replans
        assert replans[0].old_plan_id == plan.id
        assert replans[0].new_plan_id == new_plan.id
        assert new_plan.metadata["artifact_id"]
        plan_artifact = await artifact_store.get_artifact(new_plan.metadata["artifact_id"])
        assert plan_artifact is not None
        assert plan_artifact.content["version"] == new_plan.version
        assert any(node.id.startswith("repair_2_") for node in new_plan.plan_graph.nodes)

    asyncio.run(_with_runtime(_scenario))


def test_replanned_failed_node_unblocks_repair_node():
    async def _scenario(runtime, store, _):
        run = await runtime.start(
            goal="完整调研 Autonomous Agent 长程任务能力",
            user_id="user-1",
            workspace_id="ws-1",
            auto_execute=False,
        )
        plan = await store.get_plan(run.current_plan_id)
        assert plan is not None
        for node_id in ("goal_interpretation", "retrieve_memory", "draft_plan"):
            await store.create_step(
                AgentStep(
                    run_id=run.id,
                    plan_id=plan.id,
                    node_id=node_id,
                    step_type=AgentStepType.PLANNING,
                    title=node_id,
                    description="构造已完成的前置步骤",
                    status=AgentStepStatus.COMPLETED,
                    output={"ok": True},
                )
            )
        failed_step = await store.create_step(
            AgentStep(
                run_id=run.id,
                plan_id=plan.id,
                node_id="collect_evidence",
                step_type=AgentStepType.TOOL_CALL,
                title="收集证据",
                description="构造执行失败后重规划",
                status=AgentStepStatus.FAILED,
                output={"error": "外部证据源不可用"},
                error_message="外部证据源不可用",
            )
        )
        eval_result = runtime.evaluator.evaluate_step(run, failed_step)
        reflection = runtime.reflector.reflect(run=run, step=failed_step, eval_result=eval_result)

        new_plan = await runtime._replan(run, plan, failed_step, reflection)
        next_node = await runtime._select_next_node(run, new_plan)

        assert next_node is not None
        assert next_node.id.startswith("repair_2_collect_evidence")

    asyncio.run(_with_runtime(_scenario))


def test_tool_registry_contains_issue_15_required_tools():
    async def _scenario(runtime, _, __):
        tools = {tool.name: tool for tool in runtime.tool_executor.registry.list_definitions()}

        assert {
            "read_artifact",
            "write_artifact",
            "rollback_artifact",
            "retrieve_memory",
            "retrieve_trace",
            "fact_check",
            "export_docx",
        } <= set(tools)
        assert all(isinstance(tool, ToolDefinition) for tool in tools.values())

    asyncio.run(_with_runtime(_scenario))


def test_retrieve_trace_tool_reads_node_run_evidence():
    async def _scenario(runtime, store, _):
        run = await runtime.start(
            goal="完整调研 Autonomous Agent Trace 工具能力",
            user_id="user-1",
            workspace_id="ws-1",
            budget_limit={"max_steps": 3, "max_replans": 0},
            auto_execute=False,
        )
        result = await runtime.execute_until_stop(run.id)
        steps = await store.list_steps(run.id)

        tool_call = await runtime.tool_executor.execute(
            run_id=run.id,
            tool_name="retrieve_trace",
            payload={"workflow_run_id": run.id},
            step=steps[-1],
        )

        assert result.status == AgentRunStatus.FAILED
        assert tool_call.output["node_run_count"] >= 3
        assert any(
            item["node_name"] == "retrieve_memory" for item in tool_call.output["trace_evidence"]
        )

    asyncio.run(_with_runtime(_scenario))


def test_skip_node_resolves_dynamic_plan_dependency():
    async def _scenario(runtime, store, artifact_store):
        run = await runtime.start(
            goal="完整调研 Autonomous Agent 动态跳过节点能力",
            user_id="user-1",
            workspace_id="ws-1",
            auto_execute=False,
        )
        plan = await store.get_plan(run.current_plan_id)
        assert plan is not None

        skipped = await runtime.skip_node(run.id, "goal_interpretation", "目标已由人工确认")
        next_node = await runtime._select_next_node(run, plan)
        node_run = await artifact_store.get_node_run(skipped.id)

        assert skipped.status == AgentStepStatus.SKIPPED
        assert skipped.output["skipped"] is True
        assert next_node is not None
        assert next_node.id == "retrieve_memory"
        assert node_run is not None
        assert node_run.status.value == "interrupted"

    asyncio.run(_with_runtime(_scenario))


def test_runtime_budget_uses_cumulative_step_count_across_resume():
    async def _scenario(runtime, store, _):
        run = await runtime.start(
            goal="验证长程任务预算限制",
            user_id="user-1",
            workspace_id="ws-1",
            budget_limit={"max_steps": 2, "max_replans": 0},
            auto_execute=False,
        )

        first = await runtime.execute_until_stop(run.id)
        second = await runtime.execute_until_stop(run.id)
        steps = await store.list_steps(run.id)

        assert first.status == AgentRunStatus.FAILED
        assert second.status == AgentRunStatus.FAILED
        assert len(steps) == 2
        assert second.error_message == "达到最大步骤数，任务未完成"

    asyncio.run(_with_runtime(_scenario))


def test_runtime_budget_limits_tool_calls_and_cost_across_resume():
    async def _scenario(runtime, store, _):
        run = await runtime.start(
            goal="验证长程任务工具预算限制",
            user_id="user-1",
            workspace_id="ws-1",
            budget_limit={"max_steps": 10, "max_replans": 0, "max_tool_calls": 1},
            auto_execute=False,
        )

        first = await runtime.execute_until_stop(run.id)
        second = await runtime.execute_until_stop(run.id)
        tool_calls = await store.list_tool_calls(run.id)

        assert first.status == AgentRunStatus.FAILED
        assert second.status == AgentRunStatus.FAILED
        assert len(tool_calls) == 1
        assert second.error_message == "达到最大工具调用次数，任务未完成"

        cost_limited = await runtime.start(
            goal="验证长程任务成本预算限制",
            user_id="user-1",
            workspace_id="ws-1",
            budget_limit={"max_steps": 10, "max_replans": 0, "max_cost": 1},
            auto_execute=False,
        )
        cost_result = await runtime.execute_until_stop(cost_limited.id)

        assert cost_result.status == AgentRunStatus.FAILED
        assert cost_result.error_message == "达到最大成本预算，任务未完成"

    asyncio.run(_with_runtime(_scenario))


def test_pause_and_cancel_control_long_running_agent_run():
    async def _scenario(runtime, store, artifact_store):
        run = await runtime.start(
            goal="验证 Autonomous Agent 暂停和取消",
            user_id="user-1",
            workspace_id="ws-1",
            auto_execute=False,
        )

        paused = await runtime.pause_run(run.id, reason="等待人工检查")
        workflow_run = await artifact_store.get_workflow_run(run.id)
        assert paused.status == AgentRunStatus.PAUSED
        assert paused.metadata["pause"]["reason"] == "等待人工检查"
        assert workflow_run is not None
        assert workflow_run.status.value == "paused"

        resumed = await runtime.execute_until_stop(run.id)
        assert resumed.status != AgentRunStatus.PAUSED

        second = await runtime.start(
            goal="验证 Autonomous Agent 取消",
            user_id="user-1",
            workspace_id="ws-1",
            auto_execute=False,
        )
        cancelled = await runtime.cancel_run(second.id, reason="目标已废弃")
        stored = await store.get_run(second.id)
        assert stored is not None
        assert cancelled.status == AgentRunStatus.CANCELLED
        assert stored.error_message == "目标已废弃"
        assert stored.completed_at is not None

    asyncio.run(_with_runtime(_scenario))
