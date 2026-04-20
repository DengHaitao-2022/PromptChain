"""兼容导出：统一使用 orm/workflow_orm 作为 ORM 单一事实源。"""

from orm.workflow_orm import WorkflowDefinitionORM, WorkflowVersionORM

__all__ = ["WorkflowDefinitionORM", "WorkflowVersionORM"]
