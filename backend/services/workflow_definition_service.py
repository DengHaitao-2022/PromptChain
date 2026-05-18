"""
工作流定义服务

提供工作流定义的 CRUD、校验、发布和版本管理能力。
"""

import uuid
from collections import defaultdict, deque
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.time import to_utc_iso, utc_now_iso, utc_now_naive
from graph.runtime_plan import compile_workflow_runtime_plan
from models.workflow_definition import (
    WorkflowCompileResult,
    WorkflowDefinition,
    WorkflowDefinitionCreate,
    WorkflowDefinitionUpdate,
    WorkflowEdge,
    WorkflowNode,
    WorkflowValidationMode,
    WorkflowValidationResult,
)
from models.workflow_orm import WorkflowDefinitionORM, WorkflowVersionORM

_REQUIRED_RUNTIME_NODE_CONFIG_FIELDS: dict[str, list[str]] = {
    "process": ["modelName"],
    "gate": ["gateType", "timeout"],
    "checker": ["confidenceThreshold"],
    "output": ["outputFormat"],
}

_REQUIRED_NODE_CONFIG_FIELDS_BY_TYPE: dict[str, list[str]] = {
    "process": ["modelName"],
    "llm": ["modelName"],
    "agent_step": ["modelName"],
    "gate": ["gateType", "timeout"],
    "checker": ["confidenceThreshold"],
    "fact_check": ["confidenceThreshold"],
    "output": ["outputFormat"],
    "tool": ["toolName"],
    "tool_call": ["toolName"],
    "http": ["url", "method"],
    "sql": ["query"],
    "code": ["source"],
    "delay": ["durationMs"],
    "subflow": ["workflowId"],
}

_SUPPORTED_RUNTIME_NODE_TYPES = {"input", "process", "gate", "checker", "output"}

# richer taxonomy 到当前运行时五大类别的兼容映射。
# 目标不是宣称执行引擎已经拥有全部专用语义，而是让前端编辑器可以先稳定提交 DSL，
# 同时在发布校验和编译预览阶段给出明确、可预期的降级行为。
_RUNTIME_NODE_TYPE_ALIASES: dict[str, str] = {
    "start": "input",
    "prompt": "input",
    "end": "output",
    "task": "process",
    "llm": "process",
    "agent_step": "process",
    "tool": "process",
    "tool_call": "process",
    "knowledge": "process",
    "rag_retrieve": "process",
    "rerank": "process",
    "output_parser": "process",
    "memory_read": "process",
    "memory_write": "process",
    "http": "process",
    "sql": "process",
    "function": "process",
    "webhook": "process",
    "queue_publish": "process",
    "email": "process",
    "slack": "process",
    "im": "process",
    "file_loader": "process",
    "code": "process",
    "delay": "process",
    "subflow": "process",
    "switch": "gate",
    "condition": "gate",
    "if_else": "gate",
    "loop": "gate",
    "parallel": "gate",
    "merge": "gate",
    "retry_gate": "gate",
    "approval": "gate",
    "review": "gate",
    "edit": "gate",
    "assign": "gate",
    "human_approval": "gate",
    "fact_check": "checker",
}

_POSTGRES_SCHEMA_STATEMENTS = (
    "ALTER TABLE workflow_definitions ADD COLUMN IF NOT EXISTS published_version_id VARCHAR(36)",
    "ALTER TABLE workflow_definitions ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ",
    "ALTER TABLE workflow_definitions ADD COLUMN IF NOT EXISTS published_by VARCHAR(36)",
    "ALTER TABLE workflow_versions ADD COLUMN IF NOT EXISTS name VARCHAR(255) DEFAULT ''",
    "ALTER TABLE workflow_versions ADD COLUMN IF NOT EXISTS description TEXT DEFAULT ''",
    "ALTER TABLE workflow_versions ADD COLUMN IF NOT EXISTS snapshot_type VARCHAR(32) DEFAULT 'draft'",
    "ALTER TABLE workflow_versions ADD COLUMN IF NOT EXISTS source_version_id VARCHAR(36)",
    "ALTER TABLE workflow_versions ADD COLUMN IF NOT EXISTS metadata_json JSON DEFAULT '{}'::json",
    """
    UPDATE workflow_versions AS versions
    SET
        name = COALESCE(NULLIF(versions.name, ''), definitions.name),
        description = COALESCE(versions.description, definitions.description, '')
    FROM workflow_definitions AS definitions
    WHERE versions.workflow_id = definitions.id
    """,
)


