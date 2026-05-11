'use client';

import { useEffect, useRef, useCallback, useState } from 'react';
import { webSocketUrl } from '@/lib/api-config';

// ==================== 类型定义 ====================

export interface NodeStatusEvent {
  type: 'node_started' | 'node_completed' | 'node_failed';
  workflow_run_id: string;
  node_id: string;
  data?: Record<string, unknown>;
}

export interface WorkflowStatusEvent {
  type: 'workflow_completed' | 'workflow_paused' | 'workflow_failed';
  workflow_run_id: string;
  data?: Record<string, unknown>;
}

export interface ApprovalEvent {
  type: 'approval_required' | 'approval_timeout';
  approval_task_id: string;
  workflow_run_id: string;
  node_name: string;
  content_preview?: string;
}

export type WSEvent = NodeStatusEvent | WorkflowStatusEvent | ApprovalEvent | { type: string; [key: string]: unknown };

// ==================== Hook ====================

export function useWorkflowWebSocket(
  workflowRunId: string | null,
  onEvent?: (event: WSEvent) => void
) {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<WSEvent | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);

  // 连接WebSocket
  const connect = useCallback(() => {
    if (!workflowRunId) return;

    const ws = new WebSocket(webSocketUrl(`/ws/workflow/${workflowRunId}`));

    ws.onopen = () => {
      setConnected(true);
      console.log(`[WS] 已连接到工作流 ${workflowRunId}`);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as WSEvent;
        setLastEvent(data);
        onEvent?.(data);

        // 处理心跳
        if (event.data === 'ping') {
          ws.send('pong');
        }
      } catch {
        // 非JSON消息（如pong）
        if (event.data === 'pong') {
          // 心跳响应
        }
      }
    };

    ws.onclose = () => {
      setConnected(false);
      console.log('[WS] 连接已关闭');

      // 自动重连
      if (workflowRunId) {
        reconnectTimeoutRef.current = setTimeout(() => {
          setReconnectAttempt((attempt) => attempt + 1);
        }, 3000);
      }
    };

    ws.onerror = (error) => {
      console.error('[WS] 错误:', error);
    };

    wsRef.current = ws;
  }, [workflowRunId, onEvent]);

  // 断开连接
  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnected(false);
  }, []);

  // 自动连接/断开
  useEffect(() => {
    if (workflowRunId) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [workflowRunId, connect, disconnect, reconnectAttempt]);

  return {
    connected,
    lastEvent,
    disconnect,
    reconnect: connect,
  };
}

// ==================== 用户通知 Hook ====================

export function useUserNotifications(
  userId: string | null,
  onNotification?: (event: ApprovalEvent) => void
) {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [notifications, setNotifications] = useState<ApprovalEvent[]>([]);

  useEffect(() => {
    if (!userId) return;

    const ws = new WebSocket(webSocketUrl(`/ws/user/${userId}`));

    ws.onopen = () => {
      setConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'approval_required' || data.type === 'approval_timeout') {
          const notification = data as ApprovalEvent;
          setNotifications((prev) => [...prev, notification]);
          onNotification?.(notification);
        }
      } catch {
        // Ignore non-JSON messages
      }
    };

    ws.onclose = () => {
      setConnected(false);
    };

    wsRef.current = ws;

    return () => {
      ws.close();
    };
  }, [userId, onNotification]);

  const clearNotification = useCallback((approvalTaskId: string) => {
    setNotifications((prev) =>
      prev.filter((n) => n.approval_task_id !== approvalTaskId)
    );
  }, []);

  return {
    connected,
    notifications,
    clearNotification,
  };
}
