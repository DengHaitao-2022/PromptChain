"""知识检索节点。"""

from __future__ import annotations

from core.time import utc_now_naive
from graph.runtime_plan import runtime_feature_enabled
from models import (
    ArtifactType,
    EvidencePack,
    KnowledgeSearchRequest,
    NodeRun,
    NodeRunStatus,
    RetrievalConfig,
)
from services import get_artifact_store, get_postgres_store
from services.knowledge_service import KnowledgeService


def _build_retrieval_query(state: dict) -> str:
    """从意图卡和用户输入构造检索 query。"""
    intent_card = state.get("intent_card")
    if intent_card is None:
        return str(state.get("user_input") or "").strip()

    topic = getattr(intent_card, "topic", "") or ""
    goal = getattr(intent_card, "goal", "") or ""
    must_include = getattr(intent_card, "must_include", []) or []
    query_parts = [topic, goal, " ".join(must_include), str(state.get("user_input") or "")]
    return " ".join(part for part in query_parts if part).strip()


def _restore_retrieval_config(state: dict) -> RetrievalConfig:
    """从 GraphState 恢复检索配置。"""
    raw_config = state.get("retrieval_config")
    try:
        return RetrievalConfig.from_raw(raw_config)
    except Exception:
        return RetrievalConfig()


def _empty_evidence_pack(state: dict, retrieval_config: RetrievalConfig) -> EvidencePack:
    """构造跳过态证据包，保证详情页和后续节点有稳定的检索结果结构。"""
    query = _build_retrieval_query(state) or str(state.get("user_input") or "").strip()
    return EvidencePack(
        query=query,
        scopes=retrieval_config.to_scopes(),
        retrieval_mode=retrieval_config.mode,
    )


async def retrieve_knowledge(state: dict) -> dict:
    """按当前用户与工作空间权限生成 Evidence Artifact。"""
    retrieval_config = _restore_retrieval_config(state)
    if not retrieval_config.enabled or not runtime_feature_enabled(
        state,
        "knowledge_retrieval",
        default=True,
    ):
        evidence_pack = _empty_evidence_pack(state, retrieval_config)
        return {
            **state,
            "retrieval_config": retrieval_config,
            "evidence_pack": evidence_pack,
            "evidence_artifact_id": None,
            "citations": [],
            "knowledge_conflicts": [],
            "unverified_points": [],
        }

    workflow_run_id = state["workflow_run_id"]
    workspace_id = state.get("workspace_id")
    user_id = state.get("user_id")
    store = get_artifact_store()

    node_run = NodeRun(
        workflow_run_id=workflow_run_id,
        node_name="retrieve_knowledge",
        node_type="process",
        started_at=utc_now_naive(),
        status=NodeRunStatus.RUNNING,
        input_artifact_ids=[
            artifact_id for artifact_id in [state.get("intent_card_artifact_id")] if artifact_id
        ],
    )
    await store.create_node_run(node_run)

    try:
        query = _build_retrieval_query(state)
        if not workspace_id or not user_id or not query:
            evidence_pack = EvidencePack(
                query=query or str(state.get("user_input") or ""),
                scopes=retrieval_config.to_scopes(),
                unverified_points=[query or "缺少检索上下文"],
                retrieval_mode=retrieval_config.mode,
            )
            retrieval_log_id = None
        else:
            async with get_postgres_store().initialized_session() as session:
                response = await KnowledgeService(session).search(
                    request=KnowledgeSearchRequest(
                        workspace_id=workspace_id,
                        query=query,
                        scopes=retrieval_config.to_scopes(),
                        top_k=retrieval_config.top_k,
                        min_score=retrieval_config.min_score,
                        mode=retrieval_config.mode,
                        enable_query_rewrite=retrieval_config.enable_query_rewrite,
                        enable_multi_query=retrieval_config.enable_multi_query,
                        enable_rerank=retrieval_config.enable_rerank,
                        enable_context_compression=retrieval_config.enable_context_compression,
                        enable_conflict_detection=retrieval_config.enable_conflict_detection,
                        workflow_run_id=workflow_run_id,
                        node_run_id=node_run.id,
                    ),
                    workspace_id=workspace_id,
                    user_id=user_id,
                )
                evidence_pack = response.evidence_pack
                retrieval_log_id = response.retrieval_log_id

        artifact = await store.create_artifact(
            artifact_type=ArtifactType.EVIDENCE_PACK,
            content=evidence_pack.model_dump(mode="json"),
            workflow_run_id=workflow_run_id,
            node_run_id=node_run.id,
            metadata={
                "retrieval_log_id": retrieval_log_id,
                "chunk_count": len(evidence_pack.chunks),
                "conflict_count": len(evidence_pack.conflicts),
                "unverified_count": len(evidence_pack.unverified_points),
            },
        )
        node_run.output_artifact_ids.append(artifact.id)
        node_run.complete(NodeRunStatus.COMPLETED)
        await store.update_node_run(node_run)

        citations = [
            {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "document_name": chunk.document_name,
                "score": chunk.score,
                "scope": chunk.scope.value,
                "page_number": chunk.page_number,
                "heading_path": chunk.heading_path,
            }
            for chunk in evidence_pack.chunks
        ]
        return {
            **state,
            "retrieval_config": retrieval_config,
            "evidence_pack": evidence_pack,
            "evidence_artifact_id": artifact.id,
            "citations": citations,
            "knowledge_conflicts": [
                conflict.model_dump(mode="json") for conflict in evidence_pack.conflicts
            ],
            "unverified_points": list(evidence_pack.unverified_points),
        }
    except Exception as exc:
        node_run.complete(NodeRunStatus.FAILED, str(exc))
        await store.update_node_run(node_run)
        raise
