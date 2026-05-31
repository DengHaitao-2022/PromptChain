import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.outline import OutlineSection


def _load_module(name: str, relative_path: str):
    module_path = Path(__file__).resolve().parents[1] / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _evidence_state():
    return {
        "evidence_pack": {
            "chunks": [
                {
                    "document_name": "团队手册.md",
                    "scope": "workspace",
                    "score": 0.91,
                    "heading_path": ["政策"],
                    "content": "团队权威发布政策。",
                },
                {
                    "document_name": "个人笔记.md",
                    "scope": "personal",
                    "score": 0.89,
                    "heading_path": ["草稿"],
                    "content": "个人写作风格补充。",
                },
            ],
            "unverified_points": [],
        }
    }


def test_outline_evidence_context_marks_workspace_as_authoritative():
    module = _load_module("_test_outline_generator", "nodes/outline_generator.py")

    context = module._format_evidence_context(_evidence_state())

    assert "工作空间资料是权威事实源" in context
    assert "scope=workspace" in context
    assert "scope=personal" in context


def test_content_evidence_context_marks_personal_as_supplemental():
    module = _load_module("_test_content_generator", "nodes/content_generator.py")
    section = OutlineSection(
        id="section-1",
        title="发布政策",
        summary="说明发布政策",
        target_words=300,
    )

    context = module._format_evidence_context(_evidence_state(), section)

    assert "工作空间资料优先作为事实依据" in context
    assert "个人资料仅作为风格或补充材料" in context
    assert "scope=workspace" in context
    assert "scope=personal" in context


def test_fact_checker_evidence_context_marks_scope_precedence():
    module = _load_module("_test_fact_checker_authority", "nodes/fact_checker.py")

    context = module._format_evidence_context(_evidence_state())

    assert "workspace scope 为权威事实源" in context
    assert "personal scope 仅作补充" in context
    assert "scope=workspace" in context
    assert "scope=personal" in context
