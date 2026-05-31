"""
基于 Prompt Chain 的自动化内容生成系统 - FastAPI 应用入口

职责：
1. 创建 FastAPI 应用实例
2. 配置中间件（CORS 等）
3. 注册所有路由
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_settings


def create_app() -> FastAPI:
    """应用工厂"""
    settings = get_settings()

    application = FastAPI(
        title=settings.APP_TITLE,
        description=settings.APP_DESCRIPTION,
        version=settings.APP_VERSION,
        lifespan=_lifespan,
    )

    # CORS 中间件
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    _register_routes(application)
    return application


def _register_routes(application: FastAPI) -> None:
    """集中注册所有路由"""
    # 内容工作流 API
    from routes.workflow_routes import router as workflow_router

    # 统一在入口层补齐 /api 前缀，避免路由模块内部重复声明根路径
    application.include_router(workflow_router, prefix="/api", tags=["workflow"])

    # Trace / Artifact API
    from routes.trace_routes import router as trace_router

    # 统一在入口层补齐 /api 前缀，避免路由模块内部重复声明根路径
    application.include_router(trace_router, prefix="/api", tags=["trace"])

    # 认证路由
    from routes.auth_routes import router as auth_router

    application.include_router(auth_router, prefix="/api", tags=["auth"])

    # 工作空间路由
    from routes.workspace_routes import router as workspace_router

    application.include_router(workspace_router, prefix="/api", tags=["workspace"])

    # 后台管理路由
    from routes.admin_routes import router as admin_router

    application.include_router(admin_router, prefix="/api", tags=["admin"])

    # 工作流定义路由
    from routes.workflow_definition_routes import router as workflow_definition_router

    application.include_router(
        workflow_definition_router, prefix="/api", tags=["workflow-definition"]
    )

    # 版本管理路由
    from routes.workflow_version_routes import router as version_router

    application.include_router(version_router, prefix="/api", tags=["workflow-version"])

    # 知识库路由
    from routes.knowledge_routes import router as knowledge_router

    application.include_router(knowledge_router, prefix="/api", tags=["knowledge"])

    # WebSocket 路由
    from routes.websocket_routes import router as ws_router

    application.include_router(ws_router, tags=["websocket"])

    # 健康检查
    @application.get("/")
    async def root():
        """健康检查"""
        return {
            "status": "ok",
            "service": "PromptChain API",
            "version": get_settings().APP_VERSION,
        }


@asynccontextmanager
async def _lifespan(_application: FastAPI) -> AsyncIterator[None]:
    """集中管理应用启动和关闭资源。"""
    from db.postgres_store import dispose_postgres_store
    from services.knowledge_index_worker import (
        start_knowledge_index_worker,
        stop_knowledge_index_worker,
    )
    from services.workflow_event_bus import dispose_workflow_event_bus

    # 知识库普通上传走后台索引，避免请求线程长时间等待解析和 embedding。
    start_knowledge_index_worker()
    try:
        yield
    finally:
        # 热重载或进程退出时主动释放外部连接，减少残留失效连接。
        await stop_knowledge_index_worker()
        await dispose_workflow_event_bus()
        await dispose_postgres_store()


# 创建应用实例（uvicorn 入口）
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
    )
