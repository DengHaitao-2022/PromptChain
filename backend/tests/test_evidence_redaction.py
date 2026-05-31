import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import routes.workflow_helpers as workflow_helpers


class _WorkflowRun:
    def __init__(self, user_id: str):
        self.metadata = {"user_id": user_id, "workspace_id": "ws-1"}


def _evidence_pack():
    return {
        "query": "私有资料里的发布策略",
        "scopes": ["workspace", "personal"],
        "chunks": [
            {
                "chunk_id": "workspace-chunk",
                "document_id": "workspace-doc",
                "document_name": "团队手册.md",
                "scope": "workspace",
                "score": 0.91,
                "content": "团队公开资料内容",
                "heading_path": ["公开章节"],
                "page_number": 1,
                "metadata": {"source": "workspace"},
            },
            {
                "chunk_id": "personal-chunk",
                "document_id": "personal-doc",
                "document_name": "我的笔记.md",
                "scope": "personal",
                "score": 0.89,
                "content": "仅资料所有者可见的个人原文",
                "heading_path": ["私有章节"],
                "page_number": 2,
                "metadata": {"source": "personal"},
            },
        ],
        "conflicts": [],
        "unverified_points": [],
    }


def test_simplify_state_redacts_personal_evidence_for_non_owner_viewer():
    state = {"evidence_pack": _evidence_pack()}

    simplified = workflow_helpers._simplify_state(
        state,
        workflow_run=_WorkflowRun("run-owner"),
        viewer_user_id="workspace-admin",
    )

    chunks = simplified["evidence_pack"]["chunks"]
    assert chunks[0]["content"] == "团队公开资料内容"
    assert chunks[1]["document_name"] == "个人知识库资料"
    assert chunks[1]["content"] == "该证据来自运行发起人的个人知识库，当前账号无权查看原文。"
    assert chunks[1]["metadata"] == {}
    assert chunks[1]["redacted"] is True


def test_simplify_state_keeps_personal_evidence_for_run_owner():
    state = {"evidence_pack": _evidence_pack()}

    simplified = workflow_helpers._simplify_state(
        state,
        workflow_run=_WorkflowRun("run-owner"),
        viewer_user_id="run-owner",
    )

    assert simplified["evidence_pack"]["chunks"][1]["document_name"] == "我的笔记.md"
    assert simplified["evidence_pack"]["chunks"][1]["content"] == "仅资料所有者可见的个人原文"


def test_trace_artifact_redaction_covers_artifacts_and_history():
    artifact = {
        "id": "artifact-1",
        "type": "evidence_pack",
        "content": _evidence_pack(),
    }
    trace = {
        "workflow": {"id": "run-1"},
        "artifacts": {"artifact-1": artifact},
        "timeline": [],
    }
    workflow_run = _WorkflowRun("run-owner")

    redacted_trace = workflow_helpers.redact_trace_payload_for_viewer(
        trace,
        workflow_run=workflow_run,
        viewer_user_id="workspace-admin",
    )
    redacted_history = workflow_helpers.redact_artifact_history_for_viewer(
        [artifact],
        workflow_run=workflow_run,
        viewer_user_id="workspace-admin",
    )

    assert (
        redacted_trace["artifacts"]["artifact-1"]["content"]["chunks"][1]["content"]
        == "该证据来自运行发起人的个人知识库，当前账号无权查看原文。"
    )
    assert (
        redacted_history[0]["content"]["chunks"][1]["content"]
        == "该证据来自运行发起人的个人知识库，当前账号无权查看原文。"
    )
    assert artifact["content"]["chunks"][1]["content"] == "仅资料所有者可见的个人原文"


def test_rerun_options_redacts_evidence_artifacts_for_non_owner_viewer():
    artifact = {
        "id": "artifact-1",
        "type": "evidence_pack",
        "content": _evidence_pack(),
    }
    options = [
        {
            "node_name": "retrieve_knowledge",
            "output_artifacts": [artifact],
            "can_rerun": True,
        }
    ]

    redacted = workflow_helpers.redact_rerun_options_for_viewer(
        options,
        workflow_run=_WorkflowRun("run-owner"),
        viewer_user_id="workspace-admin",
    )

    personal_chunk = redacted[0]["output_artifacts"][0]["content"]["chunks"][1]
    assert personal_chunk["document_name"] == "个人知识库资料"
    assert personal_chunk["content"] == "该证据来自运行发起人的个人知识库，当前账号无权查看原文。"
    assert personal_chunk["redacted"] is True
    assert artifact["content"]["chunks"][1]["content"] == "仅资料所有者可见的个人原文"
