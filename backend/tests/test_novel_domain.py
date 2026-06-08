import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.scenario import ProjectAsset, ProjectAssetLifecycleStatus
from services.novel import (
    NOVEL_ASSET_TYPES,
    NOVEL_CORE_CANON_TYPES,
    NOVEL_MEMORY_CANDIDATE_TYPES,
    NOVEL_REQUIRED_GENERATION_MODES,
)
from services.scenario_service import DEFAULT_SCENARIO_TEMPLATES

ISSUE24_NOVEL_ASSET_TYPES: set[str] = {
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
}


def test_novel_template_exposes_complete_issue24_asset_types_and_modes():
    template = next(item for item in DEFAULT_SCENARIO_TEMPLATES if item["code"] == "novel_writing")

    assert set(NOVEL_ASSET_TYPES) == ISSUE24_NOVEL_ASSET_TYPES
    assert set(template["artifact_schema"]["asset_types"]) == ISSUE24_NOVEL_ASSET_TYPES
    assert {mode["code"] for mode in template["default_generation_modes"]} >= set(
        NOVEL_REQUIRED_GENERATION_MODES
    )


def test_project_asset_lifecycle_defaults_to_canon():
    asset = ProjectAsset(
        project_id="project-1",
        asset_type="story_bible",
        title="故事圣经",
        content={"premise": "雾城灯塔失序"},
        created_by="user-1",
    )

    assert asset.lifecycle_status == ProjectAssetLifecycleStatus.CANON


def test_novel_taxonomy_separates_canon_and_candidate_memory_types():
    assert set(NOVEL_ASSET_TYPES) >= NOVEL_CORE_CANON_TYPES
    assert set(NOVEL_ASSET_TYPES) >= NOVEL_MEMORY_CANDIDATE_TYPES
    assert "scene_draft" in NOVEL_MEMORY_CANDIDATE_TYPES
    assert "consistency_report" in NOVEL_MEMORY_CANDIDATE_TYPES
