import asyncio
import importlib
import sys
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import get_settings
from db.postgres_store import Base
from models.auth_models import MemberRole
from models.auth_orm import MembershipORM, UserORM, WorkspaceORM
from models.knowledge import (
    KnowledgeDocumentLifecycleStatus,
    KnowledgeScope,
    KnowledgeSearchRequest,
)
from orm.knowledge_orm import (
    KnowledgeBaseORM,
    KnowledgeDocumentORM,
    KnowledgeEmbeddingORM,
)
from routes import knowledge_routes
from services import knowledge_index_worker
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


def test_workspace_kb_requires_manage_and_update_permissions(run_with_knowledge_session):
    async def scenario(knowledge_session):
        service = KnowledgeService(knowledge_session)

        with pytest.raises(ValueError, match=r"knowledge_base\.manage"):
            await service.create_knowledge_base(
                workspace_id="ws-1",
                user_id="user-owner",
                role=MemberRole.VIEWER,
                name="团队资料",
                description=None,
                scope=KnowledgeScope.WORKSPACE,
            )

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
