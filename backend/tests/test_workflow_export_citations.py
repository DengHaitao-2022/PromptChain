import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.workflow_export_service import build_markdown, build_workflow_export_payload


def test_export_payload_includes_evidence_citations_from_final_artifact():
    trace = {
        "workflow": {"final_artifact_id": "final-1"},
        "artifacts": {
            "final-1": {
                "id": "final-1",
                "type": "final_content",
                "version": 1,
                "created_at": "2026-05-31T00:00:00Z",
                "content": {
                    "sections": {"section-1": "正文内容"},
                    "section_order": ["section-1"],
                    "citations": [
                        {
                            "chunk_id": "chunk-1",
                            "document_id": "doc-1",
                            "document_name": "团队手册.md",
                            "scope": "workspace",
                            "score": 0.93,
                            "page_number": 3,
                            "heading_path": ["发布策略"],
                        }
                    ],
                },
            }
        },
    }

    payload = build_workflow_export_payload(
        {"outline": {"sections": [{"id": "section-1", "title": "章节一"}]}},
        trace,
    )
    markdown = build_markdown(payload)

    assert payload.citations[0]["document_name"] == "团队手册.md"
    assert "## 参考来源" in markdown
    assert "团队手册.md" in markdown
    assert "workspace" in markdown


def test_export_payload_deduplicates_citations_from_graph_state():
    citation = {
        "chunk_id": "chunk-1",
        "document_id": "doc-1",
        "document_name": "个人知识库资料",
        "scope": "personal",
        "score": 0.8,
    }

    payload = build_workflow_export_payload(
        {
            "final_content": {"section-1": "正文内容"},
            "citations": [citation, citation],
        },
        None,
    )

    assert len(payload.citations) == 1
    assert payload.citations[0]["chunk_id"] == citation["chunk_id"]
    assert payload.citations[0]["document_name"] == citation["document_name"]
    assert payload.citations[0]["scope"] == citation["scope"]
