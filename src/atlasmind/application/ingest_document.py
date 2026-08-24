"""Transactional ingestion use case and deterministic in-memory adapter."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from atlasmind.application.document_versions import (
    ensure_unique_content,
    inherited_metadata_keys,
    next_generation,
)
from atlasmind.domain.common import InvalidState, ResourceNotAvailable, utc_now
from atlasmind.ingestion.activation import activate_version
from atlasmind.ingestion.chunking import DeterministicChunker, IngestedChunk
from atlasmind.ingestion.file_validation import FileValidator, ValidatedFile
from atlasmind.ingestion.metadata import build_metadata, requires_review, review_metadata
from atlasmind.ingestion.models import (
    DocumentMetadata,
    DocumentStatus,
    IngestionJob,
    IngestionStage,
    IngestionState,
    ManagedDocument,
    ManagedDocumentVersion,
    Projection,
    ProjectionState,
    VersionLifecycle,
)
from atlasmind.ingestion.parsers import ParserRegistry, ParsingFailed
from atlasmind.ingestion.projections import build_required_projections
from atlasmind.ingestion.reconciliation import ReconciliationReport, reconcile


@dataclass(frozen=True, slots=True)
class UploadDocument:
    title: str
    source_key: str
    file_name: str
    media_type: str
    content: bytes
    scope_ids: frozenset[str]
    metadata: Mapping[str, Any]
    created_by: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class IngestionAccepted:
    document: ManagedDocument
    version: ManagedDocumentVersion
    job: IngestionJob


@dataclass(frozen=True, slots=True)
class ObjectWriteIntent:
    object_key: str
    content_digest: str
    size_bytes: int
    state: str = "COMMITTED"


class InMemoryIngestionService:
    """Executable adapter used by contracts; production storage can implement the same boundary."""

    def __init__(self, *, max_file_bytes: int = 50 * 1024 * 1024) -> None:
        self.validator = FileValidator(max_file_bytes=max_file_bytes)
        self.parsers = ParserRegistry()
        self.chunker = DeterministicChunker()
        self.documents: dict[str, ManagedDocument] = {}
        self.versions: dict[str, ManagedDocumentVersion] = {}
        self.jobs: dict[str, IngestionJob] = {}
        self.projections: dict[str, Projection] = {}
        self.metadata: dict[str, dict[str, DocumentMetadata]] = {}
        self.chunks: dict[str, tuple[IngestedChunk, ...]] = {}
        self.object_write_intents: list[ObjectWriteIntent] = []
        self.outbox_events: list[dict[str, Any]] = []
        self._objects: dict[str, bytes] = {}
        self._source_documents: dict[str, str] = {}
        self._idempotency: dict[str, IngestionAccepted] = {}
        self._retry_idempotency: dict[tuple[str, str], IngestionJob] = {}
        self._lock = asyncio.Lock()

    async def upload(self, command: UploadDocument) -> IngestionAccepted:
        validated = self.validator.validate(command.file_name, command.media_type, command.content)
        async with self._lock:
            previous = self._idempotency.get(command.idempotency_key)
            if previous is not None:
                if previous.version.content_digest != validated.content_digest:
                    raise InvalidState(details={"reason": "IDEMPOTENCY_KEY_REUSED"})
                return previous
            if command.source_key in self._source_documents:
                ensure_unique_content(
                    self.versions.values(),
                    source_key_document_ids=frozenset({self._source_documents[command.source_key]}),
                    content_digest=validated.content_digest,
                )
                raise InvalidState(details={"reason": "SOURCE_KEY_EXISTS"})
            ensure_unique_content(
                self.versions.values(),
                source_key_document_ids=frozenset(self.documents),
                content_digest=validated.content_digest,
            )
            document = ManagedDocument(
                title=command.title,
                source_key=command.source_key,
                owner_principal_id=command.created_by,
                scope_ids=command.scope_ids,
            )
            version = self._new_version(
                document=document,
                validated=validated,
                command=command,
                version_label="v1",
                supersedes=None,
            )
            accepted = self._commit_upload(document, version, command, validated)
            self._source_documents[document.source_key] = document.id
            return accepted

    async def add_version(
        self,
        document_id: str,
        *,
        file_name: str,
        media_type: str,
        content: bytes,
        metadata: Mapping[str, Any],
        created_by: str,
        idempotency_key: str,
        version_label: str | None,
    ) -> IngestionAccepted:
        validated = self.validator.validate(file_name, media_type, content)
        async with self._lock:
            previous = self._idempotency.get(idempotency_key)
            if previous is not None:
                if previous.version.content_digest != validated.content_digest:
                    raise InvalidState(details={"reason": "IDEMPOTENCY_KEY_REUSED"})
                return previous
            document = self.get_document(document_id)
            if document.status is not DocumentStatus.ACTIVE:
                raise InvalidState(details={"reason": "DOCUMENT_NOT_ACTIVE"})
            ensure_unique_content(
                self.versions.values(),
                source_key_document_ids=frozenset({document_id}),
                content_digest=validated.content_digest,
            )
            inherited: dict[str, Any] = {}
            if document.active_version_id:
                current_metadata = self.metadata.get(document.active_version_id, {})
                inherited = {
                    key: item.value
                    for key, item in current_metadata.items()
                    if key in inherited_metadata_keys()
                }
            merged = {**inherited, **metadata}
            command = UploadDocument(
                title=document.title,
                source_key=document.source_key,
                file_name=file_name,
                media_type=media_type,
                content=content,
                scope_ids=document.scope_ids,
                metadata=merged,
                created_by=created_by,
                idempotency_key=idempotency_key,
            )
            generation = next_generation(self.versions.values(), document_id)
            version = self._new_version(
                document=document,
                validated=validated,
                command=command,
                version_label=version_label or f"v{generation}",
                supersedes=document.active_version_id,
                generation=generation,
            )
            return self._commit_upload(document, version, command, validated)

    def _new_version(
        self,
        *,
        document: ManagedDocument,
        validated: ValidatedFile,
        command: UploadDocument,
        version_label: str,
        supersedes: str | None,
        generation: int = 1,
    ) -> ManagedDocumentVersion:
        return ManagedDocumentVersion(
            document_id=document.id,
            content_digest=validated.content_digest,
            object_key=validated.object_key,
            media_type=validated.media_type,
            size_bytes=validated.size_bytes,
            scope_ids=command.scope_ids,
            generation=generation,
            created_by=command.created_by,
            version_label=version_label,
            supersedes_version_id=supersedes,
        )

    def _commit_upload(
        self,
        document: ManagedDocument,
        version: ManagedDocumentVersion,
        command: UploadDocument,
        validated: ValidatedFile,
    ) -> IngestionAccepted:
        job = IngestionJob(
            document_version_id=version.id,
            idempotency_key=command.idempotency_key,
        )
        self.documents[document.id] = document
        self.versions[version.id] = version
        self.jobs[job.id] = job
        self._objects[version.object_key] = command.content
        self.metadata[version.id] = build_metadata(
            version.id,
            user=command.metadata,
            file_facts={"fileName": validated.file_name, "mediaType": validated.media_type},
        )
        self.object_write_intents.append(
            ObjectWriteIntent(version.object_key, version.content_digest, version.size_bytes)
        )
        self.outbox_events.append(
            {
                "eventType": "knowledge.document-version.created.v1",
                "documentVersionId": version.id,
                "generation": version.generation,
            }
        )
        accepted = IngestionAccepted(document, version, job)
        self._idempotency[command.idempotency_key] = accepted
        return accepted

    async def process(self, job_id: str) -> IngestionJob:
        job = self.get_job(job_id)
        version = self.get_version(job.document_version_id)
        document = self.get_document(version.document_id)
        if document.status is not DocumentStatus.ACTIVE:
            raise InvalidState(details={"reason": "DOCUMENT_NOT_ACTIVE"})
        if job.state is IngestionState.WAITING_METADATA_REVIEW and requires_review(
            self.metadata[version.id]
        ):
            return job
        job = job.start()
        self.jobs[job.id] = job
        try:
            job = replace(job, current_stage=IngestionStage.VALIDATING)
            version = replace(version, lifecycle=VersionLifecycle.VALIDATING)
            self.versions[version.id] = version

            job = replace(job, current_stage=IngestionStage.PARSING)
            version = replace(version, lifecycle=VersionLifecycle.PARSING)
            parsed = self.parsers.parse(version.media_type, self._objects[version.object_key])

            job = replace(job, current_stage=IngestionStage.CHUNKING)
            version = replace(version, lifecycle=VersionLifecycle.CHUNKING)
            chunks = self.chunker.chunk(
                parsed,
                document_version_id=version.id,
                scope_ids=version.scope_ids,
                generation=version.generation,
            )
            self.chunks[version.id] = chunks

            job = replace(job, current_stage=IngestionStage.METADATA)
            if requires_review(self.metadata[version.id]):
                version = replace(version, lifecycle=VersionLifecycle.METADATA_REVIEW)
                job = replace(job, state=IngestionState.WAITING_METADATA_REVIEW)
                self.versions[version.id] = version
                self.jobs[job.id] = job
                return job

            existing = self.projections_for(version.id)
            built = build_required_projections(
                document_version_id=version.id,
                generation=version.generation,
                chunks=chunks,
                existing=existing,
            )
            for item in built:
                self.projections[item.id] = item
            job = replace(job, current_stage=IngestionStage.ACTIVATING)
            document, version = activate_version(
                document,
                version,
                projections=built,
                metadata=self.metadata[version.id],
            )
            if version.supersedes_version_id:
                previous = self.versions[version.supersedes_version_id]
                self.versions[previous.id] = replace(
                    previous, lifecycle=VersionLifecycle.SUPERSEDED
                )
                for projection in self.projections_for(previous.id):
                    self.projections[projection.id] = replace(
                        projection, state=ProjectionState.RETIRED
                    )
            self.documents[document.id] = document
            self.versions[version.id] = version
            job = replace(
                job,
                state=IngestionState.SEARCHABLE,
                finished_at=utc_now(),
                failure_code=None,
            )
            self.jobs[job.id] = job
            self.outbox_events.append(
                {
                    "eventType": "knowledge.document-version.activated.v1",
                    "documentVersionId": version.id,
                    "generation": version.generation,
                }
            )
            return job
        except (ParsingFailed, ValueError) as exc:
            code = getattr(exc, "reason", "INGESTION_FAILED")
            failed_job = job.fail(str(code))
            self.jobs[job.id] = failed_job
            self.versions[version.id] = replace(version, lifecycle=VersionLifecycle.FAILED)
            return failed_job

    def review_metadata(
        self,
        version_id: str,
        *,
        corrections: Mapping[str, Any],
        reviewer_id: str,
        approved: bool,
    ) -> dict[str, DocumentMetadata]:
        self.get_version(version_id)
        updated = review_metadata(
            self.metadata.get(version_id, {}),
            version_id=version_id,
            corrections=corrections,
            reviewer_id=reviewer_id,
            approved=approved,
        )
        self.metadata[version_id] = updated
        if not approved:
            for job in self.jobs.values():
                if job.document_version_id == version_id:
                    self.jobs[job.id] = job.fail("METADATA_REJECTED")
        return updated

    def revoke_document(self, document_id: str, *, actor_id: str) -> ManagedDocument:
        document = self.get_document(document_id)
        revoked = document.revoke()
        self.documents[document_id] = revoked
        for version in tuple(self.versions.values()):
            if version.document_id == document_id:
                self.versions[version.id] = replace(version, lifecycle=VersionLifecycle.REVOKED)
                for projection in self.projections_for(version.id):
                    self.projections[projection.id] = replace(
                        projection, state=ProjectionState.RETIRED
                    )
        self.outbox_events.append(
            {
                "eventType": "knowledge.document-version.revoked.v1",
                "documentId": document_id,
                "actorId": actor_id,
            }
        )
        return revoked

    def retry_job(self, job_id: str, *, idempotency_key: str) -> IngestionJob:
        cached = self._retry_idempotency.get((job_id, idempotency_key))
        if cached is not None:
            return cached
        job = self.get_job(job_id).retry()
        version = self.get_version(job.document_version_id)
        self.versions[version.id] = replace(version, lifecycle=VersionLifecycle.UPLOADED)
        self.jobs[job.id] = job
        self._retry_idempotency[(job_id, idempotency_key)] = job
        return job

    def get_document(self, document_id: str) -> ManagedDocument:
        try:
            return self.documents[document_id]
        except KeyError as exc:
            raise ResourceNotAvailable() from exc

    def get_version(self, version_id: str) -> ManagedDocumentVersion:
        try:
            return self.versions[version_id]
        except KeyError as exc:
            raise ResourceNotAvailable() from exc

    def get_job(self, job_id: str) -> IngestionJob:
        try:
            return self.jobs[job_id]
        except KeyError as exc:
            raise ResourceNotAvailable() from exc

    def projections_for(self, version_id: str) -> tuple[Projection, ...]:
        return tuple(
            item for item in self.projections.values() if item.document_version_id == version_id
        )

    def chunks_for(self, version_id: str) -> tuple[IngestedChunk, ...]:
        return self.chunks.get(version_id, ())

    def reconcile(self) -> ReconciliationReport:
        return reconcile(
            now=utc_now(),
            documents=self.documents,
            versions=self.versions,
            jobs=self.jobs,
            projections=self.projections,
        )
