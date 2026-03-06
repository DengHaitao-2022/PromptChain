"""
工作流定义服务

提供工作流定义的CRUD操作和验证功能
"""
from typing import Optional, List
from datetime import datetime
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

from models.workflow_definition import (
    WorkflowDefinition,
    WorkflowDefinitionCreate,
    WorkflowDefinitionUpdate,
    WorkflowValidationResult,
    WorkflowCompileResult,
    WorkflowNode,
    WorkflowEdge,
)
from models.workflow_orm import WorkflowDefinitionORM, WorkflowVersionORM


class WorkflowDefinitionService:
    """工作流定义服务"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(
        self,
        workspace_id: str,
        user_id: str,
        data: WorkflowDefinitionCreate
    ) -> WorkflowDefinition:
        """
        创建工作流定义
        """
        workflow = WorkflowDefinitionORM(
            id=str(uuid.uuid4()),
            name=data.name,
            description=data.description or "",
            version=1,
            nodes=[node.model_dump() for node in data.nodes],
            edges=[edge.model_dump() for edge in data.edges],
            workspace_id=workspace_id,
            created_by=user_id,
        )
        
        self.session.add(workflow)
        await self.session.commit()
        await self.session.refresh(workflow)
        
        return self._orm_to_model(workflow)
    
    async def get_by_id(
        self,
        workflow_id: str,
        workspace_id: str
    ) -> Optional[WorkflowDefinition]:
        """
        根据ID获取工作流定义
        """
        result = await self.session.execute(
            select(WorkflowDefinitionORM).where(
                WorkflowDefinitionORM.id == workflow_id,
                WorkflowDefinitionORM.workspace_id == workspace_id,
                WorkflowDefinitionORM.is_deleted == 0
            )
        )
        workflow = result.scalar_one_or_none()
        
        if not workflow:
            return None
        
        return self._orm_to_model(workflow)
    
    async def list_by_workspace(
        self,
        workspace_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[WorkflowDefinition]:
        """
        列出工作空间的所有工作流定义
        """
        result = await self.session.execute(
            select(WorkflowDefinitionORM)
            .where(
                WorkflowDefinitionORM.workspace_id == workspace_id,
                WorkflowDefinitionORM.is_deleted == 0
            )
            .order_by(WorkflowDefinitionORM.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        workflows = result.scalars().all()
        
        return [self._orm_to_model(w) for w in workflows]
    
    async def update(
        self,
        workflow_id: str,
        workspace_id: str,
        user_id: str,
        data: WorkflowDefinitionUpdate
    ) -> Optional[WorkflowDefinition]:
        """
        更新工作流定义
        """
        # 获取现有工作流
        result = await self.session.execute(
            select(WorkflowDefinitionORM).where(
                WorkflowDefinitionORM.id == workflow_id,
                WorkflowDefinitionORM.workspace_id == workspace_id,
                WorkflowDefinitionORM.is_deleted == 0
            )
        )
        workflow = result.scalar_one_or_none()
        
        if not workflow:
            return None
        
        # 保存版本历史
        version_record = WorkflowVersionORM(
            id=str(uuid.uuid4()),
            workflow_id=workflow.id,
            version=workflow.version,
            nodes=workflow.nodes,
            edges=workflow.edges,
            created_by=user_id,
        )
        self.session.add(version_record)
        
        # 更新字段
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
    
    async def delete(
        self,
        workflow_id: str,
        workspace_id: str
    ) -> bool:
        """
        软删除工作流定义
        """
        result = await self.session.execute(
            update(WorkflowDefinitionORM)
            .where(
                WorkflowDefinitionORM.id == workflow_id,
                WorkflowDefinitionORM.workspace_id == workspace_id
            )
            .values(is_deleted=1, updated_at=datetime.utcnow())
        )
        await self.session.commit()
        
        return result.rowcount > 0
    
    def validate(self, definition: WorkflowDefinition) -> WorkflowValidationResult:
        """
        验证工作流定义的合法性
        """
        errors = []
        warnings = []
        
        # 检查是否有节点
        if not definition.nodes:
            errors.append("工作流必须至少包含一个节点")
        
        # 检查是否有输入节点
        input_nodes = [n for n in definition.nodes if n.type == "input"]
        if not input_nodes:
            errors.append("工作流必须包含至少一个输入节点")
        elif len(input_nodes) > 1:
            warnings.append("工作流包含多个输入节点，可能导致执行顺序不确定")
        
        # 检查是否有输出节点
        output_nodes = [n for n in definition.nodes if n.type == "output"]
        if not output_nodes:
            warnings.append("工作流没有输出节点，可能无法正确输出结果")
        
        # 检查节点ID唯一性
        node_ids = [n.id for n in definition.nodes]
        if len(node_ids) != len(set(node_ids)):
            errors.append("存在重复的节点ID")
        
        # 检查边的有效性
        for edge in definition.edges:
            if edge.source not in node_ids:
                errors.append(f"边 {edge.id} 的源节点 {edge.source} 不存在")
            if edge.target not in node_ids:
                errors.append(f"边 {edge.id} 的目标节点 {edge.target} 不存在")
        
        # 检查是否有孤立节点
        connected_nodes = set()
        for edge in definition.edges:
            connected_nodes.add(edge.source)
            connected_nodes.add(edge.target)
        
        for node in definition.nodes:
            if node.id not in connected_nodes and node.type not in ["input", "output"]:
                warnings.append(f"节点 {node.data.label} ({node.id}) 是孤立的，没有连接")
        
        return WorkflowValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    def compile(self, definition: WorkflowDefinition) -> WorkflowCompileResult:
        """
        将工作流定义编译为LangGraph代码预览
        """
        # 首先验证
        validation = self.validate(definition)
        if not validation.is_valid:
            return WorkflowCompileResult(
                success=False,
                errors=validation.errors
            )
        
        # 生成代码预览
        code_lines = [
            "from langgraph.graph import StateGraph, END",
            "from typing import TypedDict, Annotated",
            "",
            "# 定义状态",
            "class WorkflowState(TypedDict):",
            "    messages: list",
            "    current_step: str",
            "",
            "# 创建图",
            f"graph = StateGraph(WorkflowState)",
            "",
            "# 添加节点",
        ]
        
        for node in definition.nodes:
            node_type = node.type
            node_name = node.id.replace("-", "_")
            code_lines.append(f"graph.add_node('{node_name}', {node_type}_handler)")
        
        code_lines.append("")
        code_lines.append("# 添加边")
        
        for edge in definition.edges:
            source = edge.source.replace("-", "_")
            target = edge.target.replace("-", "_")
            code_lines.append(f"graph.add_edge('{source}', '{target}')")
        
        code_lines.append("")
        code_lines.append("# 设置入口")
        if input_nodes := [n for n in definition.nodes if n.type == "input"]:
            entry = input_nodes[0].id.replace("-", "_")
            code_lines.append(f"graph.set_entry_point('{entry}')")
        
        code_lines.append("")
        code_lines.append("# 编译图")
        code_lines.append("workflow = graph.compile()")
        
        return WorkflowCompileResult(
            success=True,
            graph_code="\n".join(code_lines)
        )
    
    def _orm_to_model(self, orm: WorkflowDefinitionORM) -> WorkflowDefinition:
        """ORM转Pydantic模型"""
        return WorkflowDefinition(
            id=orm.id,
            name=orm.name,
            description=orm.description,
            version=orm.version,
            nodes=[WorkflowNode(**n) for n in (orm.nodes or [])],
            edges=[WorkflowEdge(**e) for e in (orm.edges or [])],
            created_at=orm.created_at,
            updated_at=orm.updated_at,
            created_by=orm.created_by,
        )
