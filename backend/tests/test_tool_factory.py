import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.errors.exceptions import DomainError
from graph.runtime_plan import compile_workflow_runtime_plan
from models import ArtifactType, MemberRole, NodeRunStatus, WorkflowRun
from models.auth_models import MemberRole as AuthMemberRole
from models.auth_orm import UserORM, WorkspaceORM
from orm.tool_orm import WorkspaceToolPolicyORM
from routes import tool_routes
from routes.workflow_routes import _assert_tool_gate_call_matches
from services.artifact_store import ArtifactStore
from services.tool_policy_service import ToolPolicyService
from tools import (
    BaseTool,
    RiskLevel,
    ToolCallStatus,
    ToolError,
    ToolExecutor,
    ToolFactory,
    ToolRegistry,
    ToolResult,
    ToolRuntime,
    ToolSourceType,
    ToolSpec,
)
from tools.audit import ToolAuditService
from tools.policy import ToolPolicyEngine
from tools.rate_limit import RateLimitUnavailableError, ToolRateLimiter
from tools.redaction import REDACTED_VALUE

pytestmark = pytest.mark.anyio


class ExternalEchoTool(BaseTool):
    spec = ToolSpec(
        name="test.external_echo",
        title="外部回声",
        description="测试用高风险外部动作工具。",
        category="test",
        source_type=ToolSourceType.INTERNAL,
        input_schema={
            "type": "object",
            "properties": {"message": {"type": "string", "minLength": 1}},
            "required": ["message"],
            "additionalProperties": False,
        },
        risk_level=RiskLevel.EXTERNAL_ACTION,
        permissions=["workflow.execute"],
        requires_approval=True,
    )

    async def execute(self, input_data: dict[str, Any], runtime: ToolRuntime):
        from tools import ToolResult

        return ToolResult(output={"echo": input_data["message"]}, summary="已执行外部回声")


class DestructiveEchoTool(ExternalEchoTool):
    spec = ToolSpec(
        name="test.destructive_echo",
        title="破坏性回声",
        description="测试用破坏性工具，必须强制审批。",
        category="test",
        source_type=ToolSourceType.INTERNAL,
        input_schema=ExternalEchoTool.spec.input_schema,
        risk_level=RiskLevel.DESTRUCTIVE,
        permissions=["workspace.manage"],
        requires_approval=False,
    )


class ExternalAutoCandidateTool(ExternalEchoTool):
    spec = ToolSpec(
        name="test.external_auto_candidate",
        title="可配置外部动作",
        description="测试用可被 workspace policy 放行的外部动作工具。",
        category="test",
        source_type=ToolSourceType.INTERNAL,
        input_schema=ExternalEchoTool.spec.input_schema,
        risk_level=RiskLevel.EXTERNAL_ACTION,
        permissions=["workflow.execute"],
        requires_approval=False,
    )


class FlakyGateTool(BaseTool):
    calls = 0

    spec = ToolSpec(
        name="test.flaky_gate",
        title="失败 Gate 工具",
        description="测试用先失败后成功的工具。",
        category="test",
        source_type=ToolSourceType.INTERNAL,
        input_schema={
            "type": "object",
            "properties": {"message": {"type": "string", "minLength": 1}},
            "required": ["message"],
            "additionalProperties": False,
        },
        risk_level=RiskLevel.READ_PRIVATE,
        permissions=["workflow.execute"],
        requires_approval=False,
    )

    async def execute(self, input_data: dict[str, Any], runtime: ToolRuntime):
        type(self).calls += 1
        if type(self).calls == 1:
            return ToolResult(
                success=False,
                summary="临时工具失败",
                error=ToolError(code="FLAKY_TOOL_FAILURE", message="临时工具失败"),
            )
        return ToolResult(output={"echo": input_data["message"]}, summary="失败后重试成功")


def _executor_with_test_tool(store: ArtifactStore) -> ToolExecutor:
    registry = ToolRegistry()
    registry.register(ExternalEchoTool)
    registry.register(ExternalAutoCandidateTool)
    registry.register(DestructiveEchoTool)
    registry.register(FlakyGateTool)
    return ToolExecutor(
        factory=ToolFactory(registry),
        audit_service=ToolAuditService(store),
    )


