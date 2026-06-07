"""场景运行期检查与项目记忆候选服务。"""

from __future__ import annotations

from typing import Any

NOVEL_REQUIRED_ASSET_TYPES = (
    "story_bible",
    "character_card",
    "world_setting",
    "timeline_event",
)

SCENARIO_MEMORY_CANDIDATE_TYPES: dict[str, dict[str, str]] = {
    "marketing_copy": {
        "xiaohongshu_post": "content_variants",
        "ecommerce_detail": "content_variants",
        "ad_headlines": "content_variants",
        "short_video_pitch": "content_variants",
        "ab_variants": "content_variants",
        "brand_voice_rewrite": "content_variants",
        "compliance_check": "compliance_report",
        "default": "content_variants",
    },
    "short_video_script": {
        "hook_options": "hook_options",
        "voiceover_script": "voiceover_script",
        "shot_list": "shot_list",
        "caption_pack": "caption_pack",
        "platform_variant": "platform_variant",
        "default": "script_outline",
    },
    "prd": {
        "requirement_card": "requirement_card",
        "user_story": "user_story",
        "feature_list": "feature_list",
        "business_flow": "business_flow",
        "exception_flow": "exception_flow",
        "acceptance_criteria": "acceptance_criteria",
        "risk_report": "risk_report",
        "default": "feature_list",
    },
}

SCENARIO_CHECK_SPECS: dict[str, dict[str, Any]] = {
    "marketing_copy": {
        "report_type": "marketing_quality",
        "summary": "营销文案场景已完成品牌语气、受众产品知识和合规性检查。",
        "checks": [
            {
                "type": "brand_voice_check",
                "label": "品牌语气",
                "required_assets": ("brand_voice",),
                "suggestion": "补齐 Brand Voice，避免输出偏离品牌表达。",
            },
            {
                "type": "audience_product_knowledge_check",
                "label": "受众与产品知识",
                "required_assets": ("audience_profile", "product_knowledge"),
                "suggestion": "补齐受众画像或产品知识，避免文案卖点失焦。",
            },
            {
                "type": "compliance_check",
                "label": "合规检查",
                "required_assets": (),
                "suggestion": "人工复核敏感承诺、绝对化表述和平台规范。",
            },
        ],
    },
    "short_video_script": {
        "report_type": "short_video_script_quality",
        "summary": "短视频脚本场景已完成口播、分镜和标题字幕结构检查。",
        "checks": [
            {
                "type": "voiceover_script_check",
                "label": "口播结构",
                "required_assets": (),
                "suggestion": "确认脚本是否包含可直接录制的口播段落。",
            },
            {
                "type": "shot_list_check",
                "label": "分镜结构",
                "required_assets": (),
                "suggestion": "确认脚本是否包含画面调度、镜头或素材提示。",
            },
            {
                "type": "caption_variant_check",
                "label": "标题字幕多版本",
                "required_assets": (),
                "suggestion": "确认是否包含标题、字幕或平台变体。",
            },
        ],
    },
    "prd": {
        "report_type": "prd_completeness",
        "summary": "PRD 场景已完成用户故事、流程、验收标准和风险完整性检查。",
        "checks": [
            {
                "type": "user_story_check",
                "label": "用户故事",
                "required_assets": (),
                "suggestion": "补充角色、目标和价值，避免需求描述过于抽象。",
            },
            {
                "type": "flow_coverage_check",
                "label": "正常与异常流程",
                "required_assets": (),
                "suggestion": "补充业务流程和异常流程，降低实现歧义。",
            },
            {
                "type": "acceptance_criteria_check",
                "label": "验收标准",
                "required_assets": (),
                "suggestion": "补充可验证的验收标准和风险边界。",
            },
        ],
    },
}


def _asset_titles(memory_context: dict[str, Any], asset_type: str) -> list[str]:
    assets = memory_context.get("assets") if isinstance(memory_context, dict) else {}
    typed_assets = assets.get(asset_type) if isinstance(assets, dict) else []
    titles = []
    for asset in typed_assets or []:
        if isinstance(asset, dict) and asset.get("title"):
            titles.append(str(asset["title"]))
    return titles


def _compiled_content(state: dict) -> str:
    final_content = state.get("final_content")
    if isinstance(final_content, dict):
        return "\n\n".join(str(value) for value in final_content.values() if value)
    return str(state.get("generated_content") or "")


