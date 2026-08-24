"""Release decisions enforce spec thresholds and security zero tolerance."""

from __future__ import annotations

from atlasmind.evaluation.citation_accuracy import CitationCheck, citation_accuracy
from atlasmind.evaluation.deepeval_adapter import DeepEvalAdapter
from atlasmind.evaluation.models import EvaluationResult
from atlasmind.evaluation.quality_gate import QualityGate


def test_release_passes_when_all_spec_metrics_and_semantic_checks_pass() -> None:
    semantic = DeepEvalAdapter(
        lambda _question, answer, points: (
            1.0 if all(point in answer for point in points) else 0.0,
            "DETERMINISTIC",
        ),
        version="test-1",
    ).evaluate("refund window", "Refund window is 30 days", ("30 days",))
    citations = citation_accuracy(
        (
            CitationCheck(
                "Refund window is 30 days",
                "paragraph=1",
                "Refund window is 30 days",
            ),
        )
    )
    result = EvaluationResult(
        "release-suite",
        {
            "answer_success": semantic.score,
            "multi_source_success": 0.90,
            "graph_path_consistency": 0.90,
            "citation_accuracy": citations,
            "degradation_accuracy": 1.0,
            "observability_correlation": 1.0,
            "overall_quality": 0.90,
        },
    )

    decision = QualityGate().evaluate((result,), baseline={"overall_quality": 0.90})

    assert decision.passed is True
    assert decision.blocking_reasons == ()


def test_graph_hallucination_or_permission_leak_blocks_release() -> None:
    result = EvaluationResult(
        "unsafe-suite",
        {"answer_success": 1.0, "overall_quality": 1.0},
        safety_failures=("GRAPH_RELATION_HALLUCINATED", "FORBIDDEN_EVIDENCE_DISCLOSED"),
    )

    decision = QualityGate().evaluate((result,))

    assert decision.passed is False
    assert set(decision.blocking_reasons) == {
        "GRAPH_RELATION_HALLUCINATED",
        "FORBIDDEN_EVIDENCE_DISCLOSED",
    }
