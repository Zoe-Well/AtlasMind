"""Immutable knowledge, evidence, citation, and AgentRun domain models."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum

from atlasmind.domain.common import InvalidState, new_id, utc_now


class EvidenceValidity(StrEnum):
    VALID = "VALID"
    CONFLICTED = "CONFLICTED"
    STALE = "STALE"
    REJECTED = "REJECTED"


class RunState(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    id: str
    title: str
    active_version_id: str | None = None
    active: bool = True


@dataclass(frozen=True, slots=True)
class DocumentVersion:
    id: str
    document_id: str
    content_digest: str
    scope_ids: frozenset[str]
    searchable: bool
    generation: int
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if (
            not self.scope_ids
            or self.generation < 1
            or not self.content_digest.startswith("sha256:")
        ):
            raise ValueError("document version requires scopes, generation, and sha256 digest")


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    id: str
    document_version_id: str
    ordinal: int
    content: str
    locator: str
    scope_ids: frozenset[str]
    generation: int
    active: bool = True

    def __post_init__(self) -> None:
        if self.ordinal < 0 or not self.content.strip() or not self.locator.strip():
            raise ValueError("chunk content and locator are required")
        if not self.scope_ids or self.generation < 1:
            raise ValueError("chunk requires scopes and a positive generation")


@dataclass(frozen=True, slots=True)
class SourceReference:
    type: str
    canonical_id: str
    version: str
    locator: str

    def __post_init__(self) -> None:
        if not all((self.type, self.canonical_id, self.version, self.locator)):
            raise ValueError("source reference is incomplete")


@dataclass(frozen=True, slots=True)
class Evidence:
    id: str
    source: SourceReference
    scope_ids: frozenset[str]
    content: str
    digest: str
    validity: EvidenceValidity
    authz_revision: int
    verified_at: datetime

    def __post_init__(self) -> None:
        if not self.scope_ids or not self.content or not self.digest.startswith("sha256:"):
            raise ValueError("evidence requires authorized content and digest")


@dataclass(frozen=True, slots=True)
class Citation:
    id: str
    claim: str
    evidence_id: str
    source: SourceReference
    support: str

    def validate_against(self, evidence: Evidence) -> None:
        if self.evidence_id != evidence.id or self.source != evidence.source:
            raise ValueError("citation is not bound to its evidence and source locator")
        if self.support == "SUPPORTED" and evidence.validity is not EvidenceValidity.VALID:
            raise ValueError("invalid evidence cannot fully support a claim")


@dataclass(frozen=True, slots=True)
class AgentRun:
    principal_id: str
    query: str
    correlation_id: str
    scope_ids: frozenset[str]
    authz_revision: int
    id: str = field(default_factory=new_id)
    state: RunState = RunState.QUEUED
    created_at: datetime = field(default_factory=utc_now)
    answer: str | None = None
    evidence_status: str | None = None
    citations: tuple[Citation, ...] = ()

    def cancel(self) -> AgentRun:
        if self.state not in {RunState.QUEUED, RunState.RUNNING}:
            raise InvalidState(details={"reason": "RUN_NOT_CANCELLABLE"})
        return replace(self, state=RunState.CANCELLED)
