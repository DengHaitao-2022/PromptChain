"""
基于 Prompt Chain 的自动化内容生成系统 - FastAPI 入口

主要功能：
1. /api/workflow - 工作流 API（启动、恢复、审批）
2. /api/trace - Trace 回放 API
3. WebSocket - 实时状态推送
"""
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
import os
from dotenv import load_dotenv

load_dotenv()

# 创建 FastAPI 应用
app = FastAPI(
    title="PromptChain API",
    description="基于 Prompt Chain 的自动化内容生成系统",
    version="1.0.0"
)

# CORS 配置（开发环境允许所有来源）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== 注册路由 ====================

# 认证路由
from routes.auth_routes import get_current_user, router as auth_router
app.include_router(auth_router, prefix="/api", tags=["auth"])

# 工作空间路由
from routes.workspace_routes import router as workspace_router
app.include_router(workspace_router, prefix="/api", tags=["workspace"])

# 后台管理路由
from routes.admin_routes import router as admin_router
app.include_router(admin_router, prefix="/api", tags=["admin"])

# 工作流定义路由
from routes.workflow_definition_routes import router as workflow_definition_router
app.include_router(workflow_definition_router, prefix="/api", tags=["workflow-definition"])

# WebSocket 路由
from routes.websocket_routes import router as ws_router
app.include_router(ws_router, tags=["websocket"])

# 版本管理路由
from routes.workflow_version_routes import router as version_router
app.include_router(version_router, prefix="/api", tags=["workflow-version"])


# ==================== 请求/响应模型 ====================

class StartWorkflowRequest(BaseModel):
    """启动工作流请求"""
    user_input: str


class ApproveOutlineRequest(BaseModel):
    """提纲审批请求"""
    action: str  # "approve" | "modify" | "regenerate"
    feedback: Optional[str] = ""
    modified_outline: Optional[Dict[str, Any]] = None


class ClarifyRequest(BaseModel):
    """澄清回答请求"""
    clarifications: Dict[str, str]  # {field: answer}


class ApproveFactCheckRequest(BaseModel):
    """事实核查审批请求"""
    decisions: Dict[str, str]
    manual_corrections: Dict[str, str] = {}


class WorkflowResponse(BaseModel):
    """工作流响应"""
    workflow_run_id: str
    status: str
    state: Dict[str, Any]


async def require_workspace_permission(user: dict, resource: str, action: str) -> str:
    """按当前 access_token 中的工作空间上下文校验权限。"""
    from db.postgres_store import get_postgres_store
    from services.permission_service import PermissionService

    user_id = user.get("sub") or user.get("id")
    workspace_id = user.get("workspace_id")

    if not user_id:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")

    if not workspace_id:
        raise HTTPException(status_code=400, detail="请先选择工作空间")

    store = get_postgres_store()
    async with store.async_session() as session:
        permission_service = PermissionService(session)
        await permission_service.require_permission(user_id, workspace_id, resource, action)

    return workspace_id


# ==================== API 路由 ====================

@app.get("/")
async def root():
    """健康检查"""
    return {
        "status": "ok",
        "service": "PromptChain API",
        "version": "1.0.0"
    }


