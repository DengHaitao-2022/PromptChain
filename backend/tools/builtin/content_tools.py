"""内容质量类内置工具。"""

from __future__ import annotations

import re
from typing import Any

from tools.base import BaseTool
from tools.runtime import ToolRuntime
from tools.schemas import RiskLevel, ToolResult, ToolSourceType, ToolSpec


class OutlineConsistencyCheckTool(BaseTool):
    spec = ToolSpec(
        name="content.outline_consistency_check",
        title="提纲一致性检查",
        description="检查提纲章节 ID、标题、字数目标和必含主题是否一致。",
        category="content",
        source_type=ToolSourceType.INTERNAL,
        input_schema={
            "type": "object",
            "properties": {
                "outline": {"type": "object"},
                "required_topics": {"type": "array", "items": {"type": "string"}, "default": []},
                "target_words": {"type": ["integer", "null"]},
                "tolerance": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.2},
            },
            "required": ["outline"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        risk_level=RiskLevel.READ_PUBLIC,
    )

    async def execute(self, input_data: dict[str, Any], runtime: ToolRuntime) -> ToolResult:
        outline = input_data["outline"]
        sections = outline.get("sections") if isinstance(outline, dict) else []
        issues: list[dict[str, Any]] = []
        ids: set[str] = set()
        total_words = 0
        flattened_text = str(outline)
        if not isinstance(sections, list) or not sections:
            issues.append({"severity": "high", "message": "提纲缺少 sections"})
        for index, section in enumerate(sections if isinstance(sections, list) else []):
            if not isinstance(section, dict):
                issues.append({"severity": "medium", "message": f"第 {index + 1} 个章节格式无效"})
                continue
            section_id = str(section.get("id") or "")
            if not section_id:
                issues.append({"severity": "medium", "message": f"第 {index + 1} 个章节缺少 id"})
            elif section_id in ids:
                issues.append({"severity": "high", "message": f"章节 id 重复: {section_id}"})
            ids.add(section_id)
            if not section.get("title"):
                issues.append(
                    {"severity": "medium", "message": f"章节 {section_id or index + 1} 缺少标题"}
                )
            words = section.get("target_words")
            if isinstance(words, int):
                total_words += words

        target_words = input_data.get("target_words")
        if isinstance(target_words, int) and target_words > 0:
            tolerance = float(input_data.get("tolerance") or 0.2)
            lower = target_words * (1 - tolerance)
            upper = target_words * (1 + tolerance)
            if total_words and not lower <= total_words <= upper:
                issues.append(
                    {
                        "severity": "medium",
                        "message": f"章节目标字数合计 {total_words} 与目标 {target_words} 偏差过大",
                    }
                )

        for topic in input_data.get("required_topics") or []:
            if str(topic).strip() and str(topic) not in flattened_text:
                issues.append({"severity": "medium", "message": f"缺少必含主题: {topic}"})

        high_count = len([item for item in issues if item["severity"] == "high"])
        payload = {
            "passed": high_count == 0,
            "issue_count": len(issues),
            "high_risk_count": high_count,
            "total_target_words": total_words,
            "issues": issues,
        }
        return ToolResult(
            output=payload,
            summary="提纲检查通过" if payload["passed"] else f"提纲检查发现 {len(issues)} 个问题",
        )


class StyleCheckTool(BaseTool):
    spec = ToolSpec(
        name="content.style_check",
        title="内容风格检查",
        description="用可解释规则检查语气、禁用词、句长和结构密度。",
        category="content",
        source_type=ToolSourceType.INTERNAL,
        input_schema={
            "type": "object",
            "properties": {
                "content": {"type": "string", "minLength": 1},
                "banned_terms": {"type": "array", "items": {"type": "string"}, "default": []},
                "required_terms": {"type": "array", "items": {"type": "string"}, "default": []},
                "max_sentence_length": {
                    "type": "integer",
                    "minimum": 20,
                    "maximum": 500,
                    "default": 120,
                },
            },
            "required": ["content"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        risk_level=RiskLevel.READ_PUBLIC,
    )

    async def execute(self, input_data: dict[str, Any], runtime: ToolRuntime) -> ToolResult:
        content = input_data["content"]
        issues: list[dict[str, Any]] = []
        for term in input_data.get("banned_terms") or []:
            if term and term in content:
                issues.append({"severity": "medium", "message": f"包含禁用词: {term}"})
        for term in input_data.get("required_terms") or []:
            if term and term not in content:
                issues.append({"severity": "medium", "message": f"缺少必含词: {term}"})
        max_sentence_length = int(input_data.get("max_sentence_length") or 120)
        sentences = [item.strip() for item in re.split(r"[。！？.!?]\s*", content) if item.strip()]
        long_sentences = [
            {"length": len(sentence), "preview": sentence[:80]}
            for sentence in sentences
            if len(sentence) > max_sentence_length
        ]
        for sentence in long_sentences[:10]:
            issues.append(
                {
                    "severity": "low",
                    "message": f"句子过长（{sentence['length']} 字）: {sentence['preview']}",
                }
            )
        score = max(0, 100 - len(issues) * 8)
        return ToolResult(
            output={
                "score": score,
                "issue_count": len(issues),
                "issues": issues,
                "sentence_count": len(sentences),
                "word_count": len(content),
            },
            summary=f"风格检查得分 {score}",
        )
