import asyncio
import importlib
import sys
from datetime import timedelta
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.datastructures import UploadFile
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import routes.workflow_helpers as workflow_helpers
from core.config import get_settings
from core.time import utc_now_naive
from db.postgres_store import Base
from models.auth_models import MemberRole
from models.auth_orm import MembershipORM, UserORM, WorkspaceORM
from models.knowledge import (
    GenerationFaithfulnessCase,
    GenerationFaithfulnessEvaluationRequest,
    KnowledgeDocumentLifecycleStatus,
    KnowledgeScope,
    KnowledgeSearchRequest,
    RetrievalEvaluationCase,
    RetrievalEvaluationRequest,
)
from orm.knowledge_orm import (
    KnowledgeBaseORM,
    KnowledgeDocumentORM,
    KnowledgeEmbeddingORM,
    KnowledgeRetrievalEvaluationRunORM,
)
from routes import knowledge_routes
from routes.workflow_routes import _read_run_upload_documents
from services import knowledge_index_worker
from services.knowledge_object_storage import LocalKnowledgeObjectStorage
from services.knowledge_service import KnowledgeService


@pytest.fixture
def run_with_knowledge_session(tmp_path, monkeypatch):
    def _run(scenario):
        async def _run_scenario():
            monkeypatch.setenv("KNOWLEDGE_STORAGE_DIR", str(tmp_path / "knowledge"))
            monkeypatch.setenv("KNOWLEDGE_EMBEDDING_DIMENSION", "32")
            get_settings.cache_clear()

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
                            UserORM(
                                id="user-other",
                                email="other@example.com",
                                password_hash="x",
                                status="active",
                                email_verified=True,
                            ),
                            WorkspaceORM(id="ws-1", name="默认空间", owner_id="user-owner"),
                            MembershipORM(
                                id="membership-owner",
                                user_id="user-owner",
                                workspace_id="ws-1",
                                role=MemberRole.VIEWER.value,
                            ),
                            MembershipORM(
                                id="membership-other",
                                user_id="user-other",
                                workspace_id="ws-1",
                                role=MemberRole.VIEWER.value,
                            ),
                        ]
                    )
                    await session.commit()
                    await scenario(session)
            finally:
                await engine.dispose()
                get_settings.cache_clear()

        # 当前项目未安装 pytest-asyncio，测试用同步包装保持依赖面最小。
        asyncio.run(_run_scenario())

    return _run


def test_personal_owner_can_manage_without_workspace_write_permission(run_with_knowledge_session):
    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)

        kb = await service.create_knowledge_base(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.VIEWER,
            name="个人笔记",
            description=None,
            scope=KnowledgeScope.PERSONAL,
        )
        document = await service.add_document(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.VIEWER,
            file_name="style.md",
            content=b"# Tone\nUse concise personal style.",
        )

        assert document.version == 1
        assert document.status == KnowledgeDocumentLifecycleStatus.ACTIVE

        search = await service.search(
            request=KnowledgeSearchRequest(
                query="personal concise style",
                scopes=[KnowledgeScope.PERSONAL],
                top_k=5,
                min_score=0.0,
            ),
            workspace_id="ws-1",
            user_id="user-owner",
        )

        assert [chunk.document_id for chunk in search.evidence_pack.chunks] == [document.id]

    run_with_knowledge_session(scenario)


def test_personal_documents_are_hidden_from_other_workspace_members(run_with_knowledge_session):
    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)
        kb = await service.create_knowledge_base(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.VIEWER,
            name="私有资料",
            description=None,
            scope=KnowledgeScope.PERSONAL,
        )
        await service.add_document(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.VIEWER,
            file_name="private.md",
            content=b"secret roadmap alpha",
        )

        search = await service.search(
            request=KnowledgeSearchRequest(
                query="secret roadmap",
                scopes=[KnowledgeScope.PERSONAL],
                top_k=5,
                min_score=0.0,
            ),
            workspace_id="ws-1",
            user_id="user-other",
        )

        assert search.evidence_pack.chunks == []
        assert search.evidence_pack.unverified_points == ["secret roadmap"]

    run_with_knowledge_session(scenario)


