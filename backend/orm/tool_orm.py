"""Tool Factory ORM 兼容入口。

tool_calls 表已与 Autonomous Agent Runtime 共享，避免两个运行态重复注册同名表。
"""

from orm.autonomous_agent_orm import ToolCallORM

__all__ = ["ToolCallORM"]
