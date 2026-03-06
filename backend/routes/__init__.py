"""
路由模块初始化

导出所有 API 路由
"""
from .auth_routes import router as auth_router
from .workspace_routes import router as workspace_router
from .admin_routes import router as admin_router

__all__ = [
    "auth_router",
    "workspace_router",
    "admin_router",
]