def test_workspace_kb_requires_create_and_update_permissions(run_with_knowledge_session):
    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)

        with pytest.raises(ValueError, match=r"knowledge_base\.create"):
            await service.create_knowledge_base(
                workspace_id="ws-1",
                user_id="user-owner",
                role=MemberRole.VIEWER,
                name="团队资料",
                description=None,
                scope=KnowledgeScope.WORKSPACE,
            )

        editor_kb = await service.create_knowledge_base(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.EDITOR,
            name="编辑资料",
            description=None,
            scope=KnowledgeScope.WORKSPACE,
        )
        assert editor_kb.name == "编辑资料"

        kb = await service.create_knowledge_base(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            name="团队资料",
            description=None,
            scope=KnowledgeScope.WORKSPACE,
        )

        with pytest.raises(ValueError, match=r"knowledge_base\.update"):
            await service.add_document(
                kb_id=kb.id,
                workspace_id="ws-1",
                user_id="user-other",
                role=MemberRole.VIEWER,
                file_name="manual.md",
                content=b"workspace authoritative source",
            )

    run_with_knowledge_session(scenario)


def test_new_document_version_archives_old_version_and_search_uses_latest(
    run_with_knowledge_session,
):
    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)
        kb = await service.create_knowledge_base(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            name="团队资料",
            description=None,
            scope=KnowledgeScope.WORKSPACE,
        )
        first = await service.add_document(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            file_name="policy.md",
            content=b"Legacy policy forbids beta launch.",
        )
        second = await service.add_document(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            file_name="policy.md",
            content=b"Current policy allows beta launch.",
        )

        documents = await service.list_documents(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
        )

        assert [(document.version, document.status) for document in documents] == [
            (2, KnowledgeDocumentLifecycleStatus.ACTIVE),
            (1, KnowledgeDocumentLifecycleStatus.ARCHIVED),
        ]

        search = await service.search(
            request=KnowledgeSearchRequest(
                query="beta launch policy",
                scopes=[KnowledgeScope.WORKSPACE],
                top_k=5,
                min_score=0.0,
            ),
            workspace_id="ws-1",
            user_id="user-owner",
        )

        assert [chunk.document_id for chunk in search.evidence_pack.chunks] == [second.id]
        assert first.id not in [chunk.document_id for chunk in search.evidence_pack.chunks]

    run_with_knowledge_session(scenario)


def test_disabled_and_deleted_documents_are_not_retrieved(run_with_knowledge_session):
    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)
        kb = await service.create_knowledge_base(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            name="团队资料",
            description=None,
            scope=KnowledgeScope.WORKSPACE,
        )
        document = await service.add_document(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            file_name="guide.md",
            content=b"retrieval target sentence",
        )

        await service.update_document_status(
            document_id=document.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            status=KnowledgeDocumentLifecycleStatus.DISABLED,
        )
        disabled_search = await service.search(
            request=KnowledgeSearchRequest(
                query="retrieval target",
                scopes=[KnowledgeScope.WORKSPACE],
                top_k=5,
                min_score=0.0,
            ),
            workspace_id="ws-1",
            user_id="user-owner",
        )
        assert disabled_search.evidence_pack.chunks == []

        await service.update_document_status(
            document_id=document.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            status=KnowledgeDocumentLifecycleStatus.ACTIVE,
        )
        await service.delete_document(
            document_id=document.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
        )

        deleted_search = await service.search(
            request=KnowledgeSearchRequest(
                query="retrieval target",
                scopes=[KnowledgeScope.WORKSPACE],
                top_k=5,
                min_score=0.0,
            ),
            workspace_id="ws-1",
            user_id="user-owner",
        )
        assert deleted_search.evidence_pack.chunks == []

        embedding_count = (
            await knowledge_session.execute(KnowledgeEmbeddingORM.__table__.select())
        ).all()
        assert embedding_count == []

    run_with_knowledge_session(scenario)


def test_knowledge_base_delete_cascades_index_rows(run_with_knowledge_session):
    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)
        kb = await service.create_knowledge_base(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            name="团队资料",
            description=None,
            scope=KnowledgeScope.WORKSPACE,
        )
        await service.add_document(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            file_name="manual.md",
            content=b"cascade cleanup source",
        )

        await service.delete_knowledge_base(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
        )

        for table in (KnowledgeBaseORM, KnowledgeDocumentORM, KnowledgeEmbeddingORM):
            rows = (await knowledge_session.execute(table.__table__.select())).all()
            assert rows == []

    run_with_knowledge_session(scenario)


