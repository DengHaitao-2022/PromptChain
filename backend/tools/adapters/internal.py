"""内部工具适配入口。"""

from tools.builtin import BUILTIN_TOOLS


def iter_internal_tool_classes():
    """返回内置工具类列表，供自定义注册流程复用。"""
    return iter(BUILTIN_TOOLS)
