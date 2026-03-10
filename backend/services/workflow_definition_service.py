"""
工作流定义服务

提供工作流定义的 CRUD、校验、发布和版本管理能力。
"""
from collections import defaultdict, deque
from datetime import datetime
import uuid
from typing import Any, Optional

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

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

_REQUIRED_NODE_CONFIG_FIELDS: dict[str, list[str]] = {
    "process": ["modelName"],
    "gate": ["gateType", "timeout"],
    "checker": ["confidenceThreshold"],
    "output": ["outputFormat"],
}

_POSTGRES_SCHEMA_STATEMENTS = (
    "ALTER TABLE workflow_definitions ADD COLUMN IF NOT EXISTS published_version_id VARCHAR(36)",
    "ALTER TABLE workflow_definitions ADD COLUMN IF NOT EXISTS published_at TIMESTAMP",
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
    ) -> Optional[WorkflowDefinition]:
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
        published_snapshot = await self._get_published_snapshot(workflow) if workflow.is_published else None
        if use_published_snapshot:
            snapshot = published_snapshot
            if published_only and not snapshot and not workflow.is_published:
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
            published_snapshot = await self._get_published_snapshot(workflow) if workflow.is_published else None
            snapshot = published_snapshot if use_published_snapshot else None
            items.append(
                self._orm_to_model(
                    workflow,
                    snapshot=snapshot,
                    published_snapshot=published_snapshot,
                )
            )
        return items

    async def update(
        self,
        workflow_id: str,
        workspace_id: str,
        user_id: str,
        data: WorkflowDefinitionUpdate,
    ) -> Optional[WorkflowDefinition]:
        """保存工作流草稿。"""
        await self.ensure_schema(self.session)

        workflow = await self._get_definition_orm(workflow_id=workflow_id, workspace_id=workspace_id)
        if not workflow:
            return None

        await self._ensure_snapshot(
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

        if data.name is not None:
            workflow.name = data.name
        if data.description is not None:
            workflow.description = data.description
        if data.nodes is not None:
            workflow.nodes = [node.model_dump() for node in data.nodes]
        if data.edges is not None:
            workflow.edges = [edge.model_dump() for edge in data.edges]

        workflow.version += 1
        workflow.updated_at = datetime.utcnow()

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
    ) -> tuple[Optional[WorkflowDefinition], WorkflowValidationResult, Optional[WorkflowVersionORM]]:
        """发布工作流当前草稿。"""
        await self.ensure_schema(self.session)

        workflow = await self._get_definition_orm(workflow_id=workflow_id, workspace_id=workspace_id)
        if not workflow:
            return None, WorkflowValidationResult(
                mode=WorkflowValidationMode.PUBLISH,
                is_valid=False,
                errors=["工作流不存在"],
            ), None

        definition = self._orm_to_model(workflow)
        validation = self.validate(definition, mode=WorkflowValidationMode.PUBLISH)
        if not validation.is_valid:
            return definition, validation, None

        published_at = datetime.utcnow()
        snapshot = await self._ensure_snapshot(
            workflow,
            user_id=user_id,
            snapshot_type="publish",
            change_log=change_log or f"发布版本 v{workflow.version}",
            metadata={
                "event_type": "publish",
                "published_at": published_at.isoformat(),
                "published_by": user_id,
                "published_version": workflow.version,
            },
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
    ) -> tuple[Optional[WorkflowDefinitionORM], list[WorkflowVersionORM]]:
        """获取工作流版本历史。"""
        await self.ensure_schema(self.session)

        workflow = await self._get_definition_orm(workflow_id=workflow_id, workspace_id=workspace_id)
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
    ) -> tuple[Optional[WorkflowDefinitionORM], Optional[WorkflowVersionORM]]:
        """获取指定版本快照。"""
        await self.ensure_schema(self.session)

        workflow = await self._get_definition_orm(workflow_id=workflow_id, workspace_id=workspace_id)
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
    ) -> Optional[dict[str, Any]]:
        """对比两个版本的差异。"""
        await self.ensure_schema(self.session)

        workflow = await self._get_definition_orm(workflow_id=workflow_id, workspace_id=workspace_id)
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
    ) -> tuple[Optional[WorkflowDefinition], Optional[WorkflowVersionORM]]:
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
        workflow.version += 1
        workflow.updated_at = datetime.utcnow()

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
            .values(is_deleted=1, updated_at=datetime.utcnow())
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

        input_nodes = [node for node in definition.nodes if node.type == "input"]
        output_nodes = [node for node in definition.nodes if node.type == "output"]
        process_nodes = [node for node in definition.nodes if node.type == "process"]
        gate_nodes = [node for node in definition.nodes if node.type == "gate"]

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
            if not label:
                errors.append(f"节点 {node.id} 缺少名称")

            if node.id not in incoming and node.type not in {"input"}:
                if mode == WorkflowValidationMode.PUBLISH:
                    errors.append(f"节点 {label or node.id} 没有上游连接")
                else:
                    warnings.append(f"节点 {label or node.id} 没有上游连接")

            if node.id not in outgoing and node.type not in {"output"}:
                if mode == WorkflowValidationMode.PUBLISH:
                    errors.append(f"节点 {label or node.id} 没有下游连接")
                else:
                    warnings.append(f"节点 {label or node.id} 没有下游连接")

            if node.id not in incoming and node.id not in outgoing and node.type not in {"input", "output"}:
                warnings.append(f"节点 {label or node.id} 是孤立节点，没有连接")

            if mode == WorkflowValidationMode.PUBLISH:
                config = node.data.config or {}
                required_fields = _REQUIRED_NODE_CONFIG_FIELDS.get(node.type, [])
                missing_fields = [
                    field
                    for field in required_fields
                    if config.get(field) in (None, "", [])
                ]
                if missing_fields:
                    errors.append(
                        f"节点 {label or node.id} 缺少必要配置：{', '.join(missing_fields)}"
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
                errors.append(f"存在无法从输入节点到达的节点：{', '.join(unreachable)}")
            if dead_end:
                errors.append(f"存在无法流向输出节点的节点：{', '.join(dead_end)}")

            if input_nodes and output_nodes and not (reachable_from_input & exit_ids):
                errors.append("发布前至少需要一条从输入节点到输出节点的完整路径")

        return WorkflowValidationResult(
            mode=mode,
            is_valid=not errors,
            errors=errors,
            warnings=warnings,
        )

    def compile(self, definition: WorkflowDefinition) -> WorkflowCompileResult:
        """将工作流定义编译为 LangGraph 代码预览。"""
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
            "# 添加节点",
        ]

        for node in definition.nodes:
            node_name = node.id.replace("-", "_")
            code_lines.append(f"graph.add_node('{node_name}', {node.type}_handler)")

        code_lines.append("")
        code_lines.append("# 添加边")
        for edge in definition.edges:
            source = edge.source.replace("-", "_")
            target = edge.target.replace("-", "_")
            code_lines.append(f"graph.add_edge('{source}', '{target}')")

        if input_nodes := [node for node in definition.nodes if node.type == "input"]:
            entry = input_nodes[0].id.replace("-", "_")
            code_lines.extend(["", "# 设置入口", f"graph.set_entry_point('{entry}')"])

        code_lines.extend(["", "# 编译图", "workflow = graph.compile()"])
        return WorkflowCompileResult(success=True, graph_code="\n".join(code_lines))

    def version_to_dict(
        self,
        version: WorkflowVersionORM,
        *,
        published_version_id: Optional[str] = None,
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
            "created_at": version.created_at.isoformat() if version.created_at else None,
            "is_current_published": version.id == published_version_id,
            "metadata": metadata,
        }

    async def _get_definition_orm(
        self,
        *,
        workflow_id: str,
        workspace_id: str,
        published_only: bool = False,
    ) -> Optional[WorkflowDefinitionORM]:
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
    ) -> Optional[WorkflowVersionORM]:
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
        return result.scalars().first()

    async def _load_version_payload(
        self,
        workflow: WorkflowDefinitionORM,
        version_number: int,
    ) -> Optional[dict[str, Any]]:
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
        metadata: Optional[dict[str, Any]] = None,
        source_version_id: Optional[str] = None,
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
                    "at": datetime.utcnow().isoformat(),
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
        snapshot: Optional[WorkflowVersionORM] = None,
        published_snapshot: Optional[WorkflowVersionORM] = None,
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