def test_run_upload_documents_are_scoped_to_workflow_run(run_with_knowledge_session):
    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)
        with pytest.raises(ValueError, match="workflow_run_id"):
            await service.create_knowledge_base(
                workspace_id="ws-1",
                user_id="user-owner",
                role=MemberRole.VIEWER,
                name="未绑定运行资料",
                description=None,
                scope=KnowledgeScope.RUN_UPLOAD,
            )

        kb = await service.create_knowledge_base(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.VIEWER,
            name="本次运行资料",
            description=None,
            scope=KnowledgeScope.RUN_UPLOAD,
            workflow_run_id="run-1",
        )
        document = await service.add_document(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.VIEWER,
            file_name="brief.md",
            content=b"run scoped retrieval evidence",
        )

        wrong_run_search = await service.search(
            request=KnowledgeSearchRequest(
                query="run scoped retrieval",
                scopes=[KnowledgeScope.RUN_UPLOAD],
                top_k=5,
                min_score=0.0,
                workflow_run_id="run-2",
            ),
            workspace_id="ws-1",
            user_id="user-owner",
        )
        no_run_search = await service.search(
            request=KnowledgeSearchRequest(
                query="run scoped retrieval",
                scopes=[KnowledgeScope.RUN_UPLOAD],
                top_k=5,
                min_score=0.0,
            ),
            workspace_id="ws-1",
            user_id="user-owner",
        )
        current_run_search = await service.search(
            request=KnowledgeSearchRequest(
                query="run scoped retrieval",
                scopes=[KnowledgeScope.RUN_UPLOAD],
                top_k=5,
                min_score=0.0,
                workflow_run_id="run-1",
            ),
            workspace_id="ws-1",
            user_id="user-owner",
        )

        assert kb.workflow_run_id == "run-1"
        assert document.workflow_run_id == "run-1"
        assert wrong_run_search.evidence_pack.chunks == []
        assert no_run_search.evidence_pack.chunks == []
        assert [chunk.document_id for chunk in current_run_search.evidence_pack.chunks] == [
            document.id
        ]

    run_with_knowledge_session(scenario)


def test_openai_embedding_without_fallback_marks_document_failed(
    run_with_knowledge_session,
    monkeypatch,
):
    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_FALLBACK_TO_HASH", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)
        kb = await service.create_knowledge_base(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            name="团队资料",
            description=None,
            scope=KnowledgeScope.WORKSPACE,
        )

        document = await service.add_document(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            file_name="embedding.md",
            content=b"openai embedding should fail without api key",
        )

        assert document.index_status == "failed"
        assert "OpenAI embedding" in (document.error_message or "")

    run_with_knowledge_session(scenario)


def test_openai_embedding_can_fallback_to_hash_provider(
    run_with_knowledge_session,
    monkeypatch,
):
    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_FALLBACK_TO_HASH", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)
        kb = await service.create_knowledge_base(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            name="团队资料",
            description=None,
            scope=KnowledgeScope.WORKSPACE,
        )

        document = await service.add_document(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            file_name="fallback.md",
            content=b"fallback embedding should remain searchable",
        )
        embedding = (
            await knowledge_session.execute(KnowledgeEmbeddingORM.__table__.select())
        ).first()

        assert document.index_status == "ready"
        assert embedding is not None
        assert embedding._mapping["embedding_model"] == "promptchain-hash-embedding-v1"

    run_with_knowledge_session(scenario)


def test_private_scope_embedding_uses_hash_by_default_even_when_openai_configured(
    run_with_knowledge_session,
    monkeypatch,
):
    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_FALLBACK_TO_HASH", "false")
    monkeypatch.setenv("KNOWLEDGE_ALLOW_EXTERNAL_EMBEDDING_FOR_PRIVATE_SCOPES", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)
        kb = await service.create_knowledge_base(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.VIEWER,
            name="个人资料",
            description=None,
            scope=KnowledgeScope.PERSONAL,
        )

        document = await service.add_document(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.VIEWER,
            file_name="private.md",
            content=b"private notes must not leave local process",
        )
        embedding = (
            await knowledge_session.execute(KnowledgeEmbeddingORM.__table__.select())
        ).first()

        assert document.index_status == "ready"
        assert embedding is not None
        assert embedding._mapping["embedding_model"] == "promptchain-hash-embedding-v1"

    run_with_knowledge_session(scenario)


def test_private_scope_embedding_can_be_explicitly_allowed_to_use_openai(
    run_with_knowledge_session,
    monkeypatch,
):
    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_FALLBACK_TO_HASH", "false")
    monkeypatch.setenv("KNOWLEDGE_ALLOW_EXTERNAL_EMBEDDING_FOR_PRIVATE_SCOPES", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)
        kb = await service.create_knowledge_base(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.VIEWER,
            name="个人资料",
            description=None,
            scope=KnowledgeScope.PERSONAL,
        )

        document = await service.add_document(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.VIEWER,
            file_name="private.md",
            content=b"private notes may use external embedding only after opt in",
        )

        assert document.index_status == "failed"
        assert "OpenAI embedding" in (document.error_message or "")

    run_with_knowledge_session(scenario)


