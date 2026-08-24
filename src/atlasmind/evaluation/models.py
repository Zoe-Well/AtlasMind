"""Versioned evaluation datasets, cases, runs, and immutable results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from atlasmind.domain.common import new_id, utc_now


class DatasetStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    RETIRED = "RETIRED"


class EvaluationRunState(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class EvaluationDataset:
    name: str
    version: str
    split: str
    knowledge_snapshot_digest: str
    status: DatasetStatus = DatasetStatus.DRAFT
    id: str | None = None

    def __post_init__(self) -> None:
        if self.id is None:
            object.__setattr__(self, "id", self.name)
        if self.split not in {"TUNING", "HIDDEN_REGRESSION"}:
            raise ValueError("evaluation split is invalid")
        if not self.knowledge_snapshot_digest.startswith("sha256:"):
            raise ValueError("knowledge snapshot digest is required")


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    dataset_id: str
    ordinal: int
    question: str
    allowed_scope_ids: frozenset[str]
    expected_behavior: str
    expected_evidence: tuple[str, ...] = ()
    forbidden_evidence: tuple[str, ...] = ()
    answer_points: tuple[str, ...] = ()
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        if self.ordinal < 1 or not self.question.strip() or not self.allowed_scope_ids:
            raise ValueError("evaluation case identity, question, and scopes are required")
        if self.expected_behavior not in {
            "ANSWER",
            "INSUFFICIENT",
            "CONFLICT",
            "DENY",
            "APPROVAL",
        }:
            raise ValueError("evaluation expected behavior is invalid")
        if self.expected_behavior == "DENY" and not self.forbidden_evidence:
            raise ValueError("authorization case requires forbidden evidence")


@dataclass(frozen=True, slots=True)
class EvaluationRun:
    dataset_id: str
    dataset_version: str
    requested_by: str
    correlation_id: str
    manifest_digest: str | None = None
    id: str = field(default_factory=new_id)
    state: EvaluationRunState = EvaluationRunState.QUEUED
    created_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None
    report_ref: str | None = None


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    case_id: str
    metrics: dict[str, float]
    safety_failures: tuple[str, ...] = ()
    failure_sample_ref: str | None = None

    def __post_init__(self) -> None:
        if any(not 0 <= score <= 1 for score in self.metrics.values()):
            raise ValueError("evaluation metric scores must be between zero and one")
