import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import routes.workflow_helpers as workflow_helpers
from main import app
from models.artifact import WorkflowRun, WorkflowRunStatus
from models.scenario import ContentProject, ProjectAsset, ProjectAssetVersion, ScenarioTemplate
from routes.auth_routes import ACCESS_TOKEN_COOKIE
from services.auth_service import create_access_token


class _FakeWorkflow:
    def __init__(self):
        self.calls = []

    async def start(
        self,
        user_input: str,
        workflow_definition_id: str | None = None,
        workflow_version_id: str | None = None,
        workspace_id: str | None = None,
        user_id: str | None = None,
        model_provider_id: str | None = None,
        model_name: str | None = None,
        retrieval_config=None,
        run_upload_documents: list[dict] | None = None,
        scenario_code: str | None = None,
        project_id: str | None = None,
        edit_mode: str | None = None,
        generation_mode: str | None = None,
        target_asset_id: str | None = None,
    ):
        call = {
            "user_input": user_input,
            "workflow_definition_id": workflow_definition_id,
            "workflow_version_id": workflow_version_id,
            "workspace_id": workspace_id,
            "user_id": user_id,
            "model_provider_id": model_provider_id,
            "model_name": model_name,
            "retrieval_config": retrieval_config,
            "run_upload_documents": run_upload_documents,
            "scenario_code": scenario_code,
            "project_id": project_id,
            "edit_mode": edit_mode,
            "generation_mode": generation_mode,
            "target_asset_id": target_asset_id,
        }
        self.calls.append(call)
        return {
            "workflow_run_id": "wf-project",
            "status": "running",
            "state": {
                "workflow_run_id": "wf-project",
                "user_input": user_input,
                "project_id": project_id,
                "scenario_code": scenario_code,
            },
        }


class _FakeStore:
    def __init__(self):
        self.workflow_runs = {
            "wf-project": WorkflowRun(
                id="wf-project",
                user_input="写一段场景",
                status=WorkflowRunStatus.RUNNING,
                metadata={
                    "workspace_id": "ws-1",
                    "user_id": "user-1",
                    "project_id": "project-1",
                    "scenario_code": "novel_writing",
                    "project_memory_update_candidates": [
                        {
                            "asset_type": "scene_draft",
                            "title": "场景草稿",
                            "content": {"text": "林澈走进雾城"},
                            "source_artifact_id": "artifact-candidates",
                        }
                    ],
                },
            ),
            "wf-other": WorkflowRun(
                id="wf-other",
                user_input="其他项目",
                status=WorkflowRunStatus.RUNNING,
                metadata={
                    "workspace_id": "ws-1",
                    "user_id": "user-1",
                    "project_id": "project-2",
                },
            ),
        }

    async def get_workflow_run(self, workflow_run_id: str):
        return self.workflow_runs.get(workflow_run_id)

    async def update_workflow_run(self, workflow_run):
        self.workflow_runs[workflow_run.id] = workflow_run
        return workflow_run

    async def list_workflow_runs(self, *, workspace_id: str, user_id: str | None = None):
        return [
            run
            for run in self.workflow_runs.values()
            if run.metadata.get("workspace_id") == workspace_id
            and (user_id is None or run.metadata.get("user_id") == user_id)
        ]


