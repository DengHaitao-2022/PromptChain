"""Autonomous Agent 持久化服务。"""

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.autonomous_agent import (
    AgentPlan,
    AgentPlanStatus,
    AgentRun,
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
            orm.updated_at = run.updated_at
            orm.completed_at = run.completed_at
            orm.metadata_json = run.metadata
            await self.session.commit()
        return run

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
        """按简单关键词检索记忆，后续可替换为向量检索。"""
        filters = [MemoryRecordORM.workspace_id == workspace_id]
        if memory_types:
            filters.append(MemoryRecordORM.memory_type.in_([item.value for item in memory_types]))
        if query.strip():
            filters.append(MemoryRecordORM.content.ilike(f"%{query.strip()}%"))

        result = await self.session.execute(
            select(MemoryRecordORM)
            .where(*filters)
            .order_by(desc(MemoryRecordORM.confidence), desc(MemoryRecordORM.created_at))
            .limit(limit)
        )
        return [orm.to_model() for orm in result.scalars().all()]

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
