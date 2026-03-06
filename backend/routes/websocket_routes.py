"""
WebSocket 实时状态推送

功能：
1. 工作流执行状态实时推送
2. 节点状态变更通知
3. 审批任务通知
"""
from typing import Dict, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import asyncio

router = APIRouter(tags=["websocket"])


# 连接管理器
class ConnectionManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        # workflow_run_id -> set of connections
        self.workflow_connections: Dict[str, Set[WebSocket]] = {}
        # user_id -> set of connections (用于审批通知)
        self.user_connections: Dict[str, Set[WebSocket]] = {}
    
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
    
    async def broadcast_workflow_status(
        self,
        workflow_run_id: str,
        message: dict
    ):
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
    await manager.connect(websocket, workflow_run_id)
    
    try:
        # 发送连接确认
        await websocket.send_json({
            "type": "connected",
            "workflow_run_id": workflow_run_id,
            "message": "已连接到工作流状态推送"
        })
        
        # 保持连接并处理心跳
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0  # 30秒超时
                )
                
                # 处理心跳
                if data == "ping":
                    await websocket.send_text("pong")
                    
            except asyncio.TimeoutError:
                # 发送心跳检查
                try:
                    await websocket.send_text("ping")
                except Exception:
                    break
                    
    except WebSocketDisconnect:
        pass
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
    await manager.connect_user(websocket, user_id)
    
    try:
        await websocket.send_json({
            "type": "connected",
            "user_id": user_id,
            "message": "已连接到用户通知"
        })
        
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0
                )
                
                if data == "ping":
                    await websocket.send_text("pong")
                    
            except asyncio.TimeoutError:
                try:
                    await websocket.send_text("ping")
                except Exception:
                    break
                    
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_user(websocket, user_id)


# ==================== 工具函数 ====================

async def emit_node_status(
    workflow_run_id: str,
    node_id: str,
    status: str,
    data: dict = None
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
        "data": data or {}
    }
    await manager.broadcast_workflow_status(workflow_run_id, message)


async def emit_workflow_status(
    workflow_run_id: str,
    status: str,
    data: dict = None
):
    """
    发送工作流状态更新
    
    Args:
        workflow_run_id: 工作流运行ID
        status: 状态 (completed, paused, failed)
        data: 附加数据
    """
    message = {
        "type": f"workflow_{status}",
        "workflow_run_id": workflow_run_id,
        "data": data or {}
    }
    await manager.broadcast_workflow_status(workflow_run_id, message)


async def notify_approval_required(
    user_id: str,
    approval_task_id: str,
    workflow_run_id: str,
    node_name: str,
    content_preview: str
):
    """
    通知用户有新的审批任务
    """
    message = {
        "type": "approval_required",
        "approval_task_id": approval_task_id,
        "workflow_run_id": workflow_run_id,
        "node_name": node_name,
        "content_preview": content_preview
    }
    await manager.notify_user(user_id, message)
