"""内置工具注册入口。"""

from tools.builtin.artifact_tools import (
    ArtifactListVersionsTool,
    ArtifactReadTool,
    ArtifactWriteTool,
)
from tools.builtin.content_tools import OutlineConsistencyCheckTool, StyleCheckTool
from tools.builtin.document_tools import DocumentChunkTextTool, DocumentLoadTextTool
from tools.builtin.fact_check_tools import FactCheckClaimsTool
from tools.builtin.retrieval_tools import QueryWorkspaceKnowledgeTool
from tools.builtin.validation_tools import JsonSchemaValidateTool
from tools.registry import ToolRegistry

BUILTIN_TOOLS = (
    ArtifactReadTool,
    ArtifactWriteTool,
    ArtifactListVersionsTool,
    QueryWorkspaceKnowledgeTool,
    DocumentLoadTextTool,
    DocumentChunkTextTool,
    JsonSchemaValidateTool,
    OutlineConsistencyCheckTool,
    StyleCheckTool,
    FactCheckClaimsTool,
)


def register_builtin_tools(registry: ToolRegistry) -> None:
    """注册第一批内置工具。"""
    for tool_class in BUILTIN_TOOLS:
        registry.register(tool_class, override=True)