def test_retrieval_evaluation_reports_hit_rate_mrr_and_precision(run_with_knowledge_session):
    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)
        kb = await service.create_knowledge_base(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            name="团队资料",
            description=None,
            scope=KnowledgeScope.WORKSPACE,
        )
        document = await service.add_document(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            file_name="eval.md",
            content=b"retrieval evaluation golden answer",
        )

        response = await service.evaluate_retrieval(
            request=RetrievalEvaluationRequest(
                cases=[
                    RetrievalEvaluationCase(
                        id="hit-case",
                        query="golden answer",
                        expected_document_ids=[document.id],
                    ),
                    RetrievalEvaluationCase(
                        id="miss-case",
                        query="missing topic",
                        expected_document_ids=["missing-document"],
                    ),
                ],
                scopes=[KnowledgeScope.WORKSPACE],
                top_k=3,
                min_score=0.0,
            ),
            workspace_id="ws-1",
            user_id="user-owner",
        )

        assert response.summary.total_cases == 2
        assert response.summary.hit_count == 1
        assert response.summary.hit_rate == 0.5
        assert response.summary.mean_reciprocal_rank >= 0.5
        assert response.evaluation_run_id is not None
        assert response.results[0].hit is True
        assert response.results[0].first_relevant_rank == 1
        assert response.results[1].hit is False

        runs = await service.list_retrieval_evaluation_runs(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
        )
        assert [run.id for run in runs] == [response.evaluation_run_id]
        assert runs[0].summary.hit_rate == response.summary.hit_rate

        generation_runs = await service.list_evaluation_runs(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            evaluation_type="generation_faithfulness",
        )
        assert generation_runs == []

    run_with_knowledge_session(scenario)


def test_usage_stats_summarizes_current_user_retrieval_logs(run_with_knowledge_session):
    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)
        kb = await service.create_knowledge_base(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            name="团队资料",
            description=None,
            scope=KnowledgeScope.WORKSPACE,
        )
        await service.add_document(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            file_name="stats.md",
            content=b"usage statistics evidence source",
        )

        await service.search(
            request=KnowledgeSearchRequest(
                query="usage statistics",
                scopes=[KnowledgeScope.WORKSPACE],
                top_k=3,
                min_score=0.0,
            ),
            workspace_id="ws-1",
            user_id="user-owner",
        )
        await service.search(
            request=KnowledgeSearchRequest(
                query="missing evidence",
                scopes=[KnowledgeScope.PERSONAL],
                top_k=3,
                min_score=0.0,
            ),
            workspace_id="ws-1",
            user_id="user-owner",
        )
        await service.search(
            request=KnowledgeSearchRequest(
                query="other user query",
                scopes=[KnowledgeScope.WORKSPACE],
                top_k=3,
                min_score=0.0,
            ),
            workspace_id="ws-1",
            user_id="user-other",
        )

        stats = await service.get_usage_stats(workspace_id="ws-1", user_id="user-owner")
        owner_rollup = await service.get_usage_stats(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
        )

        assert stats.total_searches == 2
        assert stats.total_chunks_returned == 1
        assert stats.average_chunks_per_search == 0.5
        assert stats.unverified_search_count == 1
        assert stats.scope_counts == {"workspace": 1, "personal": 1}
        assert stats.mode_counts == {"hybrid": 2}
        assert stats.last_search_at is not None
        assert owner_rollup.total_searches == 3

    run_with_knowledge_session(scenario)


def test_reranker_provider_records_rerank_score(run_with_knowledge_session):
    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)
        kb = await service.create_knowledge_base(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            name="团队资料",
            description=None,
            scope=KnowledgeScope.WORKSPACE,
        )
        await service.add_document(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            file_name="rerank.md",
            content=b"# Rerank\nrerank provider should boost matching heading",
        )

        search = await service.search(
            request=KnowledgeSearchRequest(
                query="rerank provider",
                scopes=[KnowledgeScope.WORKSPACE],
                top_k=3,
                min_score=0.0,
                enable_rerank=True,
            ),
            workspace_id="ws-1",
            user_id="user-owner",
        )

        assert service.reranker_provider.provider_name == "heuristic"
        assert search.evidence_pack.chunks[0].rerank_score is not None

    run_with_knowledge_session(scenario)


