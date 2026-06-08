import asyncio
import sys
from pathlib import Path

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import orm.scenario_orm  # noqa: F401
from db.postgres_store import Base
from models.auth_models import MemberRole
from models.auth_orm import MembershipORM, UserORM, WorkspaceORM
from models.fact_check import FactCheckReport
from models.knowledge import KnowledgeScope, KnowledgeSearchRequest
from models.scenario import ProjectAssetLifecycleStatus
from orm.knowledge_orm import KnowledgeBaseORM
from services.scenario_runtime_service import ScenarioRuntimeService
from services.scenario_service import ScenarioService


@pytest.fixture
def run_with_scenario_session(tmp_path, monkeypatch):
    def _run(scenario):
        async def _run_scenario():
            monkeypatch.setenv("KNOWLEDGE_STORAGE_DIR", str(tmp_path / "knowledge"))
            monkeypatch.setenv("KNOWLEDGE_EMBEDDING_DIMENSION", "32")
            engine = create_async_engine("sqlite+aiosqlite:///:memory:")

            @event.listens_for(engine.sync_engine, "connect")
            def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

            try:
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)

                session_factory = async_sessionmaker(engine, expire_on_commit=False)
                async with session_factory() as session:
                    session.add_all(
                        [
                            UserORM(
                                id="user-owner",
                                email="owner@example.com",
                                password_hash="x",
                                status="active",
                                email_verified=True,
                            ),
                            WorkspaceORM(id="ws-1", name="默认空间", owner_id="user-owner"),
                            MembershipORM(
                                id="membership-owner",
                                user_id="user-owner",
                                workspace_id="ws-1",
                                role=MemberRole.OWNER.value,
                            ),
                        ]
                    )
                    await session.commit()
                    await scenario(session)
            finally:
                await engine.dispose()

        asyncio.run(_run_scenario())

    return _run


def test_seed_templates_and_project_asset_versioning(run_with_scenario_session):
    async def scenario(session):
        service = ScenarioService(session)

        templates = await service.list_templates()
        assert {template.code for template in templates} >= {
            "novel_writing",
            "marketing_copy",
            "short_video_script",
            "prd",
        }
        prd_template = next(template for template in templates if template.code == "prd")
        assert {mode["code"] for mode in prd_template.default_generation_modes} >= {
            "user_story",
            "feature_list",
            "exception_flow",
            "acceptance_criteria",
        }

        project = await service.create_project(
            workspace_id="ws-1",
            user_id="user-owner",
            scenario_code="novel_writing",
            title="星潮纪元",
            description="长篇科幻小说项目",
        )
        asset = await service.create_asset(
            project_id=project.id,
            workspace_id="ws-1",
            user_id="user-owner",
            asset_type="character_card",
            title="林澈",
            content={"name": "林澈", "trait": "谨慎但执着"},
        )
        assert asset.version == 1
        assert asset.lifecycle_status == ProjectAssetLifecycleStatus.CANON

        with pytest.raises(ValueError, match="资产类型不属于当前场景模板"):
            await service.create_asset(
                project_id=project.id,
                workspace_id="ws-1",
                user_id="user-owner",
                asset_type="brand_voice",
                title="不属于小说场景的资产",
                content={"voice": "sharp"},
            )

        updated = await service.update_asset(
            asset_id=asset.id,
            workspace_id="ws-1",
            user_id="user-owner",
            content={"name": "林澈", "trait": "谨慎但愿意冒险"},
            lifecycle_status=ProjectAssetLifecycleStatus.CANDIDATE,
        )
        assert updated.version == 2
        assert updated.lifecycle_status == ProjectAssetLifecycleStatus.CANDIDATE

        versions = await service.list_asset_versions(asset_id=asset.id, workspace_id="ws-1")
        assert [version.version for version in versions] == [2, 1]
        assert versions[0].metadata["lifecycle_status"] == "candidate"
        assert versions[1].metadata["lifecycle_status"] == "canon"

        restored = await service.restore_asset_version(
            asset_id=asset.id,
            workspace_id="ws-1",
            user_id="user-owner",
            version=1,
        )
        assert restored.version == 3
        assert restored.content["trait"] == "谨慎但执着"
        assert restored.lifecycle_status == ProjectAssetLifecycleStatus.CANON
        assert restored.metadata["restored_from_lifecycle_status"] == "canon"

        with pytest.raises(ValueError, match="生成模式不属于当前场景模板"):
            await service.validate_project_run_context(
                project_id=project.id,
                workspace_id="ws-1",
                generation_mode="xiaohongshu_post",
            )

    run_with_scenario_session(scenario)


