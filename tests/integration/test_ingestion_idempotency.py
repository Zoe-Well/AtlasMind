"""US2 idempotency, generation switching, retry, and revocation races."""

from __future__ import annotations

import asyncio

import pytest

from atlasmind.application.ingest_document import InMemoryIngestionService, UploadDocument
from atlasmind.domain.common import InvalidState
from atlasmind.ingestion.models import DocumentStatus, IngestionState, VersionLifecycle


def command(
    *,
    content: bytes,
    key: str,
    source_key: str = "policy/refund",
    media_type: str = "text/plain",
) -> UploadDocument:
    return UploadDocument(
        title="Refund policy",
        source_key=source_key,
        file_name="refund.txt",
        media_type=media_type,
        content=content,
        scope_ids=frozenset({"scope-public"}),
        metadata={"businessOwner": "Finance", "classification": "INTERNAL"},
        created_by="knowledge-admin",
        idempotency_key=key,
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_duplicate_and_concurrent_idempotency_key_returns_one_job() -> None:
    service = InMemoryIngestionService()
    upload = command(content=b"version one", key="same-request")

    first, second = await asyncio.gather(service.upload(upload), service.upload(upload))

    assert first.document.id == second.document.id
    assert first.version.id == second.version.id
    assert first.job.id == second.job.id
    assert len(service.jobs) == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_new_generation_switches_atomically_and_retires_old_projection() -> None:
    service = InMemoryIngestionService()
    first = await service.upload(command(content=b"version one", key="v1"))
    await service.process(first.job.id)

    second = await service.add_version(
        first.document.id,
        file_name="refund-v2.txt",
        media_type="text/plain",
        content=b"version two",
        metadata={},
        created_by="knowledge-admin",
        idempotency_key="v2",
        version_label="v2",
    )
    assert service.get_document(first.document.id).active_version_id == first.version.id

    await service.process(second.job.id)

    assert service.get_document(first.document.id).active_version_id == second.version.id
    assert service.get_version(first.version.id).lifecycle is VersionLifecycle.SUPERSEDED
    assert all(item.state.value == "RETIRED" for item in service.projections_for(first.version.id))


@pytest.mark.asyncio
@pytest.mark.integration
async def test_revocation_is_immediate_and_stale_job_cannot_reactivate_document() -> None:
    service = InMemoryIngestionService()
    accepted = await service.upload(command(content=b"version one", key="revoke"))
    service.revoke_document(accepted.document.id, actor_id="knowledge-admin")

    with pytest.raises(InvalidState):
        await service.process(accepted.job.id)

    assert service.get_document(accepted.document.id).status is DocumentStatus.REVOKED
    assert service.get_document(accepted.document.id).active_version_id is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_failed_parse_retry_reuses_job_and_increments_attempt() -> None:
    service = InMemoryIngestionService()
    accepted = await service.upload(
        command(
            content=b"<html><script>only code</script></html>",
            key="bad-html",
            media_type="text/html",
        )
    )

    failed = await service.process(accepted.job.id)
    assert failed.state is IngestionState.FAILED
    assert failed.attempt == 1

    retried = service.retry_job(failed.id, idempotency_key="retry-1")
    assert retried.id == failed.id
    assert retried.state is IngestionState.QUEUED
    assert len(service.jobs) == 1