class _FakeScenarioService:
    def __init__(self):
        self.templates = {
            "novel_writing": ScenarioTemplate(
                id="scenario-novel",
                code="novel_writing",
                name="小说创作",
                category="creative",
                default_workflow_definition_id="workflow-definition-novel",
                default_workflow_version_id="workflow-version-novel",
                artifact_schema={
                    "asset_types": [
                        "story_bible",
                        "character_card",
                        "world_setting",
                        "plot_arc",
                        "timeline_event",
                        "chapter_outline",
                        "scene_draft",
                        "style_guide",
                        "foreshadowing_record",
                        "consistency_report",
                    ]
                },
                default_generation_modes=[
                    {"code": "initialize_story", "name": "初始化故事资产"},
                    {"code": "continue_scene", "name": "续写当前场景"},
                ],
                ui_schema={"fields": [{"name": "story_goal", "label": "故事目标"}]},
            ),
            "marketing_copy": ScenarioTemplate(
                id="scenario-marketing",
                code="marketing_copy",
                name="营销文案",
                category="business",
                artifact_schema={
                    "asset_types": [
                        "brand_voice",
                        "audience_profile",
                        "product_knowledge",
                        "content_variants",
                    ]
                },
                default_generation_modes=[
                    {"code": "xiaohongshu_post", "name": "小红书文案"},
                ],
            ),
            "short_video_script": ScenarioTemplate(
                id="scenario-video",
                code="short_video_script",
                name="短视频脚本",
                category="media",
                artifact_schema={"asset_types": ["voiceover_script", "shot_list", "caption_pack"]},
                default_generation_modes=[
                    {"code": "voiceover_script", "name": "生成口播稿"},
                ],
            ),
            "prd": ScenarioTemplate(
                id="scenario-prd",
                code="prd",
                name="产品需求文档",
                category="product",
                artifact_schema={
                    "asset_types": [
                        "user_story",
                        "feature_list",
                        "exception_flow",
                        "acceptance_criteria",
                    ]
                },
                default_generation_modes=[
                    {"code": "user_story", "name": "用户故事"},
                ],
            ),
        }
        self.projects = {
            "project-1": ContentProject(
                id="project-1",
                workspace_id="ws-1",
                scenario_code="novel_writing",
                title="雾城手记",
                created_by="user-1",
            ),
            "project-2": ContentProject(
                id="project-2",
                workspace_id="ws-1",
                scenario_code="marketing_copy",
                title="品牌战役",
                created_by="user-1",
            ),
        }
        self.assets = {
            "asset-1": ProjectAsset(
                id="asset-1",
                project_id="project-1",
                asset_type="character_card",
                title="林澈",
                content={"name": "林澈", "trait": "谨慎但执着"},
                created_by="user-1",
            )
        }
        self.versions = {
            "asset-1": [
                ProjectAssetVersion(
                    id="version-asset-1-1",
                    asset_id="asset-1",
                    version=1,
                    content={"name": "林澈", "trait": "谨慎但执着"},
                    created_by="user-1",
                )
            ]
        }
        self.created_assets = []

    async def list_templates(self):
        return list(self.templates.values())

    async def get_template(self, scenario_code: str):
        template = self.templates.get(scenario_code)
        if template is None:
            raise ValueError("场景模板不存在")
        return template

    async def create_project(
        self,
        *,
        workspace_id: str,
        user_id: str,
        scenario_code: str,
        title: str,
        description: str | None = None,
        config: dict | None = None,
    ):
        await self.get_template(scenario_code)
        project_id = f"project-{len(self.projects) + 1}"
        project = ContentProject(
            id=project_id,
            workspace_id=workspace_id,
            scenario_code=scenario_code,
            title=title,
            description=description,
            config=config or {},
            created_by=user_id,
        )
        self.projects[project_id] = project
        return project

    async def list_projects(
        self, *, workspace_id: str, scenario_code: str | None = None, status=None
    ):
        return [
            project
            for project in self.projects.values()
            if project.workspace_id == workspace_id
            and (scenario_code is None or project.scenario_code == scenario_code)
            and (status is None or project.status == status)
        ]

    async def get_project_model(self, *, project_id: str, workspace_id: str):
        project = self.projects.get(project_id)
        if project is None or project.workspace_id != workspace_id:
            raise ValueError("内容项目不存在")
        return project

    async def validate_project_run_context(self, **kwargs):
        project = await self.get_project_model(
            project_id=kwargs["project_id"],
            workspace_id=kwargs["workspace_id"],
        )
        scenario_code = kwargs.get("scenario_code")
        if scenario_code and scenario_code != project.scenario_code:
            raise ValueError("场景与内容项目不匹配")

        generation_mode = kwargs.get("generation_mode")
        if generation_mode:
            template = await self.get_template(project.scenario_code)
            allowed_modes = {
                mode["code"]
                for mode in template.default_generation_modes
                if isinstance(mode, dict) and mode.get("code")
            }
            if generation_mode not in allowed_modes:
                raise ValueError("生成模式不属于当前场景模板")

        target_asset_id = kwargs.get("target_asset_id")
        if target_asset_id:
            asset = self.assets.get(target_asset_id)
            if asset is None or asset.project_id != project.id:
                raise ValueError("目标资产不属于当前内容项目")
        return project

    async def list_assets(
        self, *, project_id: str, workspace_id: str, asset_type: str | None = None
    ):
        await self.get_project_model(project_id=project_id, workspace_id=workspace_id)
        return [
            asset
            for asset in self.assets.values()
            if asset.project_id == project_id
            and (asset_type is None or asset.asset_type == asset_type)
        ]

    async def get_asset(self, *, asset_id: str, workspace_id: str):
        asset = self.assets.get(asset_id)
        if asset is None:
            raise ValueError("项目资产不存在")
        await self.get_project_model(project_id=asset.project_id, workspace_id=workspace_id)
        return asset

    async def create_asset(self, **kwargs):
        project = await self.get_project_model(
            project_id=kwargs["project_id"],
            workspace_id=kwargs["workspace_id"],
        )
        template = await self.get_template(project.scenario_code)
        allowed_asset_types = set(template.artifact_schema.get("asset_types") or [])
        if allowed_asset_types and kwargs["asset_type"] not in allowed_asset_types:
            raise ValueError("资产类型不属于当前场景模板")

        asset_id = f"asset-created-{len(self.created_assets) + 1}"
        asset = ProjectAsset(
            id=asset_id,
            project_id=kwargs["project_id"],
            asset_type=kwargs["asset_type"],
            title=kwargs["title"],
            content=kwargs["content"],
            source_artifact_id=kwargs.get("source_artifact_id"),
            metadata=kwargs.get("metadata") or {},
            created_by=kwargs["user_id"],
        )
        self.assets[asset_id] = asset
        self.versions[asset_id] = [
            ProjectAssetVersion(
                id=f"version-{asset_id}-1",
                asset_id=asset_id,
                version=1,
                content=asset.content,
                source_artifact_id=asset.source_artifact_id,
                metadata=asset.metadata,
                created_by=asset.created_by,
            )
        ]
        self.created_assets.append(asset)
        return asset

    async def update_asset(
        self,
        *,
        asset_id: str,
        workspace_id: str,
        user_id: str,
        title: str | None = None,
        content=None,
        source_artifact_id: str | None = None,
        metadata: dict | None = None,
        embedding_status=None,
    ):
        asset = await self.get_asset(asset_id=asset_id, workspace_id=workspace_id)
        update = {
            "title": title if title is not None else asset.title,
            "content": content if content is not None else asset.content,
            "source_artifact_id": source_artifact_id
            if source_artifact_id is not None
            else asset.source_artifact_id,
            "metadata": metadata if metadata is not None else asset.metadata,
            "embedding_status": embedding_status
            if embedding_status is not None
            else asset.embedding_status,
            "version": asset.version + 1 if content is not None else asset.version,
        }
        updated = asset.model_copy(update=update)
        self.assets[asset_id] = updated
        if content is not None:
            self.versions.setdefault(asset_id, []).insert(
                0,
                ProjectAssetVersion(
                    id=f"version-{asset_id}-{updated.version}",
                    asset_id=asset_id,
                    version=updated.version,
                    content=updated.content,
                    source_artifact_id=updated.source_artifact_id,
                    metadata=updated.metadata,
                    created_by=user_id,
                ),
            )
        return updated

    async def list_asset_versions(self, *, asset_id: str, workspace_id: str):
        await self.get_asset(asset_id=asset_id, workspace_id=workspace_id)
        return sorted(self.versions.get(asset_id, []), key=lambda item: item.version, reverse=True)

    async def restore_asset_version(
        self,
        *,
        asset_id: str,
        workspace_id: str,
        user_id: str,
        version: int,
    ):
        asset = await self.get_asset(asset_id=asset_id, workspace_id=workspace_id)
        selected = next(
            (item for item in self.versions.get(asset_id, []) if item.version == version),
            None,
        )
        if selected is None:
            raise ValueError("资产版本不存在")
        restored = asset.model_copy(
            update={
                "content": selected.content,
                "source_artifact_id": selected.source_artifact_id,
                "metadata": {**selected.metadata, "restored_from_version": version},
                "version": asset.version + 1,
            }
        )
        self.assets[asset_id] = restored
        self.versions.setdefault(asset_id, []).insert(
            0,
            ProjectAssetVersion(
                id=f"version-{asset_id}-{restored.version}",
                asset_id=asset_id,
                version=restored.version,
                content=restored.content,
                source_artifact_id=restored.source_artifact_id,
                metadata=restored.metadata,
                created_by=user_id,
            ),
        )
        return restored

    async def sync_asset_to_knowledge(self, **kwargs):
        asset = await self.get_asset(
            asset_id=kwargs["asset_id"], workspace_id=kwargs["workspace_id"]
        )
        updated = asset.model_copy(update={"embedding_status": "ready"})
        self.assets[asset.id] = updated
        return updated


