"""Reproducible evaluation worker invalidating incomplete version manifests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from atlasmind.domain.common import utc_now
from atlasmind.evaluation.models import (
    EvaluationCase,
    EvaluationResult,
    EvaluationRun,
    EvaluationRunState,
)
from atlasmind.evaluation.quality_gate import QualityGate
from atlasmind.evaluation.snapshots import EvaluationManifest

CaseRunner = Callable[[EvaluationCase], EvaluationResult]


class EvaluationWorker:
    def __init__(self, runner: CaseRunner, gate: QualityGate | None = None) -> None:
        self._runner = runner
        self._gate = gate or QualityGate()

    def execute(
        self,
        run: EvaluationRun,
        cases: tuple[EvaluationCase, ...],
        manifest: EvaluationManifest,
        *,
        baseline: dict[str, float] | None = None,
    ) -> tuple[EvaluationRun, tuple[EvaluationResult, ...]]:
        if not cases or run.dataset_id not in manifest.dataset:
            return (
                replace(run, state=EvaluationRunState.INVALID, finished_at=utc_now()),
                (),
            )
        results = tuple(self._runner(case) for case in cases)
        decision = self._gate.evaluate(results, baseline=baseline)
        completed = replace(
            run,
            manifest_digest=manifest.digest,
            state=EvaluationRunState.PASSED if decision.passed else EvaluationRunState.FAILED,
            finished_at=utc_now(),
            report_ref=f"evaluation-report:{run.id}",
        )
        return completed, results
