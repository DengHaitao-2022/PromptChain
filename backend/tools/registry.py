"""工具注册与发现。"""

from __future__ import annotations

from collections.abc import Iterable

from tools.base import BaseTool
from tools.schemas import ToolSpec


class ToolRegistry:
    """统一工具注册表。"""

    def __init__(self):
        self._specs: dict[str, ToolSpec] = {}
        self._tool_classes: dict[str, type[BaseTool]] = {}

    def register(self, tool_class: type[BaseTool], *, override: bool = False) -> ToolSpec:
        """注册工具类。"""
        spec = tool_class.spec
        if spec.name in self._specs and not override:
            raise ValueError(f"工具已注册: {spec.name}")
        self._specs[spec.name] = spec
        self._tool_classes[spec.name] = tool_class
        return spec

    def register_instance(self, tool: BaseTool, *, override: bool = False) -> ToolSpec:
        """注册已构造工具实例的类和 spec。"""
        spec = tool.spec
        if spec.name in self._specs and not override:
            raise ValueError(f"工具已注册: {spec.name}")
        self._specs[spec.name] = spec
        self._tool_classes[spec.name] = tool.__class__
        return spec

    def get_spec(self, name: str) -> ToolSpec:
        """读取工具定义。"""
        if name not in self._specs:
            raise KeyError(f"未知工具: {name}")
        return self._specs[name]

    def get_tool_class(self, name: str) -> type[BaseTool]:
        """读取工具类。"""
        if name not in self._tool_classes:
            raise KeyError(f"未知工具: {name}")
        return self._tool_classes[name]

    def list_specs(
        self,
        *,
        category: str | None = None,
        enabled_only: bool = True,
        query: str | None = None,
    ) -> list[ToolSpec]:
        """按分类、启用状态和关键词列出工具。"""
        specs: Iterable[ToolSpec] = self._specs.values()
        if enabled_only:
            specs = [spec for spec in specs if spec.enabled]
        if category:
            specs = [spec for spec in specs if spec.category == category]
        if query:
            keyword = query.strip().lower()
            specs = [
                spec
                for spec in specs
                if keyword in spec.name.lower()
                or keyword in (spec.title or "").lower()
                or keyword in spec.description.lower()
            ]
        return sorted(specs, key=lambda spec: (spec.category, spec.name))

    def categories(self) -> list[str]:
        """返回当前工具分类。"""
        return sorted({spec.category for spec in self._specs.values()})


_tool_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """获取全局工具注册表。"""
    global _tool_registry
    if _tool_registry is None:
        registry = ToolRegistry()
        from tools.builtin import register_builtin_tools

        register_builtin_tools(registry)
        _tool_registry = registry
    return _tool_registry
