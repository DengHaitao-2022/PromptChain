"""
WebSocket 实时状态推送

功能：
1. 工作流执行状态实时推送
2. 节点状态变更通知
3. 审批任务通知
"""

import asyncio
import logging
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from db.postgres_store import get_postgres_store
from models.auth_models import UserStatus
from routes.auth_routes import ACCESS_TOKEN_COOKIE
from services.artifact_store import get_artifact_store
from services.auth_service import AuthService, verify_access_token
from services.permission_service import PermissionService, is_admin_role

router = APIRouter(tags=["websocket"])
logger = logging.getLogger(__name__)


@dataclass
class _WSAuthContext:
    user_id: str
    workspace_id: str
    is_admin: bool


# 连接管理器
class ConnectionManager:
    """WebSocket连接管理器"""

    def __init__(self):
        # workflow_run_id -> set of connections
        self.workflow_connections: dict[str, set[WebSocket]] = {}
        # user_id -> set of connections (用于审批通知)
        self.user_connections: dict[str, set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, workflow_run_id: str):
        """建立连接"""
        await websocket.accept()
        if workflow_run_id not in self.workflow_connections:
            self.workflow_connections[workflow_run_id] = set()
        self.workflow_connections[workflow_run_id].add(websocket)

    async def connect_user(self, websocket: WebSocket, user_id: str):
        """建立用户连接（用于审批通知）"""
        await websocket.accept()
        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()
        self.user_connections[user_id].add(websocket)

    def disconnect(self, websocket: WebSocket, workflow_run_id: str):
        """断开连接"""
        if workflow_run_id in self.workflow_connections:
            self.workflow_connections[workflow_run_id].discard(websocket)
            if not self.workflow_connections[workflow_run_id]:
                del self.workflow_connections[workflow_run_id]

    def disconnect_user(self, websocket: WebSocket, user_id: str):
        """断开用户连接"""
        if user_id in self.user_connections:
            self.user_connections[user_id].discard(websocket)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]

    async def broadcast_workflow_status(self, workflow_run_id: str, message: dict):
        """向订阅特定工作流的所有连接广播消息"""
        if workflow_run_id in self.workflow_connections:
            dead_connections = set()
            for connection in self.workflow_connections[workflow_run_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    dead_connections.add(connection)

            # 清理断开的连接
            for dead in dead_connections:
                self.workflow_connections[workflow_run_id].discard(dead)

    async def notify_user(self, user_id: str, message: dict):
        """向特定用户发送通知"""
        if user_id in self.user_connections:
            dead_connections = set()
            for connection in self.user_connections[user_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    dead_connections.add(connection)

            for dead in dead_connections:
                self.user_connections[user_id].discard(dead)


# 全局连接管理器实例
manager = ConnectionManager()


def get_ws_manager() -> ConnectionManager:
    """获取WebSocket管理器实例"""
    return manager


async def _close_forbidden(websocket: WebSocket, reason: str) -> None:
    """拒绝 WebSocket 连接并返回策略违规状态码。"""
    await websocket.close(code=1008, reason=reason)


async def _authenticate_websocket(websocket: WebSocket) -> _WSAuthContext | None:
    """基于 access_token cookie 认证 WebSocket 连接。"""
    access_token = websocket.cookies.get(ACCESS_TOKEN_COOKIE)
    if not access_token:
        await _close_forbidden(websocket, "未登录或登录已过期")
        return None

    payload = verify_access_token(access_token)
    if not payload:
        await _close_forbidden(websocket, "无效访问令牌")
        return None

    user_id = payload.get("sub")
    if not user_id:
        await _close_forbidden(websocket, "访问令牌缺少用户标识")
        return None

    workspace_id = payload.get("workspace_id")

    store = get_postgres_store()
    async with store.async_session() as session:
        auth_service = AuthService(session)
        user = await auth_service.get_user_by_id(user_id)
        if not user:
            await _close_forbidden(websocket, "当前登录状态无效")
            return None
        if user.status == UserStatus.SUSPENDED.value:
            await _close_forbidden(websocket, "账号已被停用")
            return None
        if user.status != UserStatus.ACTIVE.value or not user.email_verified:
            await _close_forbidden(websocket, "账号尚未激活")
            return None

        if not workspace_id:
            memberships = await auth_service.get_user_workspaces(user_id)
            if not memberships:
                await _close_forbidden(websocket, "请先加入工作空间")
                return None
            workspace_id = memberships[0][1].id

        permission_service = PermissionService(session)
        try:
            role = await permission_service.require_permission(
                user_id,
                workspace_id,
                "workflow_run",
                "read",
            )
        except HTTPException as exc:
            await _close_forbidden(websocket, exc.detail)
            return None

    return _WSAuthContext(user_id=user_id, workspace_id=workspace_id, is_admin=is_admin_role(role))


async def _authorize_workflow_subscription(
    websocket: WebSocket,
    auth_context: _WSAuthContext,
    workflow_run_id: str,
) -> bool:
    """校验当前用户是否有权订阅指定 workflow_run。"""
    store = get_artifact_store()
    workflow_run = await store.get_workflow_run(workflow_run_id)
    if not workflow_run:
        await _close_forbidden(websocket, "Workflow not found")
        return False

    metadata = workflow_run.metadata or {}
    run_workspace_id = metadata.get("workspace_id")
    run_user_id = metadata.get("user_id")

    if not run_workspace_id or not run_user_id:
        await _close_forbidden(websocket, "该任务缺少归属信息，暂不允许订阅")
        return False
    if run_workspace_id != auth_context.workspace_id:
        await _close_forbidden(websocket, "您无权订阅该工作空间任务")
        return False
    if not auth_context.is_admin and run_user_id != auth_context.user_id:
        await _close_forbidden(websocket, "您只能订阅自己的任务")
        return False
    return True


# ==================== WebSocket 端点 ====================


@router.websocket("/ws/workflow/{workflow_run_id}")
async def workflow_websocket(websocket: WebSocket, workflow_run_id: str):
    """
    工作流实时状态 WebSocket

    客户端连接后会收到：
    - node_started: 节点开始执行
    - node_completed: 节点执行完成
    - node_failed: 节点执行失败
    - workflow_completed: 工作流完成
    - workflow_paused: 工作流暂停（等待人工审批）
    """
    auth_context = await _authenticate_websocket(websocket)
    if auth_context is None:
        return
    if not await _authorize_workflow_subscription(websocket, auth_context, workflow_run_id):
        return

    await manager.connect(websocket, workflow_run_id)

    try:
        # 发送连接确认
        await websocket.send_json(
            {
                "type": "connected",
                "workflow_run_id": workflow_run_id,
                "message": "已连接到工作流状态推送",
            }
        )

        # 保持连接并处理心跳
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0,  # 30秒超时
                )

                # 处理心跳
                if data == "ping":
                    await websocket.send_text("pong")

            except TimeoutError:
                # 发送心跳检查
                try:
                    await websocket.send_text("ping")
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("workflow websocket 连接异常: workflow_run_id=%s", workflow_run_id)
    finally:
        manager.disconnect(websocket, workflow_run_id)


@router.websocket("/ws/user/{user_id}")
async def user_websocket(websocket: WebSocket, user_id: str):
    """
    用户通知 WebSocket

    客户端连接后会收到：
    - approval_required: 有新的审批任务
    - approval_timeout: 审批即将超时
    - workflow_assigned: 有新的工作流分配
    """
    auth_context = await _authenticate_websocket(websocket)
    if auth_context is None:
        return
    if auth_context.user_id != user_id:
        await _close_forbidden(websocket, "仅允许订阅当前登录用户通道")
        return

    await manager.connect_user(websocket, user_id)

    try:
        await websocket.send_json(
            {"type": "connected", "user_id": user_id, "message": "已连接到用户通知"}
        )

        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)

                if data == "ping":
                    await websocket.send_text("pong")

            except TimeoutError:
                try:
                    await websocket.send_text("ping")
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("user websocket 连接异常: user_id=%s", user_id)
    finally:
        manager.disconnect_user(websocket, user_id)


