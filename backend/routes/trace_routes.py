"""
Trace / Artifact API 路由

提供工作流追踪、节点详情、产物查看等接口
"""

import logging

from fastapi import APIRouter, HTTPException, Request

import routes.workflow_helpers as workflow_helpers
from routes.workflow_helpers import (
    _extract_workflow_status,
    _get_graph_state,
    _normalize_trace_payload,
)

router = APIRouter(prefix="/api", tags=["trace"])
logger = logging.getLogger(__name__)
INTERNAL_SERVER_ERROR = "Internal server error"


@router.get("/trace/{workflow_run_id}")
async def get_workflow_trace(workflow_run_id: str, request: Request):
    """获取工作流完整追踪"""
    from graph import get_workflow
    from services import get_artifact_store, get_trace_service

    try:
        await workflow_helpers.require_workflow_run_access(request, workflow_run_id)
        trace_service = get_trace_service()
        trace = await trace_service.get_workflow_trace(workflow_run_id)
        store = get_artifact_store()
        workflow_run = await store.get_workflow_run(workflow_run_id)
        if not workflow_run:
            raise ValueError(f"WorkflowRun not found: {workflow_run_id}")

        workflow = get_workflow()
        graph_state = await _get_graph_state(workflow, workflow_run_id)
        status = _extract_workflow_status(workflow, workflow_run, graph_state)

        return _normalize_trace_payload(
            trace,
            workflow_run=workflow_run,
            graph_state=graph_state,
            status=status,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("获取工作流追踪失败: workflow_run_id=%s", workflow_run_id)
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR) from exc


@router.get("/trace/node/{node_run_id}")
async def get_node_detail(node_run_id: str, request: Request):
    """获取节点运行详情"""
    from services import get_trace_service

    try:
        await workflow_helpers.require_node_run_access(request, node_run_id)
        trace_service = get_trace_service()
        detail = await trace_service.get_node_detail(node_run_id)
        return detail
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("获取节点详情失败: node_run_id=%s", node_run_id)
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR) from exc


@router.get("/artifact/{artifact_id}")
async def get_artifact(artifact_id: str, request: Request):
    """获取 Artifact 详情"""
    artifact = await workflow_helpers.require_artifact_access(request, artifact_id)
    return artifact.model_dump()


@router.get("/artifact/{artifact_id}/history")
async def get_artifact_history(artifact_id: str, request: Request):
    """获取 Artifact 版本历史"""
    from services import get_trace_service

    try:
        await workflow_helpers.require_artifact_access(request, artifact_id)
        trace_service = get_trace_service()
        history = await trace_service.get_artifact_history(artifact_id)
        return history
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("获取 Artifact 历史失败: artifact_id=%s", artifact_id)
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR) from exc
