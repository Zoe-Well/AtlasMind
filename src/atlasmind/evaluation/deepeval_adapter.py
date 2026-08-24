"""Optional DeepEval semantic judge port with deterministic injected adapter."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SemanticEvaluation:
    score: float
    reason_code: str
    evaluator_version: str


SemanticJudge = Callable[[str, str, tuple[str, ...]], tuple[float, str]]


class DeepEvalAdapter:
    def __init__(self, judge: SemanticJudge, *, version: str) -> None:
        self._judge = judge
        self.version = version

    def evaluate(
        self,
        question: str,
        answer: str,
        expected_points: tuple[str, ...],
    ) -> SemanticEvaluation:
        score, reason = self._judge(question, answer, expected_points)
        if not 0 <= score <= 1:
            raise ValueError("semantic evaluator score is invalid")
        return SemanticEvaluation(score, reason, self.version)