# ==================== 工具函数 ====================


async def emit_node_status(
    workflow_run_id: str, node_id: str, status: str, data: dict | None = None
):
    """
    发送节点状态更新

    Args:
        workflow_run_id: 工作流运行ID
        node_id: 节点ID
        status: 状态 (started, completed, failed)
        data: 附加数据
    """
    message = {
        "type": f"node_{status}",
        "workflow_run_id": workflow_run_id,
        "node_id": node_id,
        "data": data or {},
    }
    await manager.broadcast_workflow_status(workflow_run_id, message)


async def emit_workflow_status(workflow_run_id: str, status: str, data: dict | None = None):
    """
    发送工作流状态更新

    Args:
        workflow_run_id: 工作流运行ID
        status: 状态 (completed, paused, failed)
        data: 附加数据
    """
    message = {"type": f"workflow_{status}", "workflow_run_id": workflow_run_id, "data": data or {}}
    await manager.broadcast_workflow_status(workflow_run_id, message)


async def notify_approval_required(
    user_id: str, approval_task_id: str, workflow_run_id: str, node_name: str, content_preview: str
):
    """
    通知用户有新的审批任务
    """
    message = {
        "type": "approval_required",
        "approval_task_id": approval_task_id,
        "workflow_run_id": workflow_run_id,
        "node_name": node_name,
        "content_preview": content_preview,
    }
    await manager.notify_user(user_id, message)
