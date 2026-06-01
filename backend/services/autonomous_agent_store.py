"""Autonomous Agent 持久化服务。"""

from datetime import timedelta

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.time import utc_now_naive
from models.autonomous_agent import (
    AgentPlan,
    AgentPlanStatus,
    AgentRun,
    AgentRunStatus,
    AgentStep,
    EvalResult,
    MemoryRecord,
    MemoryType,
    ReplanRecord,
    ToolCall,
)
from orm.autonomous_agent_orm import (
    AgentPlanORM,
    AgentRunORM,
    AgentStepORM,
    EvalResultORM,
    MemoryRecordORM,
    ReplanRecordORM,
    ToolCallORM,
)


class AutonomousAgentStore:
    """封装 Agent Runtime 的数据库读写。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_run(self, run: AgentRun) -> AgentRun:
        """创建 AgentRun。"""
        self.session.add(AgentRunORM.from_model(run))
        await self.session.commit()
        return run

    async def update_run(self, run: AgentRun) -> AgentRun:
        """更新 AgentRun。"""
        orm = await self._get_run_orm(run.id)
        if orm:
            orm.status = run.status.value
            orm.autonomy_level = run.autonomy_level
            orm.goal = run.goal
            orm.budget_limit = run.budget_limit
            orm.current_plan_id = run.current_plan_id
            orm.current_step_id = run.current_step_id
            orm.final_artifact_id = run.final_artifact_id
            orm.gate = run.gate
            orm.error_message = run.error_message
            orm.queue_status = run.queue_status
            orm.queued_at = run.queued_at
            orm.claimed_at = run.claimed_at
            orm.lease_expires_at = run.lease_expires_at
            orm.heartbeat_at = run.heartbeat_at
            orm.worker_id = run.worker_id
            orm.lease_token = run.lease_token
            orm.attempt_count = run.attempt_count
            orm.last_worker_error = run.last_worker_error
            orm.updated_at = run.updated_at
            orm.completed_at = run.completed_at
            orm.metadata_json = run.metadata
            await self.session.commit()
        return run

    async def enqueue_run(self, run_id: str) -> AgentRun | None:
        """把 AgentRun 标记为可由 durable worker claim。"""
        orm = await self._get_run_orm(run_id)
        if not orm:
            return None
        now = utc_now_naive()
        if orm.queue_status not in {"running", "queued"}:
            orm.queue_status = "queued"
            orm.queued_at = now
            orm.worker_id = None
            orm.lease_token = None
            orm.lease_expires_at = None
            orm.last_worker_error = None
        orm.updated_at = now
        await self.session.commit()
        return orm.to_model()

    async def claim_run(
        self,
        run_id: str,
        *,
        worker_id: str,
        lease_token: str,
        lease_seconds: int,
    ) -> AgentRun | None:
        """原子认领一条可执行 AgentRun。"""
        now = utc_now_naive()
        result = await self.session.execute(
            select(AgentRunORM)
            .where(AgentRunORM.id == run_id)
            .where(
                AgentRunORM.status.in_([AgentRunStatus.RUNNING.value, AgentRunStatus.PAUSED.value])
            )
            .where(
                or_(
                    AgentRunORM.queue_status == "queued",
                    AgentRunORM.queue_status == "lease_expired",
                    and_(
                        AgentRunORM.queue_status == "running",
                        AgentRunORM.lease_expires_at < now,
                    ),
                )
            )
            .with_for_update(skip_locked=True)
        )
        orm = result.scalar_one_or_none()
        if not orm:
            return None
        orm.queue_status = "running"
        orm.worker_id = worker_id
        orm.lease_token = lease_token
        orm.claimed_at = now
        orm.heartbeat_at = now
        orm.lease_expires_at = now + timedelta(seconds=lease_seconds)
        orm.attempt_count = (orm.attempt_count or 0) + 1
        orm.last_worker_error = None
        orm.updated_at = now
        await self.session.commit()
        return orm.to_model()

    async def heartbeat_run(
        self,
        run_id: str,
        *,
        worker_id: str,
        lease_token: str,
        lease_seconds: int,
    ) -> bool:
        """刷新 worker lease 和 heartbeat。"""
        orm = await self._get_run_orm(run_id)
        if not orm or orm.worker_id != worker_id or orm.lease_token != lease_token:
            return False
        now = utc_now_naive()
        orm.heartbeat_at = now
        orm.lease_expires_at = now + timedelta(seconds=lease_seconds)
        orm.updated_at = now
        await self.session.commit()
        return True

    async def release_run_claim(
        self,
        run_id: str,
        *,
        worker_id: str,
        lease_token: str,
        queue_status: str = "idle",
        error: str | None = None,
    ) -> AgentRun | None:
        """释放 worker claim，并写入最终队列状态。"""
        orm = await self._get_run_orm(run_id)
        if not orm or orm.worker_id != worker_id or orm.lease_token != lease_token:
            return None
        now = utc_now_naive()
        orm.queue_status = queue_status
        orm.worker_id = None
        orm.lease_token = None
        orm.lease_expires_at = None
        orm.heartbeat_at = now
        orm.last_worker_error = error
        orm.updated_at = now
        await self.session.commit()
        return orm.to_model()

    async def list_recoverable_runs(self, *, limit: int = 50) -> list[AgentRun]:
        """列出 worker 启动后可恢复 claim 的运行。"""
        now = utc_now_naive()
        result = await self.session.execute(
            select(AgentRunORM)
            .where(
                AgentRunORM.status.in_([AgentRunStatus.RUNNING.value, AgentRunStatus.PAUSED.value])
            )
            .where(
                or_(
                    AgentRunORM.queue_status == "queued",
                    AgentRunORM.queue_status == "lease_expired",
                    AgentRunORM.lease_expires_at < now,
                )
            )
            .order_by(AgentRunORM.queued_at, AgentRunORM.updated_at)
            .limit(limit)
        )
        runs: list[AgentRun] = []
        for orm in result.scalars().all():
            if orm.lease_expires_at and orm.lease_expires_at < now:
                orm.queue_status = "lease_expired"
                orm.updated_at = now
            runs.append(orm.to_model())
        await self.session.commit()
        return runs

    async def get_run(self, run_id: str) -> AgentRun | None:
        """读取 AgentRun。"""
        orm = await self._get_run_orm(run_id)
        return orm.to_model() if orm else None

    async def list_runs(self, workspace_id: str, user_id: str | None = None) -> list[AgentRun]:
        """按工作空间列出 AgentRun。"""
        filters = [AgentRunORM.workspace_id == workspace_id]
        if user_id:
            filters.append(AgentRunORM.user_id == user_id)

        result = await self.session.execute(
            select(AgentRunORM).where(*filters).order_by(desc(AgentRunORM.created_at))
        )
        return [orm.to_model() for orm in result.scalars().all()]

    async def create_plan(self, plan: AgentPlan) -> AgentPlan:
        """创建计划版本。"""
        self.session.add(AgentPlanORM.from_model(plan))
        await self.session.commit()
        return plan

    async def update_plan_status(self, plan_id: str, status: AgentPlanStatus) -> None:
        """更新计划状态。"""
        result = await self.session.execute(select(AgentPlanORM).where(AgentPlanORM.id == plan_id))
        orm = result.scalar_one_or_none()
        if orm:
            orm.status = status.value
            await self.session.commit()

    async def get_plan(self, plan_id: str) -> AgentPlan | None:
        """读取计划版本。"""
        result = await self.session.execute(select(AgentPlanORM).where(AgentPlanORM.id == plan_id))
        orm = result.scalar_one_or_none()
        return orm.to_model() if orm else None

    async def list_plans(self, run_id: str) -> list[AgentPlan]:
        """列出运行的所有计划版本。"""
        result = await self.session.execute(
            select(AgentPlanORM).where(AgentPlanORM.run_id == run_id).order_by(AgentPlanORM.version)
        )
        return [orm.to_model() for orm in result.scalars().all()]

    async def next_plan_version(self, run_id: str) -> int:
        """计算下一个计划版本号。"""
        plans = await self.list_plans(run_id)
        return max((plan.version for plan in plans), default=0) + 1

    async def create_step(self, step: AgentStep) -> AgentStep:
        """创建步骤记录。"""
        self.session.add(AgentStepORM.from_model(step))
        await self.session.commit()
        return step

    async def update_step(self, step: AgentStep) -> AgentStep:
        """更新步骤记录。"""
        result = await self.session.execute(select(AgentStepORM).where(AgentStepORM.id == step.id))
        orm = result.scalar_one_or_none()
        if orm:
            orm.status = step.status.value
            orm.input_json = step.input
            orm.output_json = step.output
            orm.artifact_ids = step.artifact_ids
            orm.started_at = step.started_at
            orm.ended_at = step.ended_at
            orm.error_message = step.error_message
            orm.metadata_json = step.metadata
            await self.session.commit()
        return step

    async def get_step(self, step_id: str) -> AgentStep | None:
        """读取步骤。"""
        result = await self.session.execute(select(AgentStepORM).where(AgentStepORM.id == step_id))
        orm = result.scalar_one_or_none()
        return orm.to_model() if orm else None

    async def list_steps(self, run_id: str, plan_id: str | None = None) -> list[AgentStep]:
        """列出步骤。"""
        filters = [AgentStepORM.run_id == run_id]
        if plan_id:
            filters.append(AgentStepORM.plan_id == plan_id)
        result = await self.session.execute(
            select(AgentStepORM).where(*filters).order_by(AgentStepORM.started_at, AgentStepORM.id)
        )
        return [orm.to_model() for orm in result.scalars().all()]

    async def create_tool_call(self, tool_call: ToolCall) -> ToolCall:
        """创建工具调用记录。"""
        self.session.add(ToolCallORM.from_model(tool_call))
        await self.session.commit()
        return tool_call

    async def update_tool_call(self, tool_call: ToolCall) -> ToolCall:
        """更新工具调用记录。"""
        result = await self.session.execute(
            select(ToolCallORM).where(ToolCallORM.id == tool_call.id)
        )
        orm = result.scalar_one_or_none()
        if orm:
            orm.output_json = tool_call.output
            orm.status = tool_call.status.value
            orm.error_message = tool_call.error_message
            orm.latency_ms = tool_call.latency_ms
            orm.cost = tool_call.cost
            orm.completed_at = tool_call.completed_at
            orm.metadata_json = tool_call.metadata
            await self.session.commit()
        return tool_call

    async def get_tool_call(self, tool_call_id: str) -> ToolCall | None:
        """读取工具调用记录。"""
        result = await self.session.execute(
            select(ToolCallORM).where(ToolCallORM.id == tool_call_id)
        )
        orm = result.scalar_one_or_none()
        return orm.to_model() if orm else None

    async def list_tool_calls(self, run_id: str) -> list[ToolCall]:
        """列出工具调用。"""
        result = await self.session.execute(
            select(ToolCallORM).where(ToolCallORM.run_id == run_id).order_by(ToolCallORM.created_at)
        )
        return [orm.to_model() for orm in result.scalars().all()]

    async def create_eval_result(self, result: EvalResult) -> EvalResult:
        """创建评估结果。"""
        self.session.add(EvalResultORM.from_model(result))
        await self.session.commit()
        return result

    async def list_eval_results(self, run_id: str) -> list[EvalResult]:
        """列出评估结果。"""
        result = await self.session.execute(
            select(EvalResultORM)
            .where(EvalResultORM.run_id == run_id)
            .order_by(EvalResultORM.created_at)
        )
        return [orm.to_model() for orm in result.scalars().all()]

    async def create_memory(self, memory: MemoryRecord) -> MemoryRecord:
        """创建记忆记录。"""
        self.session.add(MemoryRecordORM.from_model(memory))
        await self.session.commit()
        return memory

    async def search_memories(
        self,
        workspace_id: str,
        query: str,
        *,
        memory_types: list[MemoryType] | None = None,
        limit: int = 8,
    ) -> list[MemoryRecord]:
        """按多关键词召回并本地重排记忆，后续可替换为向量检索。"""
        filters = [MemoryRecordORM.workspace_id == workspace_id]
        if memory_types:
            filters.append(MemoryRecordORM.memory_type.in_([item.value for item in memory_types]))
        query_terms = _memory_query_terms(query)
        if query_terms:
            filters.append(
                or_(*[MemoryRecordORM.content.ilike(f"%{term}%") for term in query_terms])
            )

        result = await self.session.execute(
            select(MemoryRecordORM)
            .where(*filters)
            .order_by(desc(MemoryRecordORM.confidence), desc(MemoryRecordORM.created_at))
            .limit(max(limit * 3, limit))
        )
        memories = [orm.to_model() for orm in result.scalars().all()]
        if not query_terms:
            return memories[:limit]
        return sorted(
            memories,
            key=lambda memory: _memory_rank(memory, query_terms),
            reverse=True,
        )[:limit]

    async def list_memories(self, workspace_id: str, limit: int = 50) -> list[MemoryRecord]:
        """列出工作空间记忆。"""
        result = await self.session.execute(
            select(MemoryRecordORM)
            .where(MemoryRecordORM.workspace_id == workspace_id)
            .order_by(desc(MemoryRecordORM.created_at))
            .limit(limit)
        )
        return [orm.to_model() for orm in result.scalars().all()]

    async def create_replan_record(self, record: ReplanRecord) -> ReplanRecord:
        """创建重规划记录。"""
        self.session.add(ReplanRecordORM.from_model(record))
        await self.session.commit()
        return record

    async def list_replan_records(self, run_id: str) -> list[ReplanRecord]:
        """列出重规划记录。"""
        result = await self.session.execute(
            select(ReplanRecordORM)
            .where(ReplanRecordORM.run_id == run_id)
            .order_by(ReplanRecordORM.created_at)
        )
        return [orm.to_model() for orm in result.scalars().all()]

    async def _get_run_orm(self, run_id: str) -> AgentRunORM | None:
        result = await self.session.execute(select(AgentRunORM).where(AgentRunORM.id == run_id))
        return result.scalar_one_or_none()


def _memory_query_terms(query: str) -> list[str]:
    """抽取可用于数据库召回的轻量关键词。"""
    normalized = (
        query.replace("，", " ")
        .replace("。", " ")
        .replace("、", " ")
        .replace(",", " ")
        .replace(".", " ")
        .replace("/", " ")
        .replace("\n", " ")
    )
    terms: list[str] = []
    for token in normalized.split():
        term = token.strip().lower()
        if len(term) < 2 or term in terms:
            continue
        terms.append(term)
        if len(terms) >= 8:
            break
    return terms


def _memory_rank(memory: MemoryRecord, query_terms: list[str]) -> tuple[float, float]:
    """按关键词覆盖率和置信度重排召回结果。"""
    content = memory.content.lower()
    metadata = str(memory.metadata or {}).lower()
    matched = sum(1 for term in query_terms if term in content or term in metadata)
    coverage = matched / max(len(query_terms), 1)
    return (coverage, memory.confidence)
