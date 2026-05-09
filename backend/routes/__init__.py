"""
路由模块初始化

导出所有 API 路由
"""

from .admin_routes import router as admin_router
from .auth_routes import router as auth_router
from .trace_routes import router as trace_router
from .workflow_routes import router as workflow_router
from .workspace_routes import router as workspace_router

__all__ = [
    "admin_router",
    "auth_router",
    "trace_router",
    "workflow_router",
    "workspace_router",
]
