import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.fact_check import VerificationResult

_FACT_CHECKER_PATH = Path(__file__).resolve().parents[1] / "nodes" / "fact_checker.py"
_FACT_CHECKER_SPEC = importlib.util.spec_from_file_location(
    "_test_fact_checker_module",
    _FACT_CHECKER_PATH,
)
assert _FACT_CHECKER_SPEC is not None
_FACT_CHECKER_MODULE = importlib.util.module_from_spec(_FACT_CHECKER_SPEC)
assert _FACT_CHECKER_SPEC.loader is not None
_FACT_CHECKER_SPEC.loader.exec_module(_FACT_CHECKER_MODULE)
_apply_evidence_status = _FACT_CHECKER_MODULE._apply_evidence_status


def test_verification_result_exposes_evidence_status_for_rag_fact_checking():
    result = VerificationResult(
        claim_id="claim-1",
        is_verified=False,
        confidence=0.2,
        risk_level="high",
        evidence_status="unsupported",
        source="Evidence Artifact",
    )

    dumped = result.model_dump()

    assert dumped["evidence_status"] == "unsupported"


def test_apply_evidence_status_marks_supported_when_evidence_exists():
    result = VerificationResult(
        claim_id="claim-1",
        is_verified=True,
        confidence=0.8,
        risk_level="low",
    )

    _apply_evidence_status(
        result,
        {
            "evidence_pack": {
                "chunks": [{"chunk_id": "chunk-1", "document_name": "policy.md"}],
                "conflicts": [],
                "unverified_points": [],
            }
        },
    )

    assert result.evidence_status == "supported"
    assert result.source == "Evidence Artifact"


def test_apply_evidence_status_marks_unsupported_without_evidence():
    result = VerificationResult(
        claim_id="claim-1",
        is_verified=False,
        confidence=0.2,
        risk_level="medium",
    )

    _apply_evidence_status(
        result,
        {
            "evidence_pack": {
                "chunks": [],
                "conflicts": [],
                "unverified_points": ["缺少产品发布时间资料"],
            }
        },
    )

    assert result.evidence_status == "unsupported"
    assert result.is_verified is False
    assert result.risk_level == "high"


def test_apply_evidence_status_marks_conflicting_when_conflicts_exist():
    result = VerificationResult(
        claim_id="claim-1",
        is_verified=True,
        confidence=0.7,
        risk_level="low",
    )

    _apply_evidence_status(
        result,
        {
            "evidence_pack": {
                "chunks": [{"chunk_id": "left"}, {"chunk_id": "right"}],
                "conflicts": [{"topic": "发布策略", "chunk_ids": ["left", "right"]}],
                "unverified_points": [],
            }
        },
    )

    assert result.evidence_status == "conflicting"
    assert result.is_verified is False
    assert result.risk_level == "high"
