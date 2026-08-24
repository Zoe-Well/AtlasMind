"""US2 ingestion validation, parsing, metadata, and activation lifecycle."""

from __future__ import annotations

import pytest

from atlasmind.application.ingest_document import InMemoryIngestionService, UploadDocument
from atlasmind.ingestion.file_validation import UploadRejected
from atlasmind.ingestion.models import IngestionState, VersionLifecycle


def command(
    *,
    content: bytes = b"Refund requests are accepted for 30 days.",
    media_type: str = "text/plain",
    source_key: str = "policy/refund",
    idempotency_key: str = "refund-v1",
    metadata: dict[str, str] | None = None,
) -> UploadDocument:
    return UploadDocument(
        title="Refund policy",
        source_key=source_key,
        file_name="refund.txt",
        media_type=media_type,
        content=content,
        scope_ids=frozenset({"scope-public"}),
        metadata=metadata or {"businessOwner": "Finance", "classification": "INTERNAL"},
        created_by="knowledge-admin",
        idempotency_key=idempotency_key,
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_supported_file_becomes_searchable_with_traceable_chunks() -> None:
    service = InMemoryIngestionService()
    accepted = await service.upload(command())

    completed = await service.process(accepted.job.id)

    assert completed.state is IngestionState.SEARCHABLE
    document = service.get_document(accepted.document.id)
    version = service.get_version(accepted.version.id)
    assert document.active_version_id == version.id
    assert version.lifecycle is VersionLifecycle.SEARCHABLE
    assert {projection.kind.value for projection in service.projections_for(version.id)} == {
        "LEXICAL",
        "VECTOR",
    }
    chunks = service.chunks_for(version.id)
    assert chunks and chunks[0].locator == "paragraph=1"
    assert chunks[0].scope_ids == frozenset({"scope-public"})


@pytest.mark.asyncio
@pytest.mark.integration
async def test_empty_encrypted_oversize_and_duplicate_files_are_rejected() -> None:
    service = InMemoryIngestionService(max_file_bytes=64)

    with pytest.raises(UploadRejected, match="EMPTY_FILE"):
        await service.upload(command(content=b"", idempotency_key="empty"))
    with pytest.raises(UploadRejected, match="ENCRYPTED_FILE"):
        await service.upload(
            command(
                content=b"%PDF-1.7\n/Encrypt 1 0 R\n",
                media_type="application/pdf",
                idempotency_key="encrypted",
            )
        )
    with pytest.raises(UploadRejected, match="FILE_TOO_LARGE"):
        await service.upload(command(content=b"x" * 65, idempotency_key="large"))

    await service.upload(command())
    with pytest.raises(UploadRejected, match="DUPLICATE_CONTENT"):
        await service.upload(command(idempotency_key="same-content-new-request"))


@pytest.mark.asyncio
@pytest.mark.integration
async def test_missing_critical_metadata_waits_for_authorized_review() -> None:
    service = InMemoryIngestionService()
    accepted = await service.upload(command(metadata={"classification": "INTERNAL"}))

    waiting = await service.process(accepted.job.id)
    assert waiting.state is IngestionState.WAITING_METADATA_REVIEW
    assert service.get_document(accepted.document.id).active_version_id is None

    service.review_metadata(
        accepted.version.id,
        corrections={"businessOwner": "Finance"},
        reviewer_id="knowledge-admin",
        approved=True,
    )
    completed = await service.process(accepted.job.id)
    assert completed.state is IngestionState.SEARCHABLE
