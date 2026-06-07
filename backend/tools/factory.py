"""工具实例工厂。"""

from __future__ import annotations

from tools.base import BaseTool
from tools.registry import ToolRegistry, get_tool_registry
from tools.schemas import ToolSpec


class ToolFactory:
    """根据 ToolRegistry 构造工具实例。"""

    def __init__(self, registry: ToolRegistry | None = None):
        self.registry = registry or get_tool_registry()

    def get_spec(self, name: str) -> ToolSpec:
        return self.registry.get_spec(name)

    def create(self, name: str) -> BaseTool:
        spec = self.registry.get_spec(name)
        if not spec.enabled:
            raise ValueError(f"工具已禁用: {name}")
        tool_class = self.registry.get_tool_class(name)
        return tool_class(spec)
