"""工具运行上下文。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True)
class ToolRuntime:
    """工具执行时可访问的运行态上下文。"""

    user_id: str | None
    workspace_id: str | None
    workflow_run_id: str | None = None
    node_run_id: str | None = None
    tool_call_id: str | None = None
    graph_state: dict[str, Any] | None = None
    node_config: dict[str, Any] | None = None
    db_session: Any | None = None
    artifact_writer: Any | None = None
    trace_writer: Any | None = None
    store: Any | None = None
    role: str | None = None
    request_id: str | None = None
    approval_context: dict[str, Any] | None = None

    def with_tool_call_id(self, tool_call_id: str) -> ToolRuntime:
        """返回带 tool_call_id 的新上下文，避免可变对象在重试间串味。"""
        return replace(self, tool_call_id=tool_call_id)
