"""Evaluation manifests are reproducible and safety failures are release blockers."""

from __future__ import annotations

from atlasmind.evaluation.models import EvaluationCase, EvaluationResult
from atlasmind.evaluation.quality_gate import QualityGate, QualityThresholds
from atlasmind.evaluation.snapshots import EvaluationManifest


def test_fixed_versions_and_seed_produce_identical_manifest_digest() -> None:
    values = {
        "code_version": "commit-123",
        "dataset": "golden-basic@1",
        "knowledge_snapshot": "sha256:knowledge",
        "index_generation": "8",
        "retrieval_policy": "hybrid@1",
        "model": "deterministic-test@1",
        "prompt": "answer@2",
        "evaluator": "deterministic@1",
        "seed": 42,
    }

    first = EvaluationManifest(**values)
    second = EvaluationManifest(**values)

    assert first.digest == second.digest
    assert first.as_dict() == second.as_dict()


def test_safety_failure_cannot_be_offset_by_high_average_quality() -> None:
    gate = QualityGate(QualityThresholds(answer_success=0.9, multi_source_success=0.85))
    cases = (
        EvaluationResult("answer-1", {"answer_success": 1.0}, safety_failures=()),
        EvaluationResult(
            "authorization-1",
            {"answer_success": 1.0, "multi_source_success": 1.0},
            safety_failures=("FORBIDDEN_EVIDENCE_DISCLOSED",),
        ),
    )

    decision = gate.evaluate(cases, baseline={"answer_success": 0.95})

    assert decision.passed is False
    assert decision.blocking_reasons == ("FORBIDDEN_EVIDENCE_DISCLOSED",)


def test_evaluation_case_requires_expected_security_behavior() -> None:
    case = EvaluationCase(
        dataset_id="authorization@1",
        ordinal=1,
        question="restricted question",
        allowed_scope_ids=frozenset({"scope-public"}),
        expected_behavior="DENY",
        forbidden_evidence=("secret-marker",),
    )
    assert case.expected_behavior == "DENY"