def test_async_indexing_keeps_new_document_pending_until_worker_runs(run_with_knowledge_session):
    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)
        kb = await service.create_knowledge_base(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            name="团队资料",
            description=None,
            scope=KnowledgeScope.WORKSPACE,
        )

        document = await service.add_document(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            file_name="async.md",
            content=b"async indexing source",
            index_immediately=False,
        )
        pending_search = await service.search(
            request=KnowledgeSearchRequest(
                query="async indexing source",
                scopes=[KnowledgeScope.WORKSPACE],
                top_k=5,
                min_score=0.0,
            ),
            workspace_id="ws-1",
            user_id="user-owner",
        )

        assert document.parse_status == "pending"
        assert document.index_status == "pending"
        assert pending_search.evidence_pack.chunks == []

        indexed = await service.index_document(document_id=document.id)
        ready_search = await service.search(
            request=KnowledgeSearchRequest(
                query="async indexing source",
                scopes=[KnowledgeScope.WORKSPACE],
                top_k=5,
                min_score=0.0,
            ),
            workspace_id="ws-1",
            user_id="user-owner",
        )

        assert indexed.parse_status == "ready"
        assert indexed.index_status == "ready"
        assert [chunk.document_id for chunk in ready_search.evidence_pack.chunks] == [document.id]

    run_with_knowledge_session(scenario)


def test_async_document_upload_enqueues_index_job(run_with_knowledge_session, monkeypatch):
    enqueued_ids: list[str] = []

    class _Queue:
        async def enqueue(self, document_id: str) -> None:
            enqueued_ids.append(document_id)

        async def read(self, *, count: int, block_ms: int):
            return []

        async def ack(self, job) -> None:
            return None

        async def close(self) -> None:
            return None

    monkeypatch.setenv("KNOWLEDGE_INDEX_QUEUE_BACKEND", "database")
    monkeypatch.setattr("services.knowledge_service.get_knowledge_index_queue", lambda: _Queue())

    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)
        kb = await service.create_knowledge_base(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            name="团队资料",
            description=None,
            scope=KnowledgeScope.WORKSPACE,
        )
        document = await service.add_document(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            file_name="queued.md",
            content=b"queued content",
            index_immediately=False,
        )

        assert enqueued_ids == [document.id]

    run_with_knowledge_session(scenario)


def test_local_knowledge_object_storage_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_STORAGE_DIR", str(tmp_path / "knowledge"))
    get_settings.cache_clear()

    async def scenario():
        storage = LocalKnowledgeObjectStorage()
        uri = await storage.put_document(
            workspace_id="ws-1",
            document_id="doc-1",
            file_name="source.md",
            content=b"object storage content",
        )

        assert await storage.get_bytes(uri) == b"object storage content"
        await storage.delete(uri)
        assert not Path(uri).exists()

    try:
        asyncio.run(scenario())
    finally:
        get_settings.cache_clear()


def test_pending_new_version_does_not_archive_current_active_version(run_with_knowledge_session):
    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)
        kb = await service.create_knowledge_base(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            name="团队资料",
            description=None,
            scope=KnowledgeScope.WORKSPACE,
        )
        first = await service.add_document(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            file_name="policy.md",
            content=b"Old active policy",
        )
        second = await service.add_document(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            file_name="policy.md",
            content=b"New pending policy",
            index_immediately=False,
        )

        pending_documents = await service.list_documents(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
        )
        assert [(item.version, item.status, item.index_status) for item in pending_documents] == [
            (2, KnowledgeDocumentLifecycleStatus.ACTIVE, "pending"),
            (1, KnowledgeDocumentLifecycleStatus.ACTIVE, "ready"),
        ]

        await service.index_document(document_id=second.id)
        ready_documents = await service.list_documents(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
        )
        assert [(item.version, item.status, item.index_status) for item in ready_documents] == [
            (2, KnowledgeDocumentLifecycleStatus.ACTIVE, "ready"),
            (1, KnowledgeDocumentLifecycleStatus.ARCHIVED, "ready"),
        ]
        assert first.version == 1
        assert second.version == 2

    run_with_knowledge_session(scenario)


def test_index_worker_processes_pending_documents(run_with_knowledge_session, monkeypatch):
    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)
        kb = await service.create_knowledge_base(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            name="团队资料",
            description=None,
            scope=KnowledgeScope.WORKSPACE,
        )
        document = await service.add_document(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            file_name="worker.md",
            content=b"worker indexed content",
            index_immediately=False,
        )

        class _SessionContext:
            async def __aenter__(self):
                return knowledge_session

            async def __aexit__(self, exc_type, exc, traceback):
                return False

        class _Store:
            def initialized_session(self):
                return _SessionContext()

        monkeypatch.setattr(knowledge_index_worker, "get_postgres_store", lambda: _Store())

        assert await knowledge_index_worker.index_pending_documents(limit=5) == 1
        indexed = await service.get_document(
            document_id=document.id,
            workspace_id="ws-1",
            user_id="user-owner",
        )
        assert indexed.index_status == "ready"

    run_with_knowledge_session(scenario)


