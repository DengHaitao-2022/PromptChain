"""
向后兼容入口

此文件的逻辑已拆分到以下子模块：
- graph/state.py      — GraphState 定义
- graph/conditions.py — 条件路由函数
- graph/builder.py    — 图构建 + finalize_output
- graph/executor.py   — ContentGenerationWorkflow + get_workflow

推荐直接使用 `from graph import GraphState, get_workflow` 等方式导入。
"""

# 重新导出以保持旧的 import 路径兼容
from graph.builder import (  # noqa: F401
    build_content_generation_graph,
    finalize_output,
)
from graph.conditions import (  # noqa: F401
    should_clarify,
    should_proceed_after_fact_check,
    should_regenerate_outline,
    should_run_fact_check,
    should_run_self_refine,
)
from graph.executor import (  # noqa: F401
    ContentGenerationWorkflow,
    get_workflow,
)
from graph.state import GraphState  # noqa: F401
