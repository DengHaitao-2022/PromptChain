"""小说工作台资产分类常量。"""

NOVEL_ASSET_TYPES: tuple[str, ...] = (
    "story_bible",
    "character_card",
    "character_state",
    "relationship_edge",
    "world_setting",
    "world_rule",
    "location_card",
    "faction_card",
    "item_card",
    "plot_arc",
    "chapter_outline",
    "scene_card",
    "scene_draft",
    "timeline_event",
    "foreshadowing_record",
    "continuity_fact",
    "style_guide",
    "consistency_report",
)

NOVEL_CORE_CANON_TYPES: frozenset[str] = frozenset(
    {
        "story_bible",
        "character_card",
        "relationship_edge",
        "world_setting",
        "world_rule",
        "location_card",
        "faction_card",
        "item_card",
        "plot_arc",
        "chapter_outline",
        "timeline_event",
        "continuity_fact",
        "style_guide",
    }
)

NOVEL_MEMORY_CANDIDATE_TYPES: frozenset[str] = frozenset(
    {
        "character_state",
        "scene_card",
        "scene_draft",
        "foreshadowing_record",
        "consistency_report",
    }
)

NOVEL_REQUIRED_GENERATION_MODES: tuple[str, ...] = (
    "initialize_story",
    "plan_scene",
    "continue_scene",
    "generate_scene",
    "rewrite_scene",
    "expand_scene",
    "compress_scene",
    "branch_plot",
    "polish_style",
    "fix_character_consistency",
    "fix_timeline_conflict",
)
