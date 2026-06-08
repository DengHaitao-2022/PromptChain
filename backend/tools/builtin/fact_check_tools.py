"""事实核查内置工具。"""

from __future__ import annotations

import re
from typing import Any

from tools.base import BaseTool
from tools.runtime import ToolRuntime
from tools.schemas import RiskLevel, ToolResult, ToolSourceType, ToolSpec


class FactCheckClaimsTool(BaseTool):
    spec = ToolSpec(
        name="fact.check_claims",
        title="事实声明初筛",
        description="对文本中的数字、日期、引用和政策类事实声明做可解释初筛。",
        category="fact",
        source_type=ToolSourceType.INTERNAL,
        input_schema={
            "type": "object",
            "properties": {
                "content": {"type": "string", "minLength": 1},
                "evidence_pack": {"type": ["object", "null"]},
                "max_claims": {"type": "integer", "minimum": 1, "maximum": 100, "default": 30},
            },
            "required": ["content"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        risk_level=RiskLevel.READ_PRIVATE,
        permissions=["workflow_run.read"],
    )

    async def execute(self, input_data: dict[str, Any], runtime: ToolRuntime) -> ToolResult:
        content = input_data["content"]
        max_claims = int(input_data.get("max_claims") or 30)
        evidence_text = str(input_data.get("evidence_pack") or runtime.graph_state or "")
        patterns = [
            ("number", r"[^。！？.!?]*(?:\d+(?:\.\d+)?%?|\d{4}年|\d+月|\d+日)[^。！？.!?]*"),
            ("source", r"[^。！？.!?]*(?:根据|数据显示|研究|报告|来源|引用)[^。！？.!?]*"),
            ("policy", r"[^。！？.!?]*(?:政策|法规|规定|标准|合规|许可)[^。！？.!?]*"),
        ]
        claims: list[dict[str, Any]] = []
        seen: set[str] = set()
        for category, pattern in patterns:
            for match in re.finditer(pattern, content):
                text = match.group(0).strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                supported = text[:24] in evidence_text or text[-24:] in evidence_text
                claims.append(
                    {
                        "id": f"claim-{len(claims) + 1}",
                        "text": text[:500],
                        "category": category,
                        "risk_level": "low" if supported else "medium",
                        "evidence_status": "supported" if supported else "not_checked",
                        "verification_question": f"请核实以下声明是否准确：{text[:160]}",
                    }
                )
                if len(claims) >= max_claims:
                    break
            if len(claims) >= max_claims:
                break
        payload = {
            "claims": claims,
            "total_claims": len(claims),
            "unverified_count": len(
                [item for item in claims if item["evidence_status"] != "supported"]
            ),
        }
        return ToolResult(
            output=payload,
            summary=f"识别到 {len(claims)} 条事实声明",
        )
