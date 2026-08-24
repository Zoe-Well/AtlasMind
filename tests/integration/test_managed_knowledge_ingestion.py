"""End-to-end acceptance coverage for the managed knowledge lifecycle."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from atlasmind.application.ingest_document import InMemoryIngestionService, UploadDocument
from atlasmind.domain.common import utc_now
from atlasmind.ingestion.models import (
    DocumentStatus,
    IngestionState,
    Projection,
    ProjectionKind,
    ProjectionState,
    VersionLifecycle,
)


def upload_command(
    *,
    source_key: str,
    content: bytes,
    idempotency_key: str,
) -> UploadDocument:
    return UploadDocument(
        title="Managed refund policy",
        source_key=source_key,
        file_name="refund-policy.txt",
        media_type="text/plain",
        content=content,
        scope_ids=frozenset({"scope-public"}),
        metadata={"businessOwner": "Finance", "classification": "INTERNAL"},
        created_by="knowledge-admin",
        idempotency_key=idempotency_key,
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_import_version_switch_and_revocation_are_managed_end_to_end() -> None:
    service = InMemoryIngestionService()
    first = await service.upload(
        upload_command(
            source_key="policy/managed-refund",
            content=b"Refunds are accepted within 30 days.",
            idempotency_key="managed-refund-v1",
        )
    )

    first_job = await service.process(first.job.id)

    assert first_job.state is IngestionState.SEARCHABLE
    assert first_job.finished_at is not None
    assert first_job.finished_at - first_job.created_at <= timedelta(minutes=10)
    assert service.get_document(first.document.id).active_version_id == first.version.id
    assert service.chunks_for(first.version.id)
    assert all(
        projection.state is ProjectionState.READY
        for projection in service.projections_for(first.version.id)
    )

    second = await service.add_version(
        first.document.id,
        file_name="refund-policy-v2.txt",
        media_type="text/plain",
        content=b"Refunds are accepted within 45 days.",
        metadata={},
        created_by="knowledge-admin",
        idempotency_key="managed-refund-v2",
        version_label="v2",
    )
    await service.process(second.job.id)

    assert service.get_document(first.document.id).active_version_id == second.version.id
    assert service.get_version(first.version.id).lifecycle is VersionLifecycle.SUPERSEDED
    assert all(
        projection.state is ProjectionState.RETIRED
        for projection in service.projections_for(first.version.id)
    )

    revoked = service.revoke_document(first.document.id, actor_id="knowledge-admin")

    assert revoked.status is DocumentStatus.REVOKED
    assert revoked.active_version_id is None
    assert all(
        projection.state is ProjectionState.RETIRED
        for version in (first.version, second.version)
        for projection in service.projections_for(version.id)
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_reconciliation_recovers_expired_work_and_removes_orphans() -> None:
    service = InMemoryIngestionService()
    accepted = await service.upload(
        upload_command(
            source_key="policy/reconciliation",
            content=b"A queued policy awaiting ingestion.",
            idempotency_key="reconciliation-v1",
        )
    )
    expired = replace(
        accepted.job,
        state=IngestionState.RUNNING,
        lease_owner="stopped-worker",
        lease_until=utc_now() - timedelta(seconds=1),
    )
    service.jobs[expired.id] = expired
    orphan = Projection(
        document_version_id="00000000-0000-0000-0000-000000000000",
        generation=1,
        kind=ProjectionKind.VECTOR,
        adapter_version="test",
    )
    service.projections[orphan.id] = orphan

    report = service.reconcile()

    assert report.recovered_job_ids == (expired.id,)
    assert report.orphan_projection_ids == (orphan.id,)
    assert service.get_job(expired.id).state is IngestionState.QUEUED
    assert orphan.id not in service.projections