def test_project_asset_lifecycle_statuses_and_filtering(run_with_scenario_session):
    async def scenario(session):
        service = ScenarioService(session)
        project = await service.create_project(
            workspace_id="ws-1",
            user_id="user-owner",
            scenario_code="novel_writing",
            title="镜海列传",
        )

        for status in (
            ProjectAssetLifecycleStatus.DRAFT,
            ProjectAssetLifecycleStatus.CANDIDATE,
            ProjectAssetLifecycleStatus.CONFLICT,
            ProjectAssetLifecycleStatus.DEPRECATED,
        ):
            created = await service.create_asset(
                project_id=project.id,
                workspace_id="ws-1",
                user_id="user-owner",
                asset_type="scene_card",
                title=f"场景卡：{status.value}",
                content={"status": status.value},
                lifecycle_status=status,
            )
            assert created.lifecycle_status == status

        candidate_assets = await service.list_assets(
            project_id=project.id,
            workspace_id="ws-1",
            lifecycle_status=ProjectAssetLifecycleStatus.CANDIDATE,
        )

        assert [asset.lifecycle_status for asset in candidate_assets] == [
            ProjectAssetLifecycleStatus.CANDIDATE
        ]

    run_with_scenario_session(scenario)


def test_project_asset_sync_indexes_project_memory_filters(run_with_scenario_session):
    async def scenario(session):
        service = ScenarioService(session)
        project = await service.create_project(
            workspace_id="ws-1",
            user_id="user-owner",
            scenario_code="novel_writing",
            title="雾城手记",
        )
        other_project = await service.create_project(
            workspace_id="ws-1",
            user_id="user-owner",
            scenario_code="novel_writing",
            title="海岸档案",
        )
        asset = await service.create_asset(
            project_id=project.id,
            workspace_id="ws-1",
            user_id="user-owner",
            asset_type="world_setting",
            title="雾城",
            content={"setting": "雾城依靠灯塔维持昼夜秩序"},
        )
        await service.sync_asset_to_knowledge(
            asset_id=asset.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
        )

        kb_rows = (await session.execute(select(KnowledgeBaseORM))).scalars().all()
        assert len(kb_rows) == 1

        search = await service.session.run_sync(lambda _: None)
        assert search is None

        from services.knowledge_service import KnowledgeService

        matched = await KnowledgeService(session).search(
            request=KnowledgeSearchRequest(
                query="灯塔 昼夜 秩序",
                scopes=[KnowledgeScope.WORKSPACE],
                top_k=5,
                min_score=0.0,
                filters={"project_id": project.id},
            ),
            workspace_id="ws-1",
            user_id="user-owner",
        )
        assert [chunk.metadata["project_id"] for chunk in matched.evidence_pack.chunks] == [
            project.id
        ]

        unmatched = await KnowledgeService(session).search(
            request=KnowledgeSearchRequest(
                query="灯塔 昼夜 秩序",
                scopes=[KnowledgeScope.WORKSPACE],
                top_k=5,
                min_score=0.0,
                filters={"project_id": other_project.id},
            ),
            workspace_id="ws-1",
            user_id="user-owner",
        )
        assert unmatched.evidence_pack.chunks == []

    run_with_scenario_session(scenario)


def test_novel_runtime_report_and_memory_candidates():
    service = ScenarioRuntimeService()
    state = {
        "scenario_code": "novel_writing",
        "project_id": "project-1",
        "generation_mode": "continue_scene",
        "final_content": {"scene": "林澈走进雾城，灯塔仍在远处闪烁。"},
        "project_memory_context": {
            "assets": {
                "story_bible": [{"title": "故事圣经"}],
                "character_card": [{"title": "林澈"}],
                "world_setting": [{"title": "雾城"}],
                "timeline_event": [{"title": "灯塔"}],
            }
        },
    }

    report = service.build_scenario_report(state)
    candidates = service.build_memory_update_candidates(state)

    assert report is not None
    assert {item["type"] for item in report["checks"]} == {
        "character_consistency_check",
        "timeline_consistency_check",
        "worldbuilding_consistency_check",
    }
    assert candidates[0]["asset_type"] == "scene_draft"
    assert candidates[0]["content"]["generation_mode"] == "continue_scene"


def test_novel_initialize_story_generates_core_asset_candidates():
    service = ScenarioRuntimeService()
    candidates = service.build_memory_update_candidates(
        {
            "scenario_code": "novel_writing",
            "project_id": "project-1",
            "generation_mode": "initialize_story",
            "final_content": {"story": "林澈在雾城寻找灯塔失序的真相。"},
        }
    )

    assert [candidate["asset_type"] for candidate in candidates] == [
        "story_bible",
        "character_card",
        "world_setting",
        "plot_arc",
        "chapter_outline",
    ]


