"""Metadata provenance, merge precedence, schema checks, and review."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from atlasmind.domain.common import utc_now
from atlasmind.ingestion.models import (
    DocumentMetadata,
    MetadataOrigin,
    MetadataReviewStatus,
)

CRITICAL_KEYS = frozenset({"businessOwner", "classification"})


def build_metadata(
    version_id: str,
    *,
    user: Mapping[str, Any],
    file_facts: Mapping[str, Any],
) -> dict[str, DocumentMetadata]:
    records: dict[str, DocumentMetadata] = {}
    for key, value in file_facts.items():
        records[key] = DocumentMetadata(
            document_version_id=version_id,
            key=key,
            value=value,
            origin=MetadataOrigin.FILE,
            review_status=MetadataReviewStatus.CONFIRMED,
        )
    for key, value in user.items():
        if not isinstance(key, str) or not key or value is None:
            raise ValueError("INVALID_METADATA")
        records[key] = DocumentMetadata(
            document_version_id=version_id,
            key=key,
            value=value,
            origin=MetadataOrigin.USER,
            review_status=MetadataReviewStatus.CONFIRMED,
        )
    return records


def requires_review(records: Mapping[str, DocumentMetadata]) -> bool:
    return not CRITICAL_KEYS.issubset(records) or any(
        item.key in CRITICAL_KEYS and item.review_status is not MetadataReviewStatus.CONFIRMED
        for item in records.values()
    )


def review_metadata(
    records: Mapping[str, DocumentMetadata],
    *,
    version_id: str,
    corrections: Mapping[str, Any],
    reviewer_id: str,
    approved: bool,
) -> dict[str, DocumentMetadata]:
    updated = dict(records)
    status = MetadataReviewStatus.CONFIRMED if approved else MetadataReviewStatus.REJECTED
    for key, value in corrections.items():
        if not key or value is None:
            raise ValueError("INVALID_METADATA")
        updated[key] = DocumentMetadata(
            document_version_id=version_id,
            key=key,
            value=value,
            origin=MetadataOrigin.USER,
            review_status=status,
            reviewed_by=reviewer_id,
            reviewed_at=utc_now(),
        )
    if approved:
        for key, item in tuple(updated.items()):
            if item.review_status is MetadataReviewStatus.PENDING:
                updated[key] = replace(
                    item,
                    review_status=MetadataReviewStatus.CONFIRMED,
                    reviewed_by=reviewer_id,
                    reviewed_at=utc_now(),
                )
    return updated