def _tool_state(workflow_run_id: str, tool_step: dict[str, Any]) -> dict[str, Any]:
    return {
        "workflow_run_id": workflow_run_id,
        "workspace_id": "workspace-1",
        "user_id": "user-1",
        "workspace_role": MemberRole.EDITOR.value,
        "runtime_plan": {"tool_steps": [tool_step]},
        "tool_results": {},
        "tool_call_ids": [],
        "tool_phase_completed": {},
        "awaiting_tool_approval": False,
        "tool_approvals": {},
    }


def _patch_tool_runner(monkeypatch, store: ArtifactStore, executor: ToolExecutor):
    import nodes.tool_runner as tool_runner_module

    monkeypatch.setattr(tool_runner_module, "get_artifact_store", lambda: store)
    monkeypatch.setattr(tool_runner_module, "get_tool_executor", lambda: executor)
    return tool_runner_module.run_pre_outline_tools


async def test_tool_executor_records_schema_validation_failure():
    store = ArtifactStore()
    executor = ToolExecutor(audit_service=ToolAuditService(store))
    runtime = ToolRuntime(
        user_id=None,
        workspace_id=None,
        workflow_run_id="wf-tool",
        node_run_id="node-tool",
        store=store,
    )

    result = await executor.execute(
        "validation.json_schema_validate",
        {"schema": {"type": "object"}},
        runtime,
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "TOOL_INPUT_INVALID"
    call = await store.get_tool_call(result.metadata["tool_call_id"])
    assert call is not None
    assert call.status == ToolCallStatus.FAILED
    assert call.error_message == result.error.message


async def test_high_risk_tool_requires_approval_then_executes():
    store = ArtifactStore()
    executor = _executor_with_test_tool(store)
    runtime = ToolRuntime(
        user_id="user-1",
        workspace_id="workspace-1",
        workflow_run_id="wf-tool",
        node_run_id="node-tool",
        role=MemberRole.EDITOR.value,
        store=store,
    )

    pending = await executor.execute(
        "test.external_echo",
        {"message": "hello"},
        runtime,
    )

    assert pending.requires_approval is True
    tool_call_id = pending.approval_request["tool_call_id"]
    pending_call = await store.get_tool_call(tool_call_id)
    assert pending_call is not None
    assert pending_call.status == ToolCallStatus.PENDING

    await executor.approve_tool_call(
        tool_call_id,
        approved_by="reviewer-1",
        approved=True,
        reason="测试审批通过",
    )
    executed = await executor.execute(
        "test.external_echo",
        {"message": "hello"},
        runtime,
        existing_tool_call_id=tool_call_id,
    )

    assert executed.success is True
    assert executed.output == {"echo": "hello"}
    call = await store.get_tool_call(tool_call_id)
    assert call is not None
    assert call.status == ToolCallStatus.SUCCEEDED
    assert call.approved_by == "reviewer-1"


async def test_approved_tool_call_cannot_be_reused_for_different_input():
    store = ArtifactStore()
    executor = _executor_with_test_tool(store)
    runtime = ToolRuntime(
        user_id="user-1",
        workspace_id="workspace-1",
        workflow_run_id="wf-tool",
        node_run_id="node-tool",
        role=MemberRole.EDITOR.value,
        store=store,
    )
    pending = await executor.execute("test.external_echo", {"message": "hello"}, runtime)
    tool_call_id = pending.approval_request["tool_call_id"]
    await executor.approve_tool_call(tool_call_id, approved_by="reviewer-1", approved=True)

    result = await executor.execute(
        "test.external_echo",
        {"message": "changed"},
        runtime,
        existing_tool_call_id=tool_call_id,
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "TOOL_APPROVAL_INPUT_MISMATCH"


async def test_approved_tool_call_cannot_be_reused_for_different_runtime_context():
    store = ArtifactStore()
    executor = _executor_with_test_tool(store)
    runtime = ToolRuntime(
        user_id="user-1",
        workspace_id="workspace-1",
        workflow_run_id="wf-tool",
        node_run_id="node-tool-1",
        role=MemberRole.EDITOR.value,
        store=store,
        approval_context={"phase": "pre_outline", "tool_step_id": "external-echo"},
    )
    pending = await executor.execute("test.external_echo", {"message": "hello"}, runtime)
    tool_call_id = pending.approval_request["tool_call_id"]
    await executor.approve_tool_call(tool_call_id, approved_by="reviewer-1", approved=True)

    reused_from_other_workflow = await executor.execute(
        "test.external_echo",
        {"message": "hello"},
        ToolRuntime(
            user_id="user-1",
            workspace_id="workspace-1",
            workflow_run_id="wf-other",
            node_run_id="node-tool-2",
            role=MemberRole.EDITOR.value,
            store=store,
            approval_context={"phase": "pre_outline", "tool_step_id": "external-echo"},
        ),
        existing_tool_call_id=tool_call_id,
    )
    reused_from_other_step = await executor.execute(
        "test.external_echo",
        {"message": "hello"},
        ToolRuntime(
            user_id="user-1",
            workspace_id="workspace-1",
            workflow_run_id="wf-tool",
            node_run_id="node-tool-3",
            role=MemberRole.EDITOR.value,
            store=store,
            approval_context={"phase": "pre_outline", "tool_step_id": "other-step"},
        ),
        existing_tool_call_id=tool_call_id,
    )

    assert reused_from_other_workflow.success is False
    assert reused_from_other_workflow.error is not None
    assert reused_from_other_workflow.error.code == "TOOL_APPROVAL_CONTEXT_MISMATCH"
    assert reused_from_other_step.success is False
    assert reused_from_other_step.error is not None
    assert reused_from_other_step.error.code == "TOOL_APPROVAL_CONTEXT_MISMATCH"


async def test_tool_audit_redacts_sensitive_input_output_but_keeps_fingerprint():
    store = ArtifactStore()
    audit = ToolAuditService(store)
    call = await audit.create_call(
        ExternalAutoCandidateTool.spec,
        {
            "message": "hello",
            "Authorization": "Bearer secret-token",
            "nested": {"api_key": "sk-test"},
        },
        ToolRuntime(
            user_id="user-1",
            workspace_id="workspace-1",
            workflow_run_id="wf-tool",
            node_run_id="node-tool",
            store=store,
        ),
        status=ToolCallStatus.RUNNING,
        requires_approval=False,
    )
    await audit.update_call(
        call,
        status=ToolCallStatus.SUCCEEDED,
        output={"password": "raw-password", "safe": "ok"},
    )

    saved = await store.get_tool_call(call.id)
    assert saved is not None
    assert saved.input_json["Authorization"] == REDACTED_VALUE
    assert saved.input_json["nested"]["api_key"] == REDACTED_VALUE
    assert saved.output_json["password"] == REDACTED_VALUE
    assert saved.output_json["safe"] == "ok"
    assert "input_fingerprint" in saved.metadata
    dumped = tool_routes._dump_tool_call(saved)
    assert dumped["input_json"]["Authorization"] == REDACTED_VALUE
    assert dumped["output_json"]["password"] == REDACTED_VALUE


async def test_artifact_read_direct_execution_enforces_workflow_visibility():
    store = ArtifactStore()
    workflow_run = await store.create_workflow_run(
        WorkflowRun(
            user_input="测试 Artifact 读取边界",
            metadata={"workspace_id": "workspace-1", "user_id": "owner-1"},
        )
    )
    artifact = await store.create_artifact(
        ArtifactType.TOOL_RESULT,
        content={"secret": "owner-only"},
        workflow_run_id=workflow_run.id,
        node_run_id="node-1",
    )
    executor = ToolExecutor(audit_service=ToolAuditService(store))

    denied = await executor.execute(
        "artifact.read",
        {"artifact_id": artifact.id},
        ToolRuntime(
            user_id="viewer-1",
            workspace_id="workspace-1",
            role=MemberRole.VIEWER.value,
            store=store,
        ),
    )

    assert denied.success is False
    assert denied.error is not None
    assert denied.error.code == "ARTIFACT_ACCESS_DENIED"

    allowed = await executor.execute(
        "artifact.read",
        {"artifact_id": artifact.id},
        ToolRuntime(
            user_id="admin-1",
            workspace_id="workspace-1",
            role=MemberRole.ADMIN.value,
            store=store,
        ),
    )

    assert allowed.success is True
    assert allowed.output["content"] == {"secret": "owner-only"}


async def test_artifact_write_parent_version_must_be_visible_to_runtime():
    store = ArtifactStore()
    owner_run = await store.create_workflow_run(
        WorkflowRun(
            user_input="owner",
            metadata={"workspace_id": "workspace-1", "user_id": "owner-1"},
        )
    )
    foreign_run = await store.create_workflow_run(
        WorkflowRun(
            user_input="foreign",
            metadata={"workspace_id": "workspace-2", "user_id": "owner-2"},
        )
    )
    parent = await store.create_artifact(
        ArtifactType.TOOL_RESULT,
        content={"secret": "foreign"},
        workflow_run_id=foreign_run.id,
        node_run_id="foreign-node",
    )
    executor = ToolExecutor(audit_service=ToolAuditService(store))

    denied = await executor.execute(
        "artifact.write",
        {"content": {"password": "keep-real"}, "parent_version_id": parent.id},
        ToolRuntime(
            user_id="owner-1",
            workspace_id="workspace-1",
            workflow_run_id=owner_run.id,
            node_run_id="node-1",
            role=MemberRole.EDITOR.value,
            store=store,
        ),
    )
    assert denied.success is False
    assert denied.error is not None
    assert denied.error.code == "ARTIFACT_ACCESS_DENIED"

    own_parent = await store.create_artifact(
        ArtifactType.TOOL_RESULT,
        content={"secret": "owner"},
        workflow_run_id=owner_run.id,
        node_run_id="node-1",
    )
    written = await executor.execute(
        "artifact.write",
        {"content": {"password": "keep-real"}, "parent_version_id": own_parent.id},
        ToolRuntime(
            user_id="owner-1",
            workspace_id="workspace-1",
            workflow_run_id=owner_run.id,
            node_run_id="node-2",
            role=MemberRole.EDITOR.value,
            store=store,
        ),
    )
    assert written.success is True
    artifact = await store.get_artifact(written.artifact_ids[0])
    assert artifact is not None
    assert artifact.content == {"password": "keep-real"}


async def test_destructive_tool_forces_admin_and_approval_even_in_auto_mode():
    store = ArtifactStore()
    executor = _executor_with_test_tool(store)

    denied = await executor.execute(
        "test.destructive_echo",
        {"message": "delete"},
        ToolRuntime(
            user_id="editor-1",
            workspace_id="workspace-1",
            role=MemberRole.EDITOR.value,
            store=store,
        ),
    )
    assert denied.success is False
    assert denied.error is not None
    assert denied.error.code == "TOOL_POLICY_DENIED"

    pending = await executor.execute(
        "test.destructive_echo",
        {"message": "delete"},
        ToolRuntime(
            user_id="owner-1",
            workspace_id="workspace-1",
            role=MemberRole.OWNER.value,
            store=store,
        ),
        approval_mode="auto",
    )

    assert pending.requires_approval is True
    assert pending.approval_request["risk_level"] == RiskLevel.DESTRUCTIVE.value


async def test_policy_order_keeps_requires_approval_gate_despite_workspace_auto_policy():
    class _AllowAllPolicyService:
        async def is_auto_run_enabled(self, workspace_id: str, tool_name: str) -> bool:
            return True

    class _FakeSession:
        pass

    store = ArtifactStore()
    executor = _executor_with_test_tool(store)
    runtime = ToolRuntime(
        user_id="user-1",
        workspace_id="workspace-1",
        workflow_run_id="wf-tool",
        node_run_id="node-tool",
        role=MemberRole.EDITOR.value,
        db_session=_FakeSession(),
        store=store,
    )

    from tools import policy as policy_module

    original_service = policy_module.ToolPolicyService
    policy_module.ToolPolicyService = lambda session: _AllowAllPolicyService()
    try:
        forced = await executor.execute(
            "test.external_echo",
            {"message": "hello"},
            runtime,
            approval_mode="auto",
        )
        candidate = await executor.execute(
            "test.external_auto_candidate",
            {"message": "hello"},
            runtime,
            approval_mode="auto",
        )
    finally:
        policy_module.ToolPolicyService = original_service

    assert forced.requires_approval is True
    assert forced.approval_request["tool_name"] == "test.external_echo"
    assert candidate.success is True
    assert candidate.output == {"echo": "hello"}


async def test_rate_limit_redis_failure_denies_policy_evaluation():
    class _FailingLimiter:
        async def hit(self, key: str, *, limit: int, window_seconds: int = 60) -> bool:
            raise RateLimitUnavailableError("redis unavailable")

    engine = ToolPolicyEngine(rate_limiter=_FailingLimiter())
    spec = ToolSpec(
        name="test.rate_limited",
        description="限流测试工具",
        category="test",
        risk_level=RiskLevel.READ_PRIVATE,
        permissions=[],
        cost_policy={"max_calls_per_minute": 1},
    )
    decision = await engine.evaluate(
        spec,
        ToolRuntime(
            user_id="user-1",
            workspace_id="workspace-1",
            role=MemberRole.EDITOR.value,
        ),
    )

    assert decision.allowed is False
    assert decision.reason == "redis unavailable"


async def test_tool_rate_limiter_redis_backend_fails_closed(monkeypatch):
    from core.config import get_settings

    class _BrokenRedisLimiter:
        async def hit(self, key: str, *, limit: int, window_seconds: int = 60) -> bool:
            raise RuntimeError("redis down")

    monkeypatch.setenv("TOOL_RATE_LIMIT_BACKEND", "redis")
    get_settings.cache_clear()
    try:
        limiter = ToolRateLimiter()
        limiter._redis = _BrokenRedisLimiter()
        with pytest.raises(RateLimitUnavailableError):
            await limiter.hit("workspace:user:tool", limit=1)
    finally:
        get_settings.cache_clear()


async def test_tool_policy_service_upserts_and_lists_workspace_policy():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(UserORM.__table__.create)
            await conn.run_sync(WorkspaceORM.__table__.create)
            await conn.run_sync(WorkspaceToolPolicyORM.__table__.create)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            service = ToolPolicyService(session)
            created = await service.upsert_policy(
                workspace_id="workspace-1",
                tool_name="test.external_auto_candidate",
                auto_run_enabled=True,
                actor_user_id="user-1",
                metadata={"reason": "允许自动执行"},
            )
            await session.commit()

            assert created.auto_run_enabled is True
            assert await service.is_auto_run_enabled(
                "workspace-1",
                "test.external_auto_candidate",
            )
            policies = await service.list_policies("workspace-1")
            assert [policy.tool_name for policy in policies] == ["test.external_auto_candidate"]

            updated = await service.upsert_policy(
                workspace_id="workspace-1",
                tool_name="test.external_auto_candidate",
                auto_run_enabled=False,
                actor_user_id="user-2",
                metadata={"reason": "关闭"},
            )
            await session.commit()
            assert updated.id == created.id
            assert updated.auto_run_enabled is False

            rows = (await session.execute(select(WorkspaceToolPolicyORM))).scalars().all()
            assert len(rows) == 1
    finally:
        await engine.dispose()


async def test_tool_policy_route_rejects_forced_approval_and_allows_auto_candidate(monkeypatch):
    class _FakePolicy:
        def __init__(self):
            self.id = "policy-1"
            self.workspace_id = "workspace-1"
            self.tool_name = "test.external_auto_candidate"
            self.auto_run_enabled = True
            self.created_by = "user-1"
            self.updated_by = "user-1"
            self.created_at = None
            self.updated_at = None
            self.metadata_json = {}

    class _FakePolicyService:
        async def upsert_policy(self, **kwargs):
            return _FakePolicy()

    class _FakeSession:
        async def commit(self):
            return None

    class _FakeStore:
        def initialized_session(self):
            class _Context:
                async def __aenter__(self):
                    return _FakeSession()

                async def __aexit__(self, exc_type, exc, tb):
                    return None

            return _Context()

    async def _allow_manage(request, resource: str, action: str):
        return "user-1", "workspace-1", AuthMemberRole.ADMIN

    async def _noop_record_tool_audit(*args, **kwargs):
        return None

    async def _noop_record(*args, **kwargs):
        return None

    registry = ToolRegistry()
    registry.register(ExternalEchoTool)
    registry.register(ExternalAutoCandidateTool)
    monkeypatch.setattr(tool_routes, "get_tool_registry", lambda: registry)
    monkeypatch.setattr(tool_routes.workflow_helpers, "require_workspace_permission", _allow_manage)
    monkeypatch.setattr(tool_routes, "get_postgres_store", lambda: _FakeStore())
    monkeypatch.setattr(tool_routes, "ToolPolicyService", lambda session: _FakePolicyService())
    monkeypatch.setattr(tool_routes, "_record_tool_audit", _noop_record_tool_audit)
    monkeypatch.setattr(
        tool_routes.AuditLogService,
        "record",
        _noop_record,
        raising=False,
    )

    with pytest.raises(HTTPException) as exc_info:
        await tool_routes.update_tool_policy(
            "test.external_echo",
            object(),
            tool_routes.ToolPolicyRequest(auto_run_enabled=True),
        )
    allowed = await tool_routes.update_tool_policy(
        "test.external_auto_candidate",
        object(),
        tool_routes.ToolPolicyRequest(auto_run_enabled=True),
    )

    assert exc_info.value.status_code == 403
    assert allowed["policy"]["auto_run_enabled"] is True


async def test_workflow_tool_phase_applies_output_mapping_and_audit(monkeypatch):
    store = ArtifactStore()
    workflow_run = await store.create_workflow_run(
        WorkflowRun(
            user_input="测试 tool 节点输出映射",
            metadata={"workspace_id": "workspace-1", "user_id": "user-1"},
        )
    )
    run_tool_phase = _patch_tool_runner(
        monkeypatch,
        store,
        ToolExecutor(audit_service=ToolAuditService(store)),
    )
    state = _tool_state(
        workflow_run.id,
        {
            "id": "validate-json",
            "phase": "pre_outline",
            "tool_name": "validation.json_schema_validate",
            "input": {
                "schema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
                "instance": {"name": "Ada"},
            },
            "output_mapping": {
                "stateKey": "validation_result",
                "persistArtifact": True,
                "artifactType": "tool_result",
            },
            "failure_strategy": "terminate",
            "approval_mode": "auto",
            "config": {},
        },
    )

    updated = await run_tool_phase(state)

    assert updated["validation_result"]["valid"] is True
    assert updated["tool_phase_completed"]["pre_outline"] is True
    assert updated["awaiting_tool_approval"] is False
    assert updated["tool_results"]["validate-json"]["status"] == "succeeded"
    assert len(updated["tool_call_ids"]) == 1
    tool_call = await store.get_tool_call(updated["tool_call_ids"][0])
    assert tool_call is not None
    assert tool_call.status == ToolCallStatus.SUCCEEDED
    node_runs = await store.get_node_runs_by_workflow(workflow_run.id)
    assert node_runs[-1].status == NodeRunStatus.COMPLETED
    assert node_runs[-1].output_artifact_ids
    artifact = await store.get_artifact(node_runs[-1].output_artifact_ids[0])
    assert artifact is not None
    assert artifact.type == ArtifactType.TOOL_RESULT


async def test_workflow_tool_phase_reuses_approved_gate_call(monkeypatch):
    store = ArtifactStore()
    workflow_run = await store.create_workflow_run(
        WorkflowRun(
            user_input="测试 tool Gate 恢复",
            metadata={"workspace_id": "workspace-1", "user_id": "user-1"},
        )
    )
    executor = _executor_with_test_tool(store)
    run_tool_phase = _patch_tool_runner(monkeypatch, store, executor)
    state = _tool_state(
        workflow_run.id,
        {
            "id": "external-echo",
            "phase": "pre_outline",
            "tool_name": "test.external_echo",
            "input": {"message": "hello"},
            "output_mapping": {"stateKey": "external_echo_result"},
            "failure_strategy": "terminate",
            "approval_mode": "policy_default",
            "config": {},
        },
    )

    pending_state = await run_tool_phase(state)

    assert pending_state["awaiting_tool_approval"] is True
    assert pending_state["tool_results"]["external-echo"]["status"] == "pending_approval"
    tool_call_id = pending_state["tool_results"]["external-echo"]["tool_call_id"]
    workflow_after_gate = await store.get_workflow_run(workflow_run.id)
    assert workflow_after_gate is not None
    assert workflow_after_gate.metadata["gate"]["tool_call_id"] == tool_call_id
    interrupted_runs = await store.get_node_runs_by_workflow(workflow_run.id)
    assert interrupted_runs[-1].status == NodeRunStatus.INTERRUPTED

    await executor.approve_tool_call(tool_call_id, approved_by="reviewer-1", approved=True)
    pending_state["tool_approvals"] = {tool_call_id: "approved"}
    pending_state["awaiting_tool_approval"] = False
    resumed_state = await run_tool_phase(pending_state)

    assert resumed_state["tool_phase_completed"]["pre_outline"] is True
    assert resumed_state["external_echo_result"] == {"echo": "hello"}
    assert resumed_state["tool_results"]["external-echo"]["status"] == "succeeded"
    assert resumed_state["tool_results"]["external-echo"]["tool_call_id"] == tool_call_id
    tool_call = await store.get_tool_call(tool_call_id)
    assert tool_call is not None
    assert tool_call.status == ToolCallStatus.SUCCEEDED
    workflow_after_resume = await store.get_workflow_run(workflow_run.id)
    assert workflow_after_resume is not None
    assert "gate" not in workflow_after_resume.metadata


async def test_workflow_tool_phase_enter_gate_retries_failed_call(monkeypatch):
    FlakyGateTool.calls = 0
    store = ArtifactStore()
    workflow_run = await store.create_workflow_run(
        WorkflowRun(
            user_input="测试 tool 失败 Gate 恢复",
            metadata={"workspace_id": "workspace-1", "user_id": "user-1"},
        )
    )
    executor = _executor_with_test_tool(store)
    run_tool_phase = _patch_tool_runner(monkeypatch, store, executor)
    state = _tool_state(
        workflow_run.id,
        {
            "id": "flaky-gate",
            "phase": "pre_outline",
            "tool_name": "test.flaky_gate",
            "input": {"message": "retry"},
            "output_mapping": {"stateKey": "flaky_gate_result"},
            "failure_strategy": "enter_gate",
            "approval_mode": "auto",
            "config": {},
        },
    )

    pending_state = await run_tool_phase(state)

    assert pending_state["awaiting_tool_approval"] is True
    assert pending_state["tool_results"]["flaky-gate"]["status"] == "pending_failure_gate"
    tool_call_id = pending_state["tool_results"]["flaky-gate"]["tool_call_id"]
    workflow_after_gate = await store.get_workflow_run(workflow_run.id)
    assert workflow_after_gate is not None
    assert workflow_after_gate.metadata["gate"]["trigger_reason"] == "tool_failure"
    failed_call = await store.get_tool_call(tool_call_id)
    assert failed_call is not None
    assert failed_call.status == ToolCallStatus.FAILED

    await executor.approve_tool_call(tool_call_id, approved_by="reviewer-1", approved=True)
    pending_state["tool_approvals"] = {tool_call_id: "approved"}
    pending_state["awaiting_tool_approval"] = False
    resumed_state = await run_tool_phase(pending_state)

    assert resumed_state["tool_phase_completed"]["pre_outline"] is True
    assert resumed_state["flaky_gate_result"] == {"echo": "retry"}
    assert resumed_state["tool_results"]["flaky-gate"]["status"] == "succeeded"
    assert resumed_state["tool_results"]["flaky-gate"]["tool_call_id"] == tool_call_id
    retried_call = await store.get_tool_call(tool_call_id)
    assert retried_call is not None
    assert retried_call.status == ToolCallStatus.SUCCEEDED
    assert FlakyGateTool.calls == 2


def test_runtime_plan_compiles_tool_nodes_into_phases():
    plan = compile_workflow_runtime_plan(
        {
            "workflow_definition_id": "def-1",
            "workflow_version_id": "ver-1",
            "nodes": [
                {"id": "start", "type": "start", "data": {"label": "开始"}},
                {
                    "id": "tool-1",
                    "type": "tool",
                    "data": {
                        "label": "校验 JSON",
                        "config": {
                            "toolName": "validation.json_schema_validate",
                            "executionPhase": "pre_outline",
                            "failureStrategy": "retry",
                        },
                    },
                },
                {"id": "content", "type": "task", "data": {"label": "内容"}},
                {"id": "end", "type": "end", "data": {"label": "结束"}},
            ],
            "edges": [
                {"source": "start", "target": "tool-1"},
                {"source": "tool-1", "target": "content"},
                {"source": "content", "target": "end"},
            ],
        }
    )

    assert plan["features"]["tool_execution"] is True
    assert any(step["id"] == "run_pre_outline_tools" for step in plan["steps"])
    assert plan["tool_steps"][0]["tool_name"] == "validation.json_schema_validate"
    assert plan["tool_steps"][0]["failure_strategy"] == "retry"


def test_tool_gate_approval_requires_current_gate_call():
    workflow_run = WorkflowRun(
        user_input="测试 Tool Gate 审批目标绑定",
        metadata={"gate": {"tool_call_id": "expected-call"}},
    )

    _assert_tool_gate_call_matches(workflow_run, "expected-call")

    with pytest.raises(DomainError) as exc_info:
        _assert_tool_gate_call_matches(workflow_run, "other-call")

    assert exc_info.value.code == "WORKFLOW_GATE_CONFLICT"
    assert exc_info.value.details == {
        "expected_tool_call_id": "expected-call",
        "received_tool_call_id": "other-call",
    }