def test_claim_pending_documents_marks_processing_and_skips_second_claim(
    run_with_knowledge_session,
):
    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)
        kb = await service.create_knowledge_base(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            name="团队资料",
            description=None,
            scope=KnowledgeScope.WORKSPACE,
        )
        document = await service.add_document(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            file_name="claim.md",
            content=b"claim once content",
            index_immediately=False,
        )

        first_claim = await service.claim_pending_documents_for_indexing(limit=10)
        second_claim = await service.claim_pending_documents_for_indexing(limit=10)
        row = (
            await knowledge_session.execute(
                select(KnowledgeDocumentORM).where(KnowledgeDocumentORM.id == document.id)
            )
        ).scalar_one()

        assert first_claim == [document.id]
        assert second_claim == []
        assert row.parse_status == "processing"
        assert row.index_status == "processing"

    run_with_knowledge_session(scenario)


def test_claim_pending_documents_retries_stale_processing_documents(
    run_with_knowledge_session,
    monkeypatch,
):
    monkeypatch.setenv("KNOWLEDGE_INDEX_WORKER_STALE_SECONDS", "30")

    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)
        kb = await service.create_knowledge_base(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            name="团队资料",
            description=None,
            scope=KnowledgeScope.WORKSPACE,
        )
        document = await service.add_document(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            file_name="stale.md",
            content=b"stale processing content",
            index_immediately=False,
        )
        await service.claim_pending_documents_for_indexing(limit=1)
        stale_time = utc_now_naive() - timedelta(seconds=120)
        await knowledge_session.execute(
            KnowledgeDocumentORM.__table__.update()
            .where(KnowledgeDocumentORM.id == document.id)
            .values(updated_at=stale_time)
        )
        await knowledge_session.commit()

        retry_claim = await service.claim_pending_documents_for_indexing(limit=1)

        assert retry_claim == [document.id]

    run_with_knowledge_session(scenario)


def test_redis_queue_jobs_ack_after_worker_claims_document(run_with_knowledge_session, monkeypatch):
    from services.knowledge_index_queue import KnowledgeIndexJob

    acked: list[str] = []
    queued_document_id = ""

    class _Queue:
        async def enqueue(self, document_id: str) -> None:
            _ = document_id

        async def read(self, *, count: int, block_ms: int):
            _ = (count, block_ms)
            return [KnowledgeIndexJob(document_id=queued_document_id, message_id="1-0")]

        async def ack(self, job) -> None:
            acked.append(job.message_id)

        async def close(self) -> None:
            return None

    monkeypatch.setenv("KNOWLEDGE_INDEX_QUEUE_BACKEND", "redis")
    monkeypatch.setattr(knowledge_index_worker, "get_knowledge_index_queue", lambda: _Queue())

    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)
        kb = await service.create_knowledge_base(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            name="团队资料",
            description=None,
            scope=KnowledgeScope.WORKSPACE,
        )
        document = await service.add_document(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            file_name="queued-worker.md",
            content=b"queued worker content",
            index_immediately=False,
        )
        nonlocal queued_document_id
        queued_document_id = document.id

        class _SessionContext:
            async def __aenter__(self):
                return knowledge_session

            async def __aexit__(self, exc_type, exc, traceback):
                return False

        class _Store:
            def initialized_session(self):
                return _SessionContext()

        monkeypatch.setattr(knowledge_index_worker, "get_postgres_store", lambda: _Store())

        assert await knowledge_index_worker.index_pending_documents(limit=1) == 1
        assert acked == ["1-0"]

    run_with_knowledge_session(scenario)


def test_upload_rejects_empty_oversized_and_mismatched_binary_files(
    run_with_knowledge_session,
    monkeypatch,
):
    monkeypatch.setenv("KNOWLEDGE_MAX_UPLOAD_BYTES", "8")

    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)
        kb = await service.create_knowledge_base(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            name="团队资料",
            description=None,
            scope=KnowledgeScope.WORKSPACE,
        )

        with pytest.raises(ValueError, match="不能为空"):
            await service.add_document(
                kb_id=kb.id,
                workspace_id="ws-1",
                user_id="user-owner",
                role=MemberRole.OWNER,
                file_name="empty.md",
                content=b"",
            )

        with pytest.raises(ValueError, match="不能超过"):
            await service.add_document(
                kb_id=kb.id,
                workspace_id="ws-1",
                user_id="user-owner",
                role=MemberRole.OWNER,
                file_name="oversized.md",
                content=b"123456789",
            )

        with pytest.raises(ValueError, match="PDF 文件格式校验失败"):
            await service.add_document(
                kb_id=kb.id,
                workspace_id="ws-1",
                user_id="user-owner",
                role=MemberRole.OWNER,
                file_name="fake.pdf",
                content=b"not pdf",
            )

        with pytest.raises(ValueError, match="DOCX 文件格式校验失败"):
            await service.add_document(
                kb_id=kb.id,
                workspace_id="ws-1",
                user_id="user-owner",
                role=MemberRole.OWNER,
                file_name="fake.docx",
                content=b"not docx",
            )

    run_with_knowledge_session(scenario)


