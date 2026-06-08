"""HTTP 工具适配基础结构。"""

from __future__ import annotations

from typing import Any

from tools.schemas import RiskLevel, ToolSourceType, ToolSpec


def http_endpoint_to_spec(
    *,
    name: str,
    url: str,
    method: str = "POST",
    input_schema: dict[str, Any] | None = None,
    description: str | None = None,
) -> ToolSpec:
    """把受管 HTTP 端点声明为 ToolSpec。

    远程 HTTP 调用默认关闭，管理员后续可按工作空间密钥与审批策略启用。
    """
    risk_level = RiskLevel.READ_PRIVATE if method.upper() == "GET" else RiskLevel.EXTERNAL_ACTION
    return ToolSpec(
        name=name,
        title=name,
        description=description or f"{method.upper()} {url}",
        category="http",
        source_type=ToolSourceType.HTTP,
        input_schema=input_schema or {"type": "object"},
        risk_level=risk_level,
        permissions=["workflow_run.read"]
        if risk_level == RiskLevel.READ_PRIVATE
        else ["workflow.execute"],
        requires_approval=risk_level == RiskLevel.EXTERNAL_ACTION,
        enabled=False,
        metadata={"http": {"url": url, "method": method.upper()}},
    )
