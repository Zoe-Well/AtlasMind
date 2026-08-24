"""Ingestion, metadata, projection, and document lifecycle domain models."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Any

from atlasmind.domain.common import InvalidState, new_id, utc_now


class DocumentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    DELETED = "DELETED"


class VersionLifecycle(StrEnum):
    UPLOADED = "UPLOADED"
    VALIDATING = "VALIDATING"
    PARSING = "PARSING"
    CHUNKING = "CHUNKING"
    METADATA_REVIEW = "METADATA_REVIEW"
    LEXICAL_INDEXING = "LEXICAL_INDEXING"
    VECTOR_INDEXING = "VECTOR_INDEXING"
    SEARCHABLE = "SEARCHABLE"
    SUPERSEDED = "SUPERSEDED"
    REVOKED = "REVOKED"
    FAILED = "FAILED"


class MetadataOrigin(StrEnum):
    USER = "USER"
    FILE = "FILE"
    BUSINESS = "BUSINESS"
    RULE = "RULE"
    MODEL = "MODEL"


class MetadataReviewStatus(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class ProjectionKind(StrEnum):
    LEXICAL = "LEXICAL"
    VECTOR = "VECTOR"
    GRAPH = "GRAPH"


class ProjectionState(StrEnum):
    PENDING = "PENDING"
    BUILDING = "BUILDING"
    READY = "READY"
    FAILED = "FAILED"
    RETIRED = "RETIRED"


class IngestionState(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_METADATA_REVIEW = "WAITING_METADATA_REVIEW"
    SEARCHABLE = "SEARCHABLE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class IngestionStage(StrEnum):
    VALIDATING = "VALIDATING"
    PARSING = "PARSING"
    CHUNKING = "CHUNKING"
    METADATA = "METADATA"
    LEXICAL_INDEX = "LEXICAL_INDEX"
    VECTOR_INDEX = "VECTOR_INDEX"
    GRAPH_INDEX = "GRAPH_INDEX"
    ACTIVATING = "ACTIVATING"


@dataclass(frozen=True, slots=True)
class ManagedDocument:
    title: str
    source_key: str
    owner_principal_id: str
    scope_ids: frozenset[str]
    id: str = field(default_factory=new_id)
    status: DocumentStatus = DocumentStatus.ACTIVE
    active_version_id: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.title.strip() or not self.source_key.strip() or not self.scope_ids:
            raise ValueError("document title, source key, and scopes are required")

    def revoke(self) -> ManagedDocument:
        return replace(
            self,
            status=DocumentStatus.REVOKED,
            active_version_id=None,
            updated_at=utc_now(),
        )


@dataclass(frozen=True, slots=True)
class ManagedDocumentVersion:
    document_id: str
    content_digest: str
    object_key: str
    media_type: str
    size_bytes: int
    scope_ids: frozenset[str]
    generation: int
    created_by: str
    version_label: str
    id: str = field(default_factory=new_id)
    metadata_schema_version: int = 1
    lifecycle: VersionLifecycle = VersionLifecycle.UPLOADED
    supersedes_version_id: str | None = None
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.content_digest.startswith("sha256:"):
            raise ValueError("version requires a sha256 content digest")
        if self.size_bytes <= 0 or self.generation <= 0 or not self.scope_ids:
            raise ValueError("version requires positive size/generation and scopes")


@dataclass(frozen=True, slots=True)
class DocumentMetadata:
    document_version_id: str
    key: str
    value: Any
    origin: MetadataOrigin
    review_status: MetadataReviewStatus
    confidence: float | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.key or self.value is None:
            raise ValueError("metadata key and value are required")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("metadata confidence must be between zero and one")


@dataclass(frozen=True, slots=True)
class Projection:
    document_version_id: str
    kind: ProjectionKind
    generation: int
    adapter_version: str
    id: str = field(default_factory=new_id)
    state: ProjectionState = ProjectionState.PENDING
    record_count: int = 0
    error_code: str | None = None
    updated_at: datetime = field(default_factory=utc_now)

    def ready(self, record_count: int) -> Projection:
        if record_count < 0:
            raise ValueError("projection record count cannot be negative")
        return replace(
            self,
            state=ProjectionState.READY,
            record_count=record_count,
            error_code=None,
            updated_at=utc_now(),
        )


@dataclass(frozen=True, slots=True)
class IngestionJob:
    document_version_id: str
    idempotency_key: str
    id: str = field(default_factory=new_id)
    state: IngestionState = IngestionState.QUEUED
    current_stage: IngestionStage = IngestionStage.VALIDATING
    attempt: int = 0
    max_attempts: int = 5
    lease_owner: str | None = None
    lease_until: datetime | None = None
    failure_code: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def start(self) -> IngestionJob:
        if self.state not in {IngestionState.QUEUED, IngestionState.WAITING_METADATA_REVIEW}:
            raise InvalidState(details={"reason": "INGESTION_JOB_NOT_RUNNABLE"})
        return replace(
            self,
            state=IngestionState.RUNNING,
            attempt=self.attempt + 1,
            started_at=self.started_at or utc_now(),
            failure_code=None,
        )

    def fail(self, code: str) -> IngestionJob:
        return replace(
            self,
            state=IngestionState.FAILED,
            failure_code=code,
            finished_at=utc_now(),
        )

    def retry(self) -> IngestionJob:
        if self.state is not IngestionState.FAILED or self.attempt >= self.max_attempts:
            raise InvalidState(details={"reason": "INGESTION_JOB_NOT_RETRYABLE"})
        return replace(
            self,
            state=IngestionState.QUEUED,
            current_stage=IngestionStage.VALIDATING,
            failure_code=None,
            finished_at=None,
        )