def _memory_candidate(
    *,
    asset_type: str,
    title: str,
    content: dict[str, Any],
    generation_mode: str,
) -> dict[str, Any]:
    return {
        "asset_type": asset_type,
        "title": title,
        "content": content,
        "metadata": {
            "source": "project_memory_update_candidate",
            "generation_mode": generation_mode,
        },
    }


def _has_required_memory(memory_context: dict[str, Any], asset_types: tuple[str, ...]) -> bool:
    if not asset_types:
        return True
    return all(_asset_titles(memory_context, asset_type) for asset_type in asset_types)


class ScenarioRuntimeService:
    """为场景运行生成检查报告和记忆更新候选。"""

    def build_scenario_report(self, state: dict) -> dict[str, Any] | None:
        scenario_code = state.get("scenario_code")
        memory_context = state.get("project_memory_context") or {}
        content = _compiled_content(state)
        if scenario_code != "novel_writing":
            return self._build_general_scenario_report(str(scenario_code), memory_context, content)

        checks = [
            self._build_character_check(memory_context, content),
            self._build_timeline_check(memory_context, content),
            self._build_worldbuilding_check(memory_context, content),
        ]
        risk_level = "high" if any(item["risk_level"] == "high" for item in checks) else "low"
        return {
            "scenario_code": scenario_code,
            "report_type": "novel_consistency",
            "risk_level": risk_level,
            "checks": checks,
            "summary": "小说场景已完成人物、时间线和世界观一致性检查。",
        }

    def build_memory_update_candidates(self, state: dict) -> list[dict[str, Any]]:
        scenario_code = state.get("scenario_code")
        project_id = state.get("project_id")
        if not scenario_code or not project_id:
            return []

        content = _compiled_content(state)
        if not content.strip():
            return []

        generation_mode = state.get("generation_mode") or "generate_content"
        if scenario_code == "novel_writing":
            if generation_mode == "initialize_story":
                # 初始化模式把一次生成结果拆成可人工确认的核心故事资产候选。
                shared_content = {
                    "generation_mode": generation_mode,
                    "text": content,
                    "source": "workflow_final_content",
                }
                return [
                    _memory_candidate(
                        asset_type="story_bible",
                        title="Story Bible 初稿",
                        content={**shared_content, "focus": "故事定位、核心冲突和叙事承诺"},
                        generation_mode=generation_mode,
                    ),
                    _memory_candidate(
                        asset_type="character_card",
                        title="主要人物卡初稿",
                        content={**shared_content, "focus": "人物目标、关系、性格和变化弧"},
                        generation_mode=generation_mode,
                    ),
                    _memory_candidate(
                        asset_type="world_setting",
                        title="世界观设定初稿",
                        content={**shared_content, "focus": "时代、地点、规则和限制"},
                        generation_mode=generation_mode,
                    ),
                    _memory_candidate(
                        asset_type="plot_arc",
                        title="主线大纲初稿",
                        content={**shared_content, "focus": "主要剧情阶段和转折点"},
                        generation_mode=generation_mode,
                    ),
                    _memory_candidate(
                        asset_type="chapter_outline",
                        title="章节计划初稿",
                        content={**shared_content, "focus": "章节节拍和场景推进顺序"},
                        generation_mode=generation_mode,
                    ),
                ]
            return [
                _memory_candidate(
                    asset_type="scene_draft",
                    title=f"场景草稿：{generation_mode}",
                    content={
                        "generation_mode": generation_mode,
                        "text": content,
                        "source": "workflow_final_content",
                    },
                    generation_mode=generation_mode,
                )
            ]

        candidate_map = SCENARIO_MEMORY_CANDIDATE_TYPES.get(str(scenario_code))
        if candidate_map:
            # 运行结果必须写回当前场景允许的资产类型，否则人工确认阶段会被模板校验拒绝。
            asset_type = candidate_map.get(str(generation_mode)) or candidate_map["default"]
            return [
                _memory_candidate(
                    asset_type=asset_type,
                    title=self._general_candidate_title(
                        asset_type=asset_type,
                        generation_mode=str(generation_mode),
                    ),
                    content={
                        "generation_mode": generation_mode,
                        "text": content,
                        "source": "workflow_final_content",
                    },
                    generation_mode=str(generation_mode),
                )
            ]

        return [
            _memory_candidate(
                asset_type="content_variants",
                title=f"生成结果：{generation_mode}",
                content={
                    "generation_mode": generation_mode,
                    "text": content,
                    "source": "workflow_final_content",
                },
                generation_mode=generation_mode,
            )
        ]

    def _build_general_scenario_report(
        self,
        scenario_code: str,
        memory_context: dict[str, Any],
        content: str,
    ) -> dict[str, Any] | None:
        spec = SCENARIO_CHECK_SPECS.get(scenario_code)
        if not spec:
            return None

        checks = [
            self._build_general_check(memory_context, content, check_spec)
            for check_spec in spec["checks"]
        ]
        risk_level = "high" if any(item["risk_level"] == "high" for item in checks) else "low"
        return {
            "scenario_code": scenario_code,
            "report_type": spec["report_type"],
            "risk_level": risk_level,
            "checks": checks,
            "summary": spec["summary"],
        }

    def _build_general_check(
        self,
        memory_context: dict[str, Any],
        content: str,
        check_spec: dict[str, Any],
    ) -> dict[str, Any]:
        required_assets = tuple(str(item) for item in check_spec.get("required_assets", ()))
        missing_asset_types = [
            asset_type
            for asset_type in required_assets
            if not _asset_titles(memory_context, asset_type)
        ]
        passed = bool(content.strip()) and _has_required_memory(memory_context, required_assets)
        return {
            "type": check_spec["type"],
            "label": check_spec["label"],
            "risk_level": "high" if not passed else "low",
            "passed": passed,
            "evidence": {
                "content_length": len(content),
                "required_asset_types": list(required_assets),
                "missing_asset_types": missing_asset_types,
            },
            "suggestion": None if passed else check_spec.get("suggestion"),
        }

    def _general_candidate_title(self, *, asset_type: str, generation_mode: str) -> str:
        title_by_type = {
            "content_variants": "内容版本",
            "compliance_report": "合规检查报告",
            "hook_options": "开场钩子",
            "script_outline": "脚本大纲",
            "shot_list": "分镜清单",
            "voiceover_script": "口播稿",
            "caption_pack": "标题字幕包",
            "platform_variant": "平台变体",
            "requirement_card": "需求卡片",
            "user_story": "用户故事",
            "feature_list": "功能清单",
            "business_flow": "业务流程",
            "exception_flow": "异常流程",
            "acceptance_criteria": "验收标准",
            "risk_report": "风险报告",
        }
        return f"{title_by_type.get(asset_type, '生成结果')}：{generation_mode}"

    def _build_character_check(
        self, memory_context: dict[str, Any], content: str
    ) -> dict[str, Any]:
        titles = _asset_titles(memory_context, "character_card")
        missing = [title for title in titles if title and title not in content]
        return {
            "type": "character_consistency_check",
            "label": "人物一致性",
            "risk_level": "high" if missing else "low",
            "passed": not missing,
            "evidence": {
                "character_count": len(titles),
                "missing_mentions": missing[:10],
            },
            "suggestion": "补充关键人物的行为、语气或关系状态。" if missing else None,
        }

    def _build_timeline_check(self, memory_context: dict[str, Any], content: str) -> dict[str, Any]:
        titles = _asset_titles(memory_context, "timeline_event")
        missing = [title for title in titles if title and title not in content]
        return {
            "type": "timeline_consistency_check",
            "label": "时间线一致性",
            "risk_level": "high" if missing else "low",
            "passed": not missing,
            "evidence": {
                "timeline_event_count": len(titles),
                "missing_mentions": missing[:10],
            },
            "suggestion": "核对场景发生顺序和关键事件承接。" if missing else None,
        }

    def _build_worldbuilding_check(
        self,
        memory_context: dict[str, Any],
        content: str,
    ) -> dict[str, Any]:
        missing_asset_types = [
            asset_type
            for asset_type in NOVEL_REQUIRED_ASSET_TYPES
            if not _asset_titles(memory_context, asset_type)
        ]
        return {
            "type": "worldbuilding_consistency_check",
            "label": "世界观一致性",
            "risk_level": "high" if missing_asset_types else "low",
            "passed": not missing_asset_types,
            "evidence": {
                "content_length": len(content),
                "missing_asset_types": missing_asset_types,
            },
            "suggestion": "先补齐 Story Bible、人物卡、世界观或时间线资产。"
            if missing_asset_types
            else None,
        }
