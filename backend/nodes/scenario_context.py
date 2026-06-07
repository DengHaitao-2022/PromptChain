"""场景项目记忆的 prompt 上下文格式化工具。"""

from __future__ import annotations

import json
from typing import Any


def _compact_value(value: Any, *, max_length: int = 700) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    text = " ".join(text.split())
    if len(text) <= max_length:
        return text
    return f"{text[:max_length]}..."


def format_project_memory_context(state: dict, *, max_assets: int = 14) -> str:
    """把结构化 Project Memory 压缩为 LLM 可消费的中文上下文。"""
    memory_context = state.get("project_memory_context")
    if not isinstance(memory_context, dict):
        return "当前运行未绑定内容项目，暂无结构化项目记忆。"

    project = (
        memory_context.get("project") if isinstance(memory_context.get("project"), dict) else {}
    )
    assets = memory_context.get("assets") if isinstance(memory_context.get("assets"), dict) else {}
    scenario_code = memory_context.get("scenario_code") or state.get("scenario_code") or "未指定"
    generation_mode = (
        memory_context.get("generation_mode") or state.get("generation_mode") or "默认生成"
    )

    lines = [
        "使用规则：项目记忆是本次内容生成的长期上下文；不得改写已确认设定，缺失信息需显式说明。",
        f"项目：{project.get('title') or '未命名项目'}",
        f"场景：{scenario_code}",
        f"生成模式：{generation_mode}",
    ]
    if project.get("description"):
        lines.append(f"项目说明：{_compact_value(project['description'], max_length=360)}")

    asset_count = 0
    priority_types = [
        "story_bible",
        "character_card",
        "world_setting",
        "timeline_event",
        "plot_arc",
        "chapter_outline",
        "style_guide",
        "brand_voice",
        "audience_profile",
        "product_knowledge",
    ]
    ordered_types = priority_types + sorted(set(assets.keys()) - set(priority_types))
    for asset_type in ordered_types:
        typed_assets = assets.get(asset_type)
        if not isinstance(typed_assets, list):
            continue
        for asset in typed_assets:
            if asset_count >= max_assets:
                lines.append(f"其余项目资产已省略，本次最多注入 {max_assets} 条。")
                return "\n".join(lines)
            if not isinstance(asset, dict):
                continue
            title = asset.get("title") or "未命名资产"
            version = asset.get("version") or 1
            content = _compact_value(asset.get("content"), max_length=700)
            lines.append(f"- [{asset_type} v{version}] {title}: {content}")
            asset_count += 1

    if asset_count == 0:
        lines.append("当前项目尚未沉淀结构化资产。")
    return "\n".join(lines)
