"""Spec thresholds, safety zero tolerance, and baseline regression gate."""

from __future__ import annotations

from dataclasses import dataclass

from atlasmind.evaluation.models import EvaluationResult


@dataclass(frozen=True, slots=True)
class QualityThresholds:
    answer_success: float = 0.90
    multi_source_success: float = 0.85
    graph_path_consistency: float = 0.85
    citation_accuracy: float = 0.95
    degradation_accuracy: float = 0.95
    observability_correlation: float = 0.99
    overall_quality: float = 0.85
    max_relative_regression: float = 0.05


@dataclass(frozen=True, slots=True)
class GateDecision:
    passed: bool
    metrics: dict[str, float]
    blocking_reasons: tuple[str, ...]


class QualityGate:
    def __init__(self, thresholds: QualityThresholds | None = None) -> None:
        self._thresholds = thresholds or QualityThresholds()

    def evaluate(
        self,
        results: tuple[EvaluationResult, ...],
        *,
        baseline: dict[str, float] | None = None,
    ) -> GateDecision:
        metric_names = {name for result in results for name in result.metrics}
        metrics = {
            name: sum(result.metrics[name] for result in results if name in result.metrics)
            / sum(name in result.metrics for result in results)
            for name in sorted(metric_names)
        }
        safety_failures = tuple(
            dict.fromkeys(failure for result in results for failure in result.safety_failures)
        )
        blockers = list(safety_failures)
        for name, score in metrics.items():
            threshold = getattr(self._thresholds, name, None)
            if threshold is not None and score < threshold:
                blockers.append(f"THRESHOLD_FAILED:{name}")
            previous = (baseline or {}).get(name)
            if previous is not None and score < previous - self._thresholds.max_relative_regression:
                blockers.append(f"BASELINE_REGRESSION:{name}")
        return GateDecision(not blockers, metrics, tuple(blockers))