def test_run_upload_reuses_knowledge_file_validation():
    async def scenario():
        upload = UploadFile(filename="fake.pdf", file=BytesIO(b"not pdf"))

        with pytest.raises(HTTPException) as exc_info:
            await _read_run_upload_documents([upload])

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "PDF 文件格式校验失败"

    asyncio.run(scenario())


def test_document_count_limit_allows_same_file_version_but_blocks_new_document(
    run_with_knowledge_session,
    monkeypatch,
):
    monkeypatch.setenv("KNOWLEDGE_MAX_DOCUMENTS_PER_KB", "1")

    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)
        kb = await service.create_knowledge_base(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            name="团队资料",
            description=None,
            scope=KnowledgeScope.WORKSPACE,
        )
        first = await service.add_document(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            file_name="policy.md",
            content=b"first version",
        )
        second = await service.add_document(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            file_name="policy.md",
            content=b"second version",
        )

        with pytest.raises(ValueError, match="文档数量不能超过 1 个"):
            await service.add_document(
                kb_id=kb.id,
                workspace_id="ws-1",
                user_id="user-owner",
                role=MemberRole.OWNER,
                file_name="another.md",
                content=b"new active document",
            )

        documents = await service.list_documents(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
        )

        assert first.version == 1
        assert second.version == 2
        assert [document.file_name for document in documents] == ["policy.md", "policy.md"]

    run_with_knowledge_session(scenario)


def test_knowledge_route_store_uses_initialized_sessions(monkeypatch):
    class _FakeStore:
        def __init__(self):
            self.initialized = False

        def initialized_session(self):
            self.initialized = True
            return object()

    store = _FakeStore()
    monkeypatch.setattr(knowledge_routes, "get_postgres_store", lambda: store)

    assert knowledge_routes._postgres_store().initialized_session() is not None
    assert store.initialized is True


def test_knowledge_routes_reject_cross_workspace_list(monkeypatch):
    async def _permission_context(_request: Request, _resource: str, _action: str):
        return "user-owner", "ws-1", MemberRole.OWNER

    monkeypatch.setattr(
        workflow_helpers,
        "require_workspace_permission",
        _permission_context,
        raising=False,
    )

    async def scenario():
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/workspaces/ws-2/knowledge-bases",
                "headers": [],
                "query_string": b"",
                "server": ("testserver", 80),
                "client": ("testclient", 50000),
                "scheme": "http",
            }
        )

        with pytest.raises(HTTPException) as exc_info:
            await knowledge_routes.list_workspace_knowledge_bases("ws-2", request)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "您无权访问该工作空间的知识库"

    asyncio.run(scenario())


def test_knowledge_routes_reject_cross_workspace_search(monkeypatch):
    async def _permission_context(_request: Request, _resource: str, _action: str):
        return "user-owner", "ws-1", MemberRole.OWNER

    monkeypatch.setattr(
        workflow_helpers,
        "require_workspace_permission",
        _permission_context,
        raising=False,
    )

    async def scenario():
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/knowledge/search",
                "headers": [],
                "query_string": b"",
                "server": ("testserver", 80),
                "client": ("testclient", 50000),
                "scheme": "http",
            }
        )

        with pytest.raises(HTTPException) as exc_info:
            await knowledge_routes.search_knowledge(
                request,
                KnowledgeSearchRequest(
                    workspace_id="ws-2",
                    query="跨空间资料",
                    scopes=[KnowledgeScope.WORKSPACE],
                ),
            )

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "您无权检索该工作空间的知识库"

    asyncio.run(scenario())


def test_knowledge_routes_keep_personal_documents_hidden_from_other_members(
    run_with_knowledge_session,
    monkeypatch,
):
    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)
        kb = await service.create_knowledge_base(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.VIEWER,
            name="个人资料",
            description=None,
            scope=KnowledgeScope.PERSONAL,
        )
        await service.add_document(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.VIEWER,
            file_name="private.md",
            content=b"route personal secret",
        )

        class _SessionContext:
            async def __aenter__(self):
                return knowledge_session

            async def __aexit__(self, exc_type, exc, traceback):
                return False

        class _Store:
            def initialized_session(self):
                return _SessionContext()

        async def _permission_context(_request: Request, _resource: str, _action: str):
            return "user-other", "ws-1", MemberRole.VIEWER

        monkeypatch.setattr(knowledge_routes, "get_postgres_store", lambda: _Store())
        monkeypatch.setattr(
            workflow_helpers,
            "require_workspace_permission",
            _permission_context,
            raising=False,
        )
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": f"/api/knowledge-bases/{kb.id}/documents",
                "headers": [],
                "query_string": b"",
                "server": ("testserver", 80),
                "client": ("testclient", 50000),
                "scheme": "http",
            }
        )

        with pytest.raises(HTTPException) as exc_info:
            await knowledge_routes.list_knowledge_documents(kb.id, request)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "知识库不存在或无权访问"

    run_with_knowledge_session(scenario)


