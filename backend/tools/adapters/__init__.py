"""多来源工具适配器。"""

from tools.adapters.http import http_endpoint_to_spec
from tools.adapters.langchain import LangChainToolWrapper, langchain_tool_to_spec
from tools.adapters.mcp import mcp_tool_to_spec, spec_to_mcp_tool
from tools.adapters.openapi import openapi_operation_to_spec
from tools.adapters.workflow import workflow_context_to_tool_spec

__all__ = [
    "LangChainToolWrapper",
    "http_endpoint_to_spec",
    "langchain_tool_to_spec",
    "mcp_tool_to_spec",
    "openapi_operation_to_spec",
    "spec_to_mcp_tool",
    "workflow_context_to_tool_spec",
]