def _client(monkeypatch, *, role: str = "editor"):
    async def _allow_workspace_permission(request, resource: str, action: str):
        return "user-1", "ws-1", role

    async def _fake_current_user(request):
        return {
            "id": "user-1",
            "sub": "user-1",
            "workspace_id": "ws-1",
            "default_workspace_id": "ws-1",
        }

    class _Session:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _PostgresStore:
        def initialized_session(self):
            return _Session()

    async def _skip_workflow_audit(*args, **kwargs):
        return None

    fake_store = _FakeStore()
    fake_workflow = _FakeWorkflow()
    fake_scenario_service = _FakeScenarioService()
    monkeypatch.setattr(
        workflow_helpers,
        "require_workspace_permission",
        _allow_workspace_permission,
        raising=False,
    )
    monkeypatch.setattr("routes.auth_routes.get_current_user", _fake_current_user)
    monkeypatch.setattr("routes.scenario_routes.get_postgres_store", lambda: _PostgresStore())
    monkeypatch.setattr("routes.workflow_routes.get_postgres_store", lambda: _PostgresStore())
    monkeypatch.setattr("routes.workflow_routes._record_workflow_audit", _skip_workflow_audit)
    monkeypatch.setattr(
        "routes.scenario_routes.ScenarioService", lambda session: fake_scenario_service
    )
    monkeypatch.setattr(
        "services.scenario_service.ScenarioService", lambda session: fake_scenario_service
    )
    monkeypatch.setattr("graph.executor.get_workflow", lambda: fake_workflow, raising=False)
    monkeypatch.setattr("graph.get_workflow", lambda: fake_workflow, raising=False)
    monkeypatch.setattr("services.get_artifact_store", lambda: fake_store)
    monkeypatch.setattr(
        "routes.workflow_helpers.get_artifact_store", lambda: fake_store, raising=False
    )

    client = TestClient(app)
    client.cookies.set(
        ACCESS_TOKEN_COOKIE,
        create_access_token(user_id="user-1", workspace_id="ws-1"),
    )
    return client, fake_workflow, fake_store, fake_scenario_service


