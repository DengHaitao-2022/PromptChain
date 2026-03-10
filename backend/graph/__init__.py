"""
工作流图模块

将 LangGraph 相关逻辑组织为子模块：
- state.py      — GraphState 数据合约
- conditions.py — 条件路由函数
- builder.py    — 图构建 + finalize_output 节点
- executor.py   — ContentGenerationWorkflow 执行器
"""
from .state import GraphState
from .builder import build_content_generation_graph
from .executor import ContentGenerationWorkflow, get_workflow

__all__ = [
    "GraphState",
    "build_content_generation_graph",
    "ContentGenerationWorkflow",
    "get_workflow",
]