@app.post("/api/workflow/start", response_model=WorkflowResponse)
async def start_workflow(request: StartWorkflowRequest, user: dict = Depends(get_current_user)):
    """
    启动新的内容生成工作流

    工作流会在需要用户输入时暂停：
    - needs_clarification: 需要澄清信息
    - awaiting_outline_approval: 等待提纲审批
    """
    from graph import get_workflow

    try:
        await require_workspace_permission(user, "workflow", "execute")
        workflow = get_workflow()
        result = await workflow.start(request.user_input)

        # 简化状态返回（移除大型对象的详细内容）
        simplified_state = _simplify_state(result["state"])

        return WorkflowResponse(
            workflow_run_id=result["workflow_run_id"],
            status=result["status"],
            state=simplified_state
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/workflow/{workflow_run_id}/approve-outline", response_model=WorkflowResponse)
async def approve_outline(
    workflow_run_id: str,
    request: ApproveOutlineRequest,
    user: dict = Depends(get_current_user),
):
    """
    处理提纲审批

    action 可选值：
    - approve: 确认提纲
    - modify: 修改提纲（需提供 modified_outline）
    - regenerate: 重新生成（可提供 feedback）
    """
    from graph import get_workflow

    try:
        await require_workspace_permission(user, "workflow", "execute")
        workflow = get_workflow()
        result = await workflow.approve_outline(
            workflow_run_id=workflow_run_id,
            action=request.action,
            feedback=request.feedback or "",
            modified_outline=request.modified_outline
        )

        simplified_state = _simplify_state(result["state"])

        return WorkflowResponse(
            workflow_run_id=result["workflow_run_id"],
            status=result["status"],
            state=simplified_state
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/workflow/{workflow_run_id}/clarify", response_model=WorkflowResponse)
async def clarify_intent(
    workflow_run_id: str,
    request: ClarifyRequest,
    user: dict = Depends(get_current_user),
):
    """提供澄清回答"""
    from graph import get_workflow

    try:
        await require_workspace_permission(user, "workflow", "execute")
        workflow = get_workflow()
        result = await workflow.resume(
            workflow_run_id=workflow_run_id,
            user_input={"user_clarifications": request.clarifications}
        )

        simplified_state = _simplify_state(result["state"])

        return WorkflowResponse(
            workflow_run_id=result["workflow_run_id"],
            status=result["status"],
            state=simplified_state
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/workflow/{workflow_run_id}/approve-fact-check", response_model=WorkflowResponse)
async def approve_fact_check(
    workflow_run_id: str,
    request: ApproveFactCheckRequest,
    user: dict = Depends(get_current_user),
):
    """处理事实核查高风险项审批"""
    from graph import get_workflow

    try:
        await require_workspace_permission(user, "workflow", "execute")
        workflow = get_workflow()
        result = await workflow.resume(
            workflow_run_id=workflow_run_id,
            user_input={
                "fact_check_decisions": request.decisions,
                "manual_corrections": request.manual_corrections,
                "awaiting_fact_check_approval": False,
            },
        )

        return WorkflowResponse(
            workflow_run_id=result["workflow_run_id"],
            status=result["status"],
            state=_simplify_state(result["state"]),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/workflow/{workflow_run_id}", response_model=WorkflowResponse)
async def get_workflow_status(workflow_run_id: str, user: dict = Depends(get_current_user)):
    """获取工作流状态"""
    from services import get_artifact_store
    from graph import get_workflow

    store = get_artifact_store()
    await require_workspace_permission(user, "workflow_run", "read")
    workflow_run = await store.get_workflow_run(workflow_run_id)

    if not workflow_run:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflow = get_workflow()
    graph_state = await _get_graph_state(workflow, workflow_run_id)
    status = _extract_workflow_status(workflow, workflow_run, graph_state)

    return WorkflowResponse(
        workflow_run_id=workflow_run_id,
        status=status,
        state=_simplify_state(graph_state),
    )


# ==================== Trace API ====================

@app.get("/api/trace/{workflow_run_id}")
async def get_workflow_trace(workflow_run_id: str, user: dict = Depends(get_current_user)):
    """获取工作流完整追踪"""
    from services import get_trace_service

    try:
        await require_workspace_permission(user, "workflow_run", "read")
        trace_service = get_trace_service()
        trace = await trace_service.get_workflow_trace(workflow_run_id)
        return trace
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trace/node/{node_run_id}")
async def get_node_detail(node_run_id: str, user: dict = Depends(get_current_user)):
    """获取节点运行详情"""
    from services import get_trace_service

    try:
        await require_workspace_permission(user, "workflow_run", "read")
        trace_service = get_trace_service()
        detail = await trace_service.get_node_detail(node_run_id)
        return detail
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/artifact/{artifact_id}")
async def get_artifact(artifact_id: str, user: dict = Depends(get_current_user)):
    """获取 Artifact 详情"""
    from services import get_artifact_store

    await require_workspace_permission(user, "workflow_run", "read")
    store = get_artifact_store()
    artifact = await store.get_artifact(artifact_id)

    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    return artifact.model_dump()


@app.get("/api/artifact/{artifact_id}/history")
async def get_artifact_history(artifact_id: str, user: dict = Depends(get_current_user)):
    """获取 Artifact 版本历史"""
    from services import get_trace_service

    try:
        await require_workspace_permission(user, "workflow_run", "read")
        trace_service = get_trace_service()
        history = await trace_service.get_artifact_history(artifact_id)
        return history
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/workflow/{workflow_run_id}/rerun-options")
async def get_rerun_options(workflow_run_id: str, user: dict = Depends(get_current_user)):
    """获取可重跑的节点列表"""
    from services import get_rerun_service

    try:
        await require_workspace_permission(user, "workflow_run", "read")
        rerun_service = get_rerun_service()
        options = await rerun_service.get_rerun_options(workflow_run_id)
        return {"options": options}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class RerunRequest(BaseModel):
    """重跑请求"""
    from_node: str
    updated_input: Optional[Dict[str, Any]] = None
    reason: Optional[str] = ""


@app.post("/api/workflow/{workflow_run_id}/rerun")
async def rerun_workflow(
    workflow_run_id: str,
    request: RerunRequest,
    user: dict = Depends(get_current_user),
):
    """
    从指定节点重跑工作流

    创建新的工作流运行，保留指定节点之前的所有Artifact
    """
    from services import get_rerun_service
    from graph import get_workflow

    try:
        await require_workspace_permission(user, "workflow", "execute")
        rerun_service = get_rerun_service()

        # 1. 准备重跑状态
        preserved_state = await rerun_service.prepare_rerun_state(
            workflow_run_id,
            request.from_node,
            request.updated_input
        )

        # 2. 创建新的 WorkflowRun
        new_workflow_run = await rerun_service.create_rerun_workflow(
            workflow_run_id,
            request.from_node,
            request.reason or ""
        )

        # 3. 使用新的工作流执行器恢复执行
        workflow = get_workflow()
        result = await workflow.resume(
            new_workflow_run.id,
            preserved_state
        )

        simplified_state = _simplify_state(result["state"])

        return {
            "original_workflow_run_id": workflow_run_id,
            "new_workflow_run_id": new_workflow_run.id,
            "rerun_from_node": request.from_node,
            "status": result["status"],
            "state": simplified_state
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/workflow/{workflow_run_id}/rerun-history")
async def get_rerun_history(workflow_run_id: str, user: dict = Depends(get_current_user)):
    """获取工作流的重跑历史"""
    from services import get_rerun_service

    try:
        await require_workspace_permission(user, "workflow_run", "read")
        rerun_service = get_rerun_service()
        history = await rerun_service.get_rerun_history(workflow_run_id)
        return {"history": history}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 工具函数 ====================

def _simplify_state(state: dict) -> dict:
    """简化状态返回，移除大型对象"""
    simplified = {}

    for key, value in state.items():
        if key in ["intent_card", "outline"]:
            # Pydantic 模型转换为 dict
            if hasattr(value, "model_dump"):
                simplified[key] = value.model_dump()
            else:
                simplified[key] = value
        elif key in ["draft_sections", "final_content"]:
            # 仅返回章节ID和字数预览
            if isinstance(value, dict):
                simplified[key] = {
                    section_id: {
                        "preview": content[:100] + "..." if len(content) > 100 else content,
                        "word_count": len(content)
                    }
                    for section_id, content in value.items()
                }
            else:
                simplified[key] = value
        elif key in ["clarification_questions"]:
            # 转换 Uncertainty 对象
            if isinstance(value, list):
                simplified[key] = _normalize_clarification_questions(value)
            else:
                simplified[key] = value
        else:
            simplified[key] = value

    return simplified


async def _get_graph_state(workflow: Any, workflow_run_id: str) -> dict:
    """从图检查点读取最新状态，失败时返回空状态。"""
    config = {"configurable": {"thread_id": workflow_run_id}}
    try:
        snapshot = await workflow.graph.aget_state(config)
        if snapshot and isinstance(snapshot.values, dict):
            return snapshot.values
    except Exception:
        pass
    return {}


def _extract_workflow_status(workflow: Any, workflow_run: Any, graph_state: dict) -> str:
    """优先使用图状态推导状态，缺失时回退到 WorkflowRun 状态字段。"""
    if graph_state:
        return workflow._get_workflow_status(graph_state)

    raw_status = getattr(workflow_run, "status", "running")
    if hasattr(raw_status, "value"):
        return str(raw_status.value)
    return str(raw_status)


def _map_clarification_priority(value: Any) -> str:
    """把后端数值优先级映射为前端枚举优先级。"""
    if isinstance(value, str):
        if value in {"high", "medium", "low"}:
            return value
        try:
            value = int(value)
        except ValueError:
            return "low"

    if isinstance(value, int):
        if value <= 2:
            return "high"
        if value == 3:
            return "medium"
        return "low"

    return "low"


def _normalize_clarification_questions(items: list[Any]) -> list[dict]:
    """统一澄清问题输出结构与优先级枚举。"""
    normalized: list[dict] = []
    for item in items:
        if hasattr(item, "model_dump"):
            question = item.model_dump()
        elif isinstance(item, dict):
            question = item
        else:
            continue

        normalized.append(
            {
                "field": question.get("field"),
                "question": question.get("question"),
                "priority": _map_clarification_priority(question.get("priority", 5)),
                "default_assumption": question.get("default_assumption"),
            }
        )
    return normalized


# ==================== 启动 ====================

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    debug = os.getenv("DEBUG", "true").lower() == "true"

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=debug
    )