def test_knowledge_routes_keep_run_upload_results_bound_to_workflow_run(
    run_with_knowledge_session,
    monkeypatch,
):
    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)
        kb = await service.create_knowledge_base(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.VIEWER,
            name="本次运行资料",
            description=None,
            scope=KnowledgeScope.RUN_UPLOAD,
            workflow_run_id="run-1",
        )
        await service.add_document(
            kb_id=kb.id,
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.VIEWER,
            file_name="run.md",
            content=b"route run upload source",
        )

        class _SessionContext:
            async def __aenter__(self):
                return knowledge_session

            async def __aexit__(self, exc_type, exc, traceback):
                return False

        class _Store:
            def initialized_session(self):
                return _SessionContext()

        async def _permission_context(_request: Request, _resource: str, _action: str):
            return "user-owner", "ws-1", MemberRole.VIEWER

        monkeypatch.setattr(knowledge_routes, "get_postgres_store", lambda: _Store())
        monkeypatch.setattr(
            workflow_helpers,
            "require_workspace_permission",
            _permission_context,
            raising=False,
        )
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/knowledge/search",
                "headers": [],
                "query_string": b"",
                "server": ("testserver", 80),
                "client": ("testclient", 50000),
                "scheme": "http",
            }
        )

        wrong_run = await knowledge_routes.search_knowledge(
            request,
            KnowledgeSearchRequest(
                query="route run upload source",
                scopes=[KnowledgeScope.RUN_UPLOAD],
                top_k=5,
                min_score=0.0,
                workflow_run_id="run-2",
            ),
        )
        current_run = await knowledge_routes.search_knowledge(
            request,
            KnowledgeSearchRequest(
                query="route run upload source",
                scopes=[KnowledgeScope.RUN_UPLOAD],
                top_k=5,
                min_score=0.0,
                workflow_run_id="run-1",
            ),
        )

        assert wrong_run.evidence_pack.chunks == []
        assert [chunk.document_id for chunk in current_run.evidence_pack.chunks]

    run_with_knowledge_session(scenario)


def test_generation_faithfulness_evaluation_persists_summary(run_with_knowledge_session):
    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)
        response = await service.evaluate_generation_faithfulness(
            request=GenerationFaithfulnessEvaluationRequest(
                cases=[
                    GenerationFaithfulnessCase(
                        id="case-1",
                        query="PromptChain 是什么？",
                        answer="PromptChain 使用 Prompt Chain 和 LangGraph 编排内容生成。",
                        contexts=["PromptChain 使用 Prompt Chain 和 LangGraph 编排内容生成。"],
                    )
                ],
            ),
            workspace_id="ws-1",
            user_id="user-owner",
        )

        assert response.evaluation_run_id
        assert response.summary.total_cases == 1
        assert response.summary.provider == "heuristic"
        row = (
            await knowledge_session.execute(
                select(KnowledgeRetrievalEvaluationRunORM).where(
                    KnowledgeRetrievalEvaluationRunORM.id == response.evaluation_run_id
                )
            )
        ).scalar_one()
        assert row.evaluation_type == "generation_faithfulness"
        assert row.summary_json["provider"] == "heuristic"
        runs = await service.list_evaluation_runs(
            workspace_id="ws-1",
            user_id="user-owner",
            role=MemberRole.OWNER,
            evaluation_type="generation_faithfulness",
        )
        assert [run.id for run in runs] == [response.evaluation_run_id]

    run_with_knowledge_session(scenario)


@pytest.mark.asyncio
async def test_disabled_retrieval_returns_empty_evidence_pack():
    importlib.import_module("graph.content_generation_graph")
    from nodes.knowledge_retriever import retrieve_knowledge

    result = await retrieve_knowledge(
        {
            "workflow_run_id": "wf-disabled-retrieval",
            "user_input": "本次运行不启用知识检索",
            "retrieval_config": {"enabled": False},
        }
    )

    assert result["evidence_artifact_id"] is None
    assert result["citations"] == []
    assert result["knowledge_conflicts"] == []
    assert result["unverified_points"] == []
    assert result["evidence_pack"].query == "本次运行不启用知识检索"
    assert result["evidence_pack"].chunks == []