def test_scenario_project_api_smoke_covers_assets_versions_and_boundaries(monkeypatch):
    client, _, _, _ = _client(monkeypatch)

    scenario_response = client.get("/api/scenarios")
    assert scenario_response.status_code == 200
    assert {item["code"] for item in scenario_response.json()["scenarios"]} >= {
        "novel_writing",
        "marketing_copy",
        "short_video_script",
        "prd",
    }

    project_response = client.post(
        "/api/content-projects",
        json={
            "scenario_code": "novel_writing",
            "title": "星潮纪元",
            "description": "长篇科幻小说项目",
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]
    assert project_response.json()["scenario_code"] == "novel_writing"

    list_response = client.get("/api/content-projects?scenario_code=novel_writing")
    assert list_response.status_code == 200
    assert project_id in {item["id"] for item in list_response.json()["projects"]}

    asset_response = client.post(
        f"/api/content-projects/{project_id}/assets",
        json={
            "asset_type": "story_bible",
            "title": "故事圣经",
            "content": {"promise": "寻找星潮失序的真相"},
        },
    )
    assert asset_response.status_code == 200
    asset = asset_response.json()
    assert asset["version"] == 1

    invalid_asset_response = client.post(
        f"/api/content-projects/{project_id}/assets",
        json={
            "asset_type": "brand_voice",
            "title": "错误资产",
            "content": {"voice": "sharp"},
        },
    )
    assert invalid_asset_response.status_code == 400

    update_response = client.patch(
        f"/api/project-assets/{asset['id']}",
        json={"content": {"promise": "寻找星潮失序与灯塔坠落的真相"}},
    )
    assert update_response.status_code == 200
    assert update_response.json()["version"] == 2

    versions_response = client.get(f"/api/project-assets/{asset['id']}/versions")
    assert versions_response.status_code == 200
    assert [item["version"] for item in versions_response.json()["versions"]] == [2, 1]

    restore_response = client.post(
        f"/api/project-assets/{asset['id']}/restore",
        json={"version": 1},
    )
    assert restore_response.status_code == 200
    assert restore_response.json()["version"] == 3
    assert restore_response.json()["metadata"]["restored_from_version"] == 1

    assets_response = client.get(f"/api/content-projects/{project_id}/assets")
    assert assets_response.status_code == 200
    assert {item["id"] for item in assets_response.json()["assets"]} == {asset["id"]}


def test_project_run_starts_workflow_with_project_metadata(monkeypatch):
    client, fake_workflow, _, _ = _client(monkeypatch)

    response = client.post(
        "/api/content-projects/project-1/runs",
        json={
            "user_input": "续写林澈进入雾城的场景",
            "generation_mode": "continue_scene",
            "target_asset_id": "asset-1",
        },
    )

    assert response.status_code == 200
    assert response.json()["workflow_run_id"] == "wf-project"
    assert fake_workflow.calls[0]["project_id"] == "project-1"
    assert fake_workflow.calls[0]["scenario_code"] == "novel_writing"
    assert fake_workflow.calls[0]["workflow_definition_id"] == "workflow-definition-novel"
    assert fake_workflow.calls[0]["workflow_version_id"] == "workflow-version-novel"
    assert fake_workflow.calls[0]["generation_mode"] == "continue_scene"
    assert fake_workflow.calls[0]["target_asset_id"] == "asset-1"


def test_project_runs_list_filters_by_project(monkeypatch):
    client, _, _, _ = _client(monkeypatch)

    response = client.get("/api/content-projects/project-1/runs")

    assert response.status_code == 200
    body = response.json()
    assert [run["id"] for run in body["runs"]] == ["wf-project"]
    assert body["runs"][0]["metadata"]["scenario_code"] == "novel_writing"
    assert (
        body["runs"][0]["metadata"]["project_memory_update_candidates"][0]["asset_type"]
        == "scene_draft"
    )


def test_apply_memory_updates_creates_project_asset(monkeypatch):
    client, _, _, _ = _client(monkeypatch)

    response = client.post(
        "/api/content-projects/project-1/memory-updates/apply",
        json={"workflow_run_id": "wf-project", "candidate_indexes": [0]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["assets"][0]["asset_type"] == "scene_draft"
    assert body["assets"][0]["source_artifact_id"] == "artifact-candidates"


def test_project_run_rejects_invalid_generation_mode(monkeypatch):
    client, _, _, _ = _client(monkeypatch)

    response = client.post(
        "/api/content-projects/project-1/runs",
        json={
            "user_input": "生成错误模式",
            "generation_mode": "xiaohongshu_post",
        },
    )

    assert response.status_code == 400
    assert response.json()["message"] == "生成模式不属于当前场景模板"


def test_direct_workflow_start_validates_project_context_and_passes_metadata(monkeypatch):
    client, fake_workflow, _, _ = _client(monkeypatch)

    response = client.post(
        "/api/workflow/start",
        json={
            "user_input": "续写项目场景",
            "project_id": "project-1",
            "scenario_code": "novel_writing",
            "generation_mode": "continue_scene",
            "target_asset_id": "asset-1",
        },
    )

    assert response.status_code == 200
    call = fake_workflow.calls[-1]
    assert call["project_id"] == "project-1"
    assert call["scenario_code"] == "novel_writing"
    assert call["workflow_definition_id"] == "workflow-definition-novel"
    assert call["workflow_version_id"] == "workflow-version-novel"
    assert call["generation_mode"] == "continue_scene"
    assert call["target_asset_id"] == "asset-1"

    mismatch_response = client.post(
        "/api/workflow/start",
        json={
            "user_input": "错误场景",
            "project_id": "project-1",
            "scenario_code": "marketing_copy",
        },
    )
    assert mismatch_response.status_code == 400
