import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models import ArtifactType
from services.rerun_service import RerunService


def _intent_content(topic: str = "Agent") -> dict:
    return {
        "goal": "生成技术文章",
        "topic": topic,
        "audience": "中级读者",
        "tone": "学术专业",
        "length": 1200,
        "must_include": [],
        "must_exclude": [],
        "source_references": [],
        "uncertainties": [],
    }


def _outline_content(title: str = "Agent 架构") -> dict:
    return {
        "title": title,
        "abstract": "概述",
        "sections": [
            {
                "id": "intro",
                "title": "引言",
                "summary": "介绍背景",
                "target_words": 300,
                "subsections": [],
                "dependencies": [],
            }
        ],
        "total_target_words": 300,
        "version": 1,
        "is_approved": True,
    }


class _FakeTraceService:
    def __init__(self, trace: dict):
        self.trace = trace

    async def get_workflow_trace(self, workflow_run_id: str):
        await asyncio.sleep(0)
        return self.trace


@pytest.mark.asyncio
async def test_prepare_rerun_state_raises_when_from_node_not_found():
    trace_service = _FakeTraceService(
        {
            "nodes": [
                {"node_name": "parse_intent", "output_artifact_ids": ["a1"]},
            ],
            "artifacts": {
                "a1": {
                    "type": ArtifactType.INTENT_CARD.value,
                    "content": {"intent": "write"},
                }
            },
        }
    )
    service = RerunService(artifact_store=None, trace_service=trace_service)

    with pytest.raises(ValueError, match="Node 'unknown_node' not found in workflow"):
        await service.prepare_rerun_state("wf-1", "unknown_node")


@pytest.mark.asyncio
async def test_prepare_rerun_state_maps_artifacts_before_from_node():
    trace_service = _FakeTraceService(
        {
            "nodes": [
                {
                    "node_name": "parse_intent",
                    "output_artifact_ids": ["intent-artifact"],
                },
                {
                    "node_name": "generate_outline",
                    "output_artifact_ids": ["outline-artifact"],
                },
                {
                    "node_name": "generate_content",
                    "output_artifact_ids": ["section-1", "section-missing-id"],
                },
                {
                    "node_name": "check_facts",
                    "output_artifact_ids": ["fact-artifact"],
                },
                {
                    "node_name": "finalize",
                    "output_artifact_ids": ["final-artifact"],
                },
            ],
            "artifacts": {
                "intent-artifact": {
                    "type": ArtifactType.INTENT_CARD.value,
                    "content": _intent_content("Agent"),
                },
                "outline-artifact": {
                    "type": ArtifactType.OUTLINE.value,
                    "content": _outline_content(),
                },
                "section-1": {
                    "type": ArtifactType.SECTION_CONTENT.value,
                    "content": {"section_id": "intro", "content": "Intro draft"},
                },
                "section-missing-id": {
                    "type": ArtifactType.SECTION_CONTENT.value,
                    "content": {"content": "Should be ignored"},
                },
                "fact-artifact": {
                    "type": ArtifactType.FACT_CHECK_REPORT.value,
                    "content": {
                        "claims": [
                            {
                                "id": "claim-1",
                                "text": "事实声明",
                                "section_id": "intro",
                            }
                        ],
                        "results": [
                            {
                                "claim_id": "claim-1",
                                "is_verified": True,
                                "confidence": 0.9,
                                "risk_level": "low",
                            }
                        ],
                        "total_claims": 1,
                        "verified_count": 1,
                        "unverified_count": 0,
                    },
                },
                "final-artifact": {
                    "type": ArtifactType.FINAL_CONTENT.value,
                    "content": {"sections": {"intro": "Final intro"}},
                },
            },
        }
    )
    service = RerunService(artifact_store=None, trace_service=trace_service)

    state = await service.prepare_rerun_state("wf-1", "finalize")

    assert state["intent_card"].topic == "Agent"
    assert state["intent_card_artifact_id"] == "intent-artifact"
    assert state["outline"].sections[0].id == "intro"
    assert state["outline_artifact_id"] == "outline-artifact"
    assert state["outline_approved"] is True
    assert state["draft_sections"] == {"intro": "Intro draft"}
    assert state["section_artifact_ids"] == {"intro": "section-1"}
    assert state["fact_check_report"].results[0].risk_level == "low"
    assert state["fact_check_artifact_id"] == "fact-artifact"
    assert "final_content" not in state
    assert "final_content_artifact_id" not in state


@pytest.mark.asyncio
async def test_prepare_rerun_state_applies_updated_input_override():
    trace_service = _FakeTraceService(
        {
            "nodes": [
                {
                    "node_name": "parse_intent",
                    "output_artifact_ids": ["intent-artifact"],
                },
                {
                    "node_name": "generate_outline",
                    "output_artifact_ids": ["outline-artifact"],
                },
            ],
            "artifacts": {
                "intent-artifact": {
                    "type": ArtifactType.INTENT_CARD.value,
                    "content": _intent_content("旧主题"),
                },
                "outline-artifact": {
                    "type": ArtifactType.OUTLINE.value,
                    "content": _outline_content("旧提纲"),
                },
            },
        }
    )
    service = RerunService(artifact_store=None, trace_service=trace_service)

    state = await service.prepare_rerun_state(
        "wf-1",
        "generate_outline",
        updated_input={"intent_card": {"topic": "新主题"}, "custom": "value"},
    )

    assert state["intent_card"] == {"topic": "新主题"}
    assert state["custom"] == "value"
