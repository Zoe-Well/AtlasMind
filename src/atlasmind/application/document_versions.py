"""Immutable document-version and duplicate relation rules."""

from __future__ import annotations

from collections.abc import Iterable

from atlasmind.ingestion.file_validation import UploadRejected
from atlasmind.ingestion.models import ManagedDocumentVersion


def ensure_unique_content(
    versions: Iterable[ManagedDocumentVersion],
    *,
    source_key_document_ids: frozenset[str],
    content_digest: str,
) -> None:
    for version in versions:
        if (
            version.document_id in source_key_document_ids
            and version.content_digest == content_digest
        ):
            raise UploadRejected("DUPLICATE_CONTENT")


def next_generation(versions: Iterable[ManagedDocumentVersion], document_id: str) -> int:
    generations = [item.generation for item in versions if item.document_id == document_id]
    return max(generations, default=0) + 1


def inherited_metadata_keys() -> frozenset[str]:
    return frozenset({"businessOwner", "classification"})