class WorkflowDefinitionService:
    """工作流定义服务。"""

    _schema_ready = False

    def __init__(self, session: AsyncSession):
        self.session = session

    @classmethod
    async def ensure_schema(cls, session: AsyncSession) -> None:
        """对齐工作流定义相关表结构。"""
        if cls._schema_ready:
            return

        bind = session.get_bind()
        if bind is None or bind.dialect.name != "postgresql":
            cls._schema_ready = True
            return

        for statement in _POSTGRES_SCHEMA_STATEMENTS:
            await session.execute(text(statement))

        await session.commit()
        cls._schema_ready = True

    async def create(
        self,
        workspace_id: str,
        user_id: str,
        data: WorkflowDefinitionCreate,
    ) -> WorkflowDefinition:
        """创建工作流定义。"""
        await self.ensure_schema(self.session)

        workflow = WorkflowDefinitionORM(
            id=str(uuid.uuid4()),
            name=data.name,
            description=data.description or "",
            version=1,
            nodes=[node.model_dump() for node in data.nodes],
            edges=[edge.model_dump() for edge in data.edges],
            workspace_id=workspace_id,
            created_by=user_id,
            is_published=0,
        )

        self.session.add(workflow)
        await self.session.commit()
        await self.session.refresh(workflow)

        return self._orm_to_model(workflow)

    async def get_by_id(
        self,
        workflow_id: str,
        workspace_id: str,
        *,
        published_only: bool = False,
        use_published_snapshot: bool = False,
    ) -> WorkflowDefinition | None:
        """根据 ID 获取工作流定义。"""
        await self.ensure_schema(self.session)

        workflow = await self._get_definition_orm(
            workflow_id=workflow_id,
            workspace_id=workspace_id,
            published_only=published_only,
        )
        if not workflow:
            return None

        snapshot = None
        published_snapshot = (
            await self._get_published_snapshot(workflow) if workflow.is_published else None
        )
        if use_published_snapshot:
            snapshot = published_snapshot
            if not snapshot:
                return None

        return self._orm_to_model(
            workflow,
            snapshot=snapshot,
            published_snapshot=published_snapshot,
        )

    async def list_by_workspace(
        self,
        workspace_id: str,
        limit: int = 50,
        offset: int = 0,
        *,
        published_only: bool = False,
        use_published_snapshot: bool = False,
    ) -> list[WorkflowDefinition]:
        """列出工作空间中的工作流定义。"""
        await self.ensure_schema(self.session)

        statement = (
            select(WorkflowDefinitionORM)
            .where(
                WorkflowDefinitionORM.workspace_id == workspace_id,
                WorkflowDefinitionORM.is_deleted == 0,
            )
            .order_by(WorkflowDefinitionORM.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if published_only:
            statement = statement.where(WorkflowDefinitionORM.is_published == 1)

        result = await self.session.execute(statement)
        workflows = result.scalars().all()

        items: list[WorkflowDefinition] = []
        for workflow in workflows:
            published_snapshot = (
                await self._get_published_snapshot(workflow) if workflow.is_published else None
            )
            snapshot = published_snapshot if use_published_snapshot else None
            if use_published_snapshot and snapshot is None:
                continue
            items.append(
                self._orm_to_model(
                    workflow,
                    snapshot=snapshot,
                    published_snapshot=published_snapshot,
                )
            )
        return items

    async def list_public_published(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowDefinition]:
        """列出首页匿名可见的已发布工作流。"""
        await self.ensure_schema(self.session)

        statement = (
            select(WorkflowDefinitionORM)
            .where(
                WorkflowDefinitionORM.is_deleted == 0,
                WorkflowDefinitionORM.is_published == 1,
            )
            .order_by(WorkflowDefinitionORM.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(statement)
        workflows = result.scalars().all()

        items: list[WorkflowDefinition] = []
        for workflow in workflows:
            published_snapshot = await self._get_published_snapshot(workflow)
            if not published_snapshot:
                continue
            items.append(
                self._orm_to_model(
                    workflow,
                    snapshot=published_snapshot,
                    published_snapshot=published_snapshot,
                )
            )
        return items

    async def get_public_published_version(
        self,
        workflow_id: str,
    ) -> tuple[WorkflowDefinitionORM | None, WorkflowVersionORM | None]:
        """获取匿名可见工作流的已发布版本快照。"""
        await self.ensure_schema(self.session)

        result = await self.session.execute(
            select(WorkflowDefinitionORM).where(
                WorkflowDefinitionORM.id == workflow_id,
                WorkflowDefinitionORM.is_deleted == 0,
                WorkflowDefinitionORM.is_published == 1,
            )
        )
        workflow = result.scalar_one_or_none()
        if not workflow:
            return None, None

        return workflow, await self._get_published_snapshot(workflow)

    async def update(
        self,
        workflow_id: str,
        workspace_id: str,
        user_id: str,
        data: WorkflowDefinitionUpdate,
    ) -> WorkflowDefinition | None:
        """保存工作流草稿。"""
        await self.ensure_schema(self.session)

        workflow = await self._get_definition_orm(
            workflow_id=workflow_id, workspace_id=workspace_id
        )
        if not workflow:
            return None

        current_snapshot = await self._ensure_snapshot(
            workflow,
            user_id=user_id,
            snapshot_type="draft",
            change_log=data.change_log or f"保存草稿 v{workflow.version}",
            metadata={
                "event_type": "save",
                "saved_by": user_id,
                "saved_version": workflow.version,
            },
        )
        restore_provenance = self._extract_restore_provenance(current_snapshot.metadata_json)

        if data.name is not None:
            workflow.name = data.name
        if data.description is not None:
            workflow.description = data.description
        if data.nodes is not None:
            workflow.nodes = [node.model_dump() for node in data.nodes]
        if data.edges is not None:
            workflow.edges = [edge.model_dump() for edge in data.edges]

        workflow.version += 1
        workflow.updated_at = utc_now_naive()

        if restore_provenance:
            # 恢复来源需要沿当前草稿版本继续传递，避免后续发布丢失 lineage。
            restore_provenance["draft_version"] = workflow.version
            await self._ensure_snapshot(
                workflow,
                user_id=user_id,
                snapshot_type="draft",
                change_log=data.change_log or f"保存草稿 v{workflow.version}",
                metadata={
                    "event_type": "save",
                    "saved_by": user_id,
                    "saved_version": workflow.version,
                    "restore_provenance": restore_provenance,
                    "restored_from_version_id": restore_provenance.get("restored_from_version_id"),
                    "restored_from_version": restore_provenance.get("restored_from_version"),
                    "restore_source_snapshot_type": restore_provenance.get(
                        "restore_source_snapshot_type"
                    ),
                },
                source_version_id=restore_provenance.get("restored_from_version_id"),
            )

        await self.session.commit()
        await self.session.refresh(workflow)

        return self._orm_to_model(workflow)

    async def publish(
        self,
        workflow_id: str,
        workspace_id: str,
        user_id: str,
        *,
        change_log: str = "",
    ) -> tuple[WorkflowDefinition | None, WorkflowValidationResult, WorkflowVersionORM | None]:
        """发布工作流当前草稿。"""
        await self.ensure_schema(self.session)

        workflow = await self._get_definition_orm(
            workflow_id=workflow_id, workspace_id=workspace_id
        )
        if not workflow:
            return (
                None,
                WorkflowValidationResult(
                    mode=WorkflowValidationMode.PUBLISH,
                    is_valid=False,
                    errors=["工作流不存在"],
                ),
                None,
            )

        definition = self._orm_to_model(workflow)
        validation = self.validate(definition, mode=WorkflowValidationMode.PUBLISH)
        if not validation.is_valid:
            return definition, validation, None

        current_snapshot = await self._get_version_snapshot(workflow.id, workflow.version)
        restore_provenance = self._extract_restore_provenance(
            current_snapshot.metadata_json if current_snapshot else None
        )
        published_at = utc_now_naive()
        publish_metadata: dict[str, Any] = {
            "event_type": "publish",
            "published_at": to_utc_iso(published_at),
            "published_by": user_id,
            "published_version": workflow.version,
        }
        publish_source_version_id = None
        if restore_provenance:
            restore_provenance["draft_version"] = workflow.version
            publish_source_version_id = restore_provenance.get("restored_from_version_id")
            publish_metadata.update(
                {
                    "restore_provenance": restore_provenance,
                    "restored_from_version_id": restore_provenance.get("restored_from_version_id"),
                    "restored_from_version": restore_provenance.get("restored_from_version"),
                    "restore_source_snapshot_type": restore_provenance.get(
                        "restore_source_snapshot_type"
                    ),
                }
            )
        snapshot = await self._ensure_snapshot(
            workflow,
            user_id=user_id,
            snapshot_type="publish",
            change_log=change_log or f"发布版本 v{workflow.version}",
            metadata=publish_metadata,
            source_version_id=publish_source_version_id,
            force_refresh=True,
        )

        workflow.is_published = 1
        workflow.published_version_id = snapshot.id
        workflow.published_at = published_at
        workflow.published_by = user_id
        workflow.updated_at = published_at

        await self.session.commit()
        await self.session.refresh(workflow)

        published_snapshot = await self._get_published_snapshot(workflow)
        return self._orm_to_model(workflow, snapshot=published_snapshot), validation, snapshot

    async def get_version_history(
        self,
        workflow_id: str,
        workspace_id: str,
    ) -> tuple[WorkflowDefinitionORM | None, list[WorkflowVersionORM]]:
        """获取工作流版本历史。"""
        await self.ensure_schema(self.session)

        workflow = await self._get_definition_orm(
            workflow_id=workflow_id, workspace_id=workspace_id
        )
        if not workflow:
            return None, []

        result = await self.session.execute(
            select(WorkflowVersionORM)
            .where(WorkflowVersionORM.workflow_id == workflow_id)
            .order_by(WorkflowVersionORM.version.desc(), WorkflowVersionORM.created_at.desc())
        )
        versions = result.scalars().all()
        return workflow, list(versions)

    async def get_version_by_id(
        self,
        workflow_id: str,
        workspace_id: str,
        version_id: str,
    ) -> tuple[WorkflowDefinitionORM | None, WorkflowVersionORM | None]:
        """获取指定版本快照。"""
        await self.ensure_schema(self.session)

        workflow = await self._get_definition_orm(
            workflow_id=workflow_id, workspace_id=workspace_id
        )
        if not workflow:
            return None, None

        result = await self.session.execute(
            select(WorkflowVersionORM).where(
                WorkflowVersionORM.id == version_id,
                WorkflowVersionORM.workflow_id == workflow_id,
            )
        )
        return workflow, result.scalar_one_or_none()

    async def compare_versions(
        self,
        workflow_id: str,
        workspace_id: str,
        version_a: int,
        version_b: int,
    ) -> dict[str, Any] | None:
        """对比两个版本的差异。"""
        await self.ensure_schema(self.session)

        workflow = await self._get_definition_orm(
            workflow_id=workflow_id, workspace_id=workspace_id
        )
        if not workflow:
            return None

        left = await self._load_version_payload(workflow, version_a)
        right = await self._load_version_payload(workflow, version_b)
        if left is None or right is None:
            return None

        left_nodes = left["nodes"]
        right_nodes = right["nodes"]
        left_edges = left["edges"]
        right_edges = right["edges"]

        left_node_ids = {node.get("id") for node in left_nodes}
        right_node_ids = {node.get("id") for node in right_nodes}
        left_edge_ids = {edge.get("id") for edge in left_edges}
        right_edge_ids = {edge.get("id") for edge in right_edges}

        left_node_map = {node.get("id"): node for node in left_nodes}
        right_node_map = {node.get("id"): node for node in right_nodes}

        nodes_modified = [
            node_id
            for node_id in sorted(left_node_ids & right_node_ids)
            if left_node_map.get(node_id) != right_node_map.get(node_id)
        ]

        return {
            "version_a": version_a,
            "version_b": version_b,
            "nodes_added": sorted(right_node_ids - left_node_ids),
            "nodes_removed": sorted(left_node_ids - right_node_ids),
            "nodes_modified": nodes_modified,
            "edges_added": sorted(right_edge_ids - left_edge_ids),
            "edges_removed": sorted(left_edge_ids - right_edge_ids),
        }

    async def restore(
        self,
        workflow_id: str,
        workspace_id: str,
        user_id: str,
        version_id: str,
        *,
        change_log: str = "",
    ) -> tuple[WorkflowDefinition | None, WorkflowVersionORM | None]:
        """从历史版本恢复到新的草稿版本。"""
        await self.ensure_schema(self.session)

        workflow, version = await self.get_version_by_id(workflow_id, workspace_id, version_id)
        if not workflow or not version:
            return None, None

        await self._ensure_snapshot(
            workflow,
            user_id=user_id,
            snapshot_type="restore_backup",
            change_log=change_log or f"恢复前备份 v{workflow.version}",
            metadata={
                "event_type": "restore_backup",
                "restore_target_version_id": version.id,
                "restore_target_version": version.version,
                "restore_requested_by": user_id,
            },
            source_version_id=version.id,
        )

        workflow.name = version.name or workflow.name
        workflow.description = version.description or ""
        workflow.nodes = version.nodes or []
        workflow.edges = version.edges or []
        restored_at = utc_now_naive()
        restore_provenance = {
            "restored_from_version_id": version.id,
            "restored_from_version": version.version,
            "restore_source_snapshot_type": version.snapshot_type,
            "restored_by": user_id,
            "restored_at": to_utc_iso(restored_at),
            "draft_version": workflow.version + 1,
        }
        workflow.version += 1
        workflow.updated_at = utc_now_naive()
        await self._ensure_snapshot(
            workflow,
            user_id=user_id,
            snapshot_type="draft",
            change_log=change_log or f"恢复版本 v{version.version} 到草稿",
            metadata={
                "event_type": "restore",
                "restore_provenance": restore_provenance,
                "restored_from_version_id": version.id,
                "restored_from_version": version.version,
                "restore_source_snapshot_type": version.snapshot_type,
                "restored_by": user_id,
                "restored_at": to_utc_iso(restored_at),
            },
            source_version_id=version.id,
        )

        await self.session.commit()
        await self.session.refresh(workflow)

        restored = self._orm_to_model(workflow)
        return restored, version

    async def delete(self, workflow_id: str, workspace_id: str) -> bool:
        """软删除工作流定义。"""
        await self.ensure_schema(self.session)

        result = await self.session.execute(
            update(WorkflowDefinitionORM)
            .where(
                WorkflowDefinitionORM.id == workflow_id,
                WorkflowDefinitionORM.workspace_id == workspace_id,
            )
            .values(is_deleted=1, updated_at=utc_now_naive())
        )
        await self.session.commit()
        return result.rowcount > 0

    def validate(
        self,
        definition: WorkflowDefinition,
        *,
        mode: WorkflowValidationMode = WorkflowValidationMode.SAVE,
    ) -> WorkflowValidationResult:
        """校验工作流定义。"""
        errors: list[str] = []
        warnings: list[str] = []

        if not definition.nodes:
            errors.append("工作流必须至少包含一个节点")

        runtime_types = {
            node.id: self._resolve_runtime_node_type(node.type) for node in definition.nodes
        }
        input_nodes = [node for node in definition.nodes if runtime_types[node.id] == "input"]
        output_nodes = [node for node in definition.nodes if runtime_types[node.id] == "output"]
        process_nodes = [node for node in definition.nodes if runtime_types[node.id] == "process"]
        gate_nodes = [node for node in definition.nodes if runtime_types[node.id] == "gate"]

        runtime_warnings: set[str] = set()
        for node in definition.nodes:
            runtime_type = runtime_types[node.id]
            label = (node.data.label or "").strip() or node.id
            if runtime_type not in _SUPPORTED_RUNTIME_NODE_TYPES:
                errors.append(
                    f"节点 {label} 使用了暂不支持的类型 {node.type}，"
                    "请改为受支持的运行时类别，或先补齐执行引擎语义。"
                )
                continue

            if runtime_type != node.type:
                runtime_warnings.add(
                    f"节点 {label} 的类型 {node.type} 当前按 {runtime_type} 类别参与发布校验与编译预览。"
                )

        if not input_nodes:
            errors.append("工作流必须包含至少一个输入节点")
        elif len(input_nodes) > 1:
            if mode == WorkflowValidationMode.PUBLISH:
                errors.append("发布前只能保留一个输入节点")
            else:
                warnings.append("工作流包含多个输入节点，可能导致执行顺序不确定")

        if not output_nodes:
            if mode == WorkflowValidationMode.PUBLISH:
                errors.append("发布前必须至少包含一个输出节点")
            else:
                warnings.append("工作流没有输出节点，可能无法正确输出结果")

        if mode == WorkflowValidationMode.PUBLISH and not process_nodes:
            errors.append("发布前必须至少包含一个处理节点")

        if mode == WorkflowValidationMode.PUBLISH and not gate_nodes:
            warnings.append("建议至少包含一个 Gate 节点，便于人工确认关键风险")

        node_ids = [node.id for node in definition.nodes]
        edge_ids = [edge.id for edge in definition.edges]

        if len(node_ids) != len(set(node_ids)):
            errors.append("存在重复的节点 ID")
        if len(edge_ids) != len(set(edge_ids)):
            errors.append("存在重复的连线 ID")

        node_map = {node.id: node for node in definition.nodes}
        incoming: dict[str, list[str]] = defaultdict(list)
        outgoing: dict[str, list[str]] = defaultdict(list)

        for edge in definition.edges:
            if edge.source not in node_map:
                errors.append(f"连线 {edge.id} 的源节点 {edge.source} 不存在")
                continue
            if edge.target not in node_map:
                errors.append(f"连线 {edge.id} 的目标节点 {edge.target} 不存在")
                continue
            if edge.source == edge.target:
                errors.append(f"连线 {edge.id} 不能连接到自身")
                continue

            outgoing[edge.source].append(edge.target)
            incoming[edge.target].append(edge.source)

        for node in definition.nodes:
            label = (node.data.label or "").strip()
            runtime_type = runtime_types[node.id]
            if not label:
                errors.append(f"节点 {node.id} 缺少名称")

            if node.id not in incoming and runtime_type not in {"input"}:
                if mode == WorkflowValidationMode.PUBLISH:
                    errors.append(f"节点 {label or node.id} 没有上游连接")
                else:
                    warnings.append(f"节点 {label or node.id} 没有上游连接")

            if node.id not in outgoing and runtime_type not in {"output"}:
                if mode == WorkflowValidationMode.PUBLISH:
                    errors.append(f"节点 {label or node.id} 没有下游连接")
                else:
                    warnings.append(f"节点 {label or node.id} 没有下游连接")

            if (
                node.id not in incoming
                and node.id not in outgoing
                and runtime_type not in {"input", "output"}
            ):
                warnings.append(f"节点 {label or node.id} 是孤立节点，没有连接")

            if mode == WorkflowValidationMode.PUBLISH:
                config = node.data.config or {}
                required_fields = self._get_required_node_config_fields(node.type, runtime_type)
                missing_fields = [
                    field for field in required_fields if config.get(field) in (None, "", [])
                ]
                if missing_fields:
                    errors.append(
                        f"节点 {label or node.id} 缺少必要配置: {', '.join(missing_fields)}"
                    )

        if mode == WorkflowValidationMode.PUBLISH and definition.edges:
            if self._has_cycle(definition.nodes, definition.edges):
                errors.append("发布前工作流不能包含循环")

            entry_ids = {node.id for node in input_nodes}
            exit_ids = {node.id for node in output_nodes}

            reachable_from_input = self._collect_reachable(entry_ids, outgoing)
            can_reach_output = self._collect_reachable(exit_ids, incoming)

            unreachable = [
                node.data.label or node.id
                for node in definition.nodes
                if node.id not in reachable_from_input
            ]
            dead_end = [
                node.data.label or node.id
                for node in definition.nodes
                if node.id not in can_reach_output
            ]

            if unreachable:
                errors.append(f"存在无法从输入节点到达的节点: {', '.join(unreachable)}")
            if dead_end:
                errors.append(f"存在无法流向输出节点的节点: {', '.join(dead_end)}")

            if input_nodes and output_nodes and not (reachable_from_input & exit_ids):
                errors.append("发布前至少需要一条从输入节点到输出节点的完整路径")

        warnings.extend(sorted(runtime_warnings))

        return WorkflowValidationResult(
            mode=mode,
            is_valid=not errors,
            errors=errors,
            warnings=warnings,
        )

    def compile(self, definition: WorkflowDefinition) -> WorkflowCompileResult:
        """将工作流定义编译为 LangGraph 代码预览和受限运行计划。"""
        validation = self.validate(definition, mode=WorkflowValidationMode.PUBLISH)
        if not validation.is_valid:
            return WorkflowCompileResult(success=False, errors=validation.errors)

        code_lines = [
            "from langgraph.graph import StateGraph, END",
            "from typing import TypedDict",
            "",
            "class WorkflowState(TypedDict):",
            "    messages: list",
            "    current_step: str",
            "",
            "graph = StateGraph(WorkflowState)",
            "",
            "# 说明: 扩展节点类型会先映射到当前运行时支持的五大类别。",
            "# 这里的 LangGraph 代码是预览；实际运行会同时使用 runtime_plan 控制受限执行闭环。",
            "",
            "# 添加节点",
        ]

        for node in definition.nodes:
            node_name = node.id.replace("-", "_")
            runtime_type = self._resolve_runtime_node_type(node.type)
            if runtime_type != node.type:
                code_lines.append(
                    f"# 节点 {node.data.label or node.id}: 原始类型 {node.type} -> 兼容映射 {runtime_type}"
                )
            code_lines.append(f"graph.add_node('{node_name}', {runtime_type}_handler)")

        code_lines.append("")
        code_lines.append("# 添加边")
        for edge in definition.edges:
            source = edge.source.replace("-", "_")
            target = edge.target.replace("-", "_")
            code_lines.append(f"graph.add_edge('{source}', '{target}')")

        if input_nodes := [
            node
            for node in definition.nodes
            if self._resolve_runtime_node_type(node.type) == "input"
        ]:
            entry = input_nodes[0].id.replace("-", "_")
            code_lines.extend(["", "# 设置入口", f"graph.set_entry_point('{entry}')"])

        code_lines.extend(["", "# 编译图", "workflow = graph.compile()"])
        runtime_plan = compile_workflow_runtime_plan(
            {
                "workflow_definition_id": definition.id,
                "workflow_version_id": definition.published_version_id,
                "definition_name": definition.name,
                "definition_description": definition.description,
                "version": definition.version,
                "nodes": [node.model_dump(mode="json") for node in definition.nodes],
                "edges": [edge.model_dump(mode="json") for edge in definition.edges],
            }
        )
        return WorkflowCompileResult(
            success=True,
            graph_code="\n".join(code_lines),
            runtime_plan=runtime_plan,
        )

    def _resolve_runtime_node_type(self, node_type: str) -> str:
        normalized = node_type.strip().lower().replace("-", "_")
        return _RUNTIME_NODE_TYPE_ALIASES.get(normalized, normalized)

    def _get_required_node_config_fields(self, node_type: str, runtime_type: str) -> list[str]:
        normalized = node_type.strip().lower().replace("-", "_")
        if normalized in _REQUIRED_NODE_CONFIG_FIELDS_BY_TYPE:
            return _REQUIRED_NODE_CONFIG_FIELDS_BY_TYPE[normalized]
        return _REQUIRED_RUNTIME_NODE_CONFIG_FIELDS.get(runtime_type, [])

    def version_to_dict(
        self,
        version: WorkflowVersionORM,
        *,
        published_version_id: str | None = None,
    ) -> dict[str, Any]:
        """序列化版本快照。"""
        metadata = version.metadata_json or {}
        return {
            "id": version.id,
            "workflow_id": version.workflow_id,
            "version": version.version,
            "name": version.name,
            "description": version.description,
            "nodes": version.nodes or [],
            "edges": version.edges or [],
            "change_log": version.change_log,
            "snapshot_type": version.snapshot_type,
            "source_version_id": version.source_version_id,
            "created_by": version.created_by,
            "created_at": to_utc_iso(version.created_at) if version.created_at else None,
            "is_current_published": version.id == published_version_id,
            "metadata": metadata,
        }

    async def _get_definition_orm(
        self,
        *,
        workflow_id: str,
        workspace_id: str,
        published_only: bool = False,
    ) -> WorkflowDefinitionORM | None:
        statement = select(WorkflowDefinitionORM).where(
            WorkflowDefinitionORM.id == workflow_id,
            WorkflowDefinitionORM.workspace_id == workspace_id,
            WorkflowDefinitionORM.is_deleted == 0,
        )
        if published_only:
            statement = statement.where(WorkflowDefinitionORM.is_published == 1)

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def _get_published_snapshot(
        self,
        workflow: WorkflowDefinitionORM,
    ) -> WorkflowVersionORM | None:
        if workflow.published_version_id:
            result = await self.session.execute(
                select(WorkflowVersionORM).where(
                    WorkflowVersionORM.id == workflow.published_version_id,
                    WorkflowVersionORM.workflow_id == workflow.id,
                )
            )
            snapshot = result.scalar_one_or_none()
            if snapshot:
                return snapshot

        result = await self.session.execute(
            select(WorkflowVersionORM)
            .where(
                WorkflowVersionORM.workflow_id == workflow.id,
                WorkflowVersionORM.snapshot_type == "publish",
            )
            .order_by(WorkflowVersionORM.version.desc(), WorkflowVersionORM.created_at.desc())
        )
        snapshot = result.scalars().first()
        if snapshot:
            return snapshot

        return await self._backfill_published_snapshot(workflow)

    async def _get_version_snapshot(
        self,
        workflow_id: str,
        version_number: int,
    ) -> WorkflowVersionORM | None:
        result = await self.session.execute(
            select(WorkflowVersionORM)
            .where(
                WorkflowVersionORM.workflow_id == workflow_id,
                WorkflowVersionORM.version == version_number,
            )
            .order_by(WorkflowVersionORM.created_at.desc())
        )
        return result.scalars().first()

    def _extract_restore_provenance(
        self,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not metadata:
            return None

        provenance = metadata.get("restore_provenance")
        if not isinstance(provenance, dict):
            return None
        if not provenance.get("restored_from_version_id"):
            return None
        return dict(provenance)

    async def _backfill_published_snapshot(
        self,
        workflow: WorkflowDefinitionORM,
    ) -> WorkflowVersionORM | None:
        if not workflow.is_published:
            return None

        candidate = None
        if workflow.published_at:
            # 仅回填发布时间之前的快照，避免把后续草稿误判成已发布版本。
            result = await self.session.execute(
                select(WorkflowVersionORM)
                .where(
                    WorkflowVersionORM.workflow_id == workflow.id,
                    WorkflowVersionORM.created_at <= workflow.published_at,
                    WorkflowVersionORM.snapshot_type != "restore_backup",
                )
                .order_by(WorkflowVersionORM.version.desc(), WorkflowVersionORM.created_at.desc())
            )
            candidate = result.scalars().first()

        backfilled_at = utc_now_iso()
        if candidate:
            metadata_payload = dict(candidate.metadata_json or {})
            events = list(metadata_payload.get("events", []))
            events.append(
                {
                    "type": "publish_backfill",
                    "at": backfilled_at,
                    "backfilled_from_snapshot_id": candidate.id,
                    "backfilled_from_version": candidate.version,
                }
            )
            metadata_payload.update(
                {
                    "backfill_reason": "legacy_published_snapshot_missing",
                    "backfilled_from_snapshot_id": candidate.id,
                    "backfilled_from_version": candidate.version,
                    "events": events,
                }
            )
            snapshot = WorkflowVersionORM(
                id=str(uuid.uuid4()),
                workflow_id=workflow.id,
                version=candidate.version,
                name=candidate.name or workflow.name,
                description=candidate.description or "",
                nodes=candidate.nodes or [],
                edges=candidate.edges or [],
                change_log=candidate.change_log or f"回填已发布版本 v{candidate.version}",
                snapshot_type="publish",
                source_version_id=candidate.id,
                metadata_json=metadata_payload,
                created_by=workflow.published_by or candidate.created_by or workflow.created_by,
                created_at=workflow.published_at or utc_now_naive(),
            )
            self.session.add(snapshot)
            workflow.published_version_id = snapshot.id
            await self.session.commit()
            await self.session.refresh(workflow)
            return snapshot

        result = await self.session.execute(
            select(WorkflowVersionORM.id)
            .where(WorkflowVersionORM.workflow_id == workflow.id)
            .limit(1)
        )
        if result.scalar_one_or_none() is not None:
            return None

        snapshot = WorkflowVersionORM(
            id=str(uuid.uuid4()),
            workflow_id=workflow.id,
            version=workflow.version,
            name=workflow.name,
            description=workflow.description or "",
            nodes=workflow.nodes or [],
            edges=workflow.edges or [],
            change_log=f"回填已发布版本 v{workflow.version}",
            snapshot_type="publish",
            metadata_json={
                "backfill_reason": "legacy_published_without_versions",
                "events": [
                    {
                        "type": "publish_backfill",
                        "at": backfilled_at,
                        "backfilled_from": "workflow_definition_row",
                    }
                ],
            },
            created_by=workflow.published_by or workflow.created_by,
            created_at=workflow.published_at or utc_now_naive(),
        )
        self.session.add(snapshot)
        workflow.published_version_id = snapshot.id
        await self.session.commit()
        await self.session.refresh(workflow)
        return snapshot

    async def _load_version_payload(
        self,
        workflow: WorkflowDefinitionORM,
        version_number: int,
    ) -> dict[str, Any] | None:
        if workflow.version == version_number:
            return {
                "version": workflow.version,
                "name": workflow.name,
                "description": workflow.description or "",
                "nodes": workflow.nodes or [],
                "edges": workflow.edges or [],
            }

        result = await self.session.execute(
            select(WorkflowVersionORM)
            .where(
                WorkflowVersionORM.workflow_id == workflow.id,
                WorkflowVersionORM.version == version_number,
            )
            .order_by(WorkflowVersionORM.created_at.desc())
        )
        snapshot = result.scalars().first()
        if not snapshot:
            return None

        return {
            "version": snapshot.version,
            "name": snapshot.name,
            "description": snapshot.description,
            "nodes": snapshot.nodes or [],
            "edges": snapshot.edges or [],
        }

    async def _ensure_snapshot(
        self,
        workflow: WorkflowDefinitionORM,
        *,
        user_id: str,
        snapshot_type: str,
        change_log: str,
        metadata: dict[str, Any] | None = None,
        source_version_id: str | None = None,
        force_refresh: bool = False,
    ) -> WorkflowVersionORM:
        """为当前草稿版本创建或更新唯一快照。"""
        result = await self.session.execute(
            select(WorkflowVersionORM)
            .where(
                WorkflowVersionORM.workflow_id == workflow.id,
                WorkflowVersionORM.version == workflow.version,
            )
            .order_by(WorkflowVersionORM.created_at.desc())
        )
        snapshot = result.scalars().first()

        metadata_payload = dict(snapshot.metadata_json or {}) if snapshot else {}
        if metadata:
            event = dict(metadata)
            event_type = event.pop("event_type", snapshot_type)
            events = list(metadata_payload.get("events", []))
            events.append(
                {
                    "type": event_type,
                    "at": utc_now_iso(),
                    **event,
                }
            )
            metadata_payload.update(event)
            metadata_payload["events"] = events

        if snapshot is None:
            snapshot = WorkflowVersionORM(
                id=str(uuid.uuid4()),
                workflow_id=workflow.id,
                version=workflow.version,
                name=workflow.name,
                description=workflow.description or "",
                nodes=workflow.nodes or [],
                edges=workflow.edges or [],
                change_log=change_log,
                snapshot_type=snapshot_type,
                source_version_id=source_version_id,
                metadata_json=metadata_payload,
                created_by=user_id,
            )
            self.session.add(snapshot)
            return snapshot

        if force_refresh:
            snapshot.name = workflow.name
            snapshot.description = workflow.description or ""
            snapshot.nodes = workflow.nodes or []
            snapshot.edges = workflow.edges or []

        if change_log and (snapshot.snapshot_type != "publish" or snapshot_type == "publish"):
            snapshot.change_log = change_log
        if snapshot.snapshot_type != "publish" or snapshot_type == "publish":
            snapshot.snapshot_type = snapshot_type
        if source_version_id:
            snapshot.source_version_id = source_version_id
        if user_id and not snapshot.created_by:
            snapshot.created_by = user_id
        snapshot.metadata_json = metadata_payload
        return snapshot

    def _orm_to_model(
        self,
        orm: WorkflowDefinitionORM,
        *,
        snapshot: WorkflowVersionORM | None = None,
        published_snapshot: WorkflowVersionORM | None = None,
    ) -> WorkflowDefinition:
        source_name = snapshot.name if snapshot else orm.name
        source_description = snapshot.description if snapshot else orm.description
        source_nodes = snapshot.nodes if snapshot else orm.nodes
        source_edges = snapshot.edges if snapshot else orm.edges
        source_version = snapshot.version if snapshot else orm.version
        source_updated_at = orm.published_at if snapshot else orm.updated_at

        published_version = published_snapshot.version if published_snapshot else None

        return WorkflowDefinition(
            id=orm.id,
            name=source_name,
            description=source_description,
            version=source_version,
            nodes=[WorkflowNode(**node) for node in (source_nodes or [])],
            edges=[WorkflowEdge(**edge) for edge in (source_edges or [])],
            created_at=orm.created_at,
            updated_at=source_updated_at,
            created_by=orm.created_by,
            is_published=bool(orm.is_published),
            published_version_id=orm.published_version_id,
            published_version=published_version,
            published_at=orm.published_at,
            published_by=orm.published_by,
        )

    def _collect_reachable(
        self,
        seeds: set[str],
        adjacency: dict[str, list[str]],
    ) -> set[str]:
        visited = set(seeds)
        queue = deque(seeds)

        while queue:
            node_id = queue.popleft()
            for next_node in adjacency.get(node_id, []):
                if next_node in visited:
                    continue
                visited.add(next_node)
                queue.append(next_node)

        return visited

    def _has_cycle(
        self,
        nodes: list[WorkflowNode],
        edges: list[WorkflowEdge],
    ) -> bool:
        indegree = {node.id: 0 for node in nodes}
        adjacency: dict[str, list[str]] = defaultdict(list)

        for edge in edges:
            if edge.source not in indegree or edge.target not in indegree:
                continue
            adjacency[edge.source].append(edge.target)
            indegree[edge.target] += 1

        queue = deque(node_id for node_id, degree in indegree.items() if degree == 0)
        visited_count = 0

        while queue:
            node_id = queue.popleft()
            visited_count += 1
            for next_node in adjacency.get(node_id, []):
                indegree[next_node] -= 1
                if indegree[next_node] == 0:
                    queue.append(next_node)

        return visited_count != len(nodes)