def test_novel_runtime_missing_memory_becomes_high_risk():
    service = ScenarioRuntimeService()
    report = service.build_scenario_report(
        {
            "scenario_code": "novel_writing",
            "project_id": "project-1",
            "final_content": {"scene": "一段没有任何既有人物和时间线承接的正文。"},
            "project_memory_context": {
                "assets": {
                    "character_card": [{"title": "林澈"}],
                    "timeline_event": [{"title": "灯塔熄灭"}],
                }
            },
        }
    )

    assert report is not None
    assert report["risk_level"] == "high"
    failed_checks = [item for item in report["checks"] if not item["passed"]]
    assert {item["type"] for item in failed_checks} >= {
        "character_consistency_check",
        "timeline_consistency_check",
    }


def test_novel_consistency_checks_are_mapped_to_fact_check_gate_risks():
    service = ScenarioRuntimeService()
    report = FactCheckReport()
    scenario_report = service.append_checks_to_fact_report(
        report,
        {
            "scenario_code": "novel_writing",
            "project_id": "project-1",
            "final_content": {"scene": "一段没有既有人物和时间线承接的正文。"},
            "project_memory_context": {
                "assets": {
                    "character_card": [{"title": "林澈"}],
                    "timeline_event": [{"title": "灯塔熄灭"}],
                }
            },
        },
    )

    assert scenario_report is not None
    assert scenario_report["risk_level"] == "high"
    report.compute_stats()
    assert report.has_high_risk_items()
    assert {result.claim_id for result in report.results if result.risk_level == "high"} >= {
        "scenario_character_consistency_check",
        "scenario_timeline_consistency_check",
        "scenario_worldbuilding_consistency_check",
    }


def test_p2_runtime_candidates_use_scenario_asset_types():
    service = ScenarioRuntimeService()

    cases = [
        ("marketing_copy", "xiaohongshu_post", "content_variants"),
        ("marketing_copy", "compliance_check", "compliance_report"),
        ("short_video_script", "voiceover_script", "voiceover_script"),
        ("short_video_script", "shot_list", "shot_list"),
        ("short_video_script", "caption_pack", "caption_pack"),
        ("prd", "user_story", "user_story"),
        ("prd", "feature_list", "feature_list"),
        ("prd", "exception_flow", "exception_flow"),
        ("prd", "acceptance_criteria", "acceptance_criteria"),
        ("prd", "risk_report", "risk_report"),
    ]

    for scenario_code, generation_mode, expected_asset_type in cases:
        candidates = service.build_memory_update_candidates(
            {
                "scenario_code": scenario_code,
                "project_id": "project-1",
                "generation_mode": generation_mode,
                "final_content": {"result": f"{scenario_code}:{generation_mode}"},
            }
        )

        assert candidates[0]["asset_type"] == expected_asset_type
        assert candidates[0]["content"]["generation_mode"] == generation_mode


def test_p2_runtime_reports_cover_marketing_video_and_prd_checks():
    service = ScenarioRuntimeService()

    marketing_report = service.build_scenario_report(
        {
            "scenario_code": "marketing_copy",
            "project_id": "project-1",
            "final_content": {"copy": "品牌语气稳定，面向新手用户介绍核心卖点。"},
            "project_memory_context": {
                "assets": {
                    "brand_voice": [{"title": "品牌语气"}],
                    "audience_profile": [{"title": "新手用户"}],
                    "product_knowledge": [{"title": "核心卖点"}],
                }
            },
        }
    )
    assert marketing_report is not None
    assert marketing_report["risk_level"] == "low"
    assert {check["type"] for check in marketing_report["checks"]} == {
        "brand_voice_check",
        "audience_product_knowledge_check",
        "compliance_check",
    }

    short_video_report = service.build_scenario_report(
        {
            "scenario_code": "short_video_script",
            "project_id": "project-1",
            "final_content": {"script": "开场钩子、口播、分镜和标题字幕多版本。"},
        }
    )
    assert short_video_report is not None
    assert {check["type"] for check in short_video_report["checks"]} == {
        "voiceover_script_check",
        "shot_list_check",
        "caption_variant_check",
    }

    prd_report = service.build_scenario_report(
        {
            "scenario_code": "prd",
            "project_id": "project-1",
            "final_content": {"prd": "用户故事、业务流程、异常流程和验收标准。"},
        }
    )
    assert prd_report is not None
    assert {check["type"] for check in prd_report["checks"]} == {
        "user_story_check",
        "flow_coverage_check",
        "acceptance_criteria_check",
    }
