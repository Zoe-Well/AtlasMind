"""Atomic activation rules for searchable document versions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from atlasmind.domain.common import InvalidState, utc_now
from atlasmind.ingestion.metadata import requires_review
from atlasmind.ingestion.models import (
    DocumentMetadata,
    DocumentStatus,
    ManagedDocument,
    ManagedDocumentVersion,
    Projection,
    ProjectionState,
    VersionLifecycle,
)
from atlasmind.ingestion.projections import REQUIRED_PROJECTIONS


def activate_version(
    document: ManagedDocument,
    version: ManagedDocumentVersion,
    *,
    projections: tuple[Projection, ...],
    metadata: Mapping[str, DocumentMetadata],
) -> tuple[ManagedDocument, ManagedDocumentVersion]:
    if document.status is not DocumentStatus.ACTIVE:
        raise InvalidState(details={"reason": "DOCUMENT_NOT_ACTIVE"})
    if requires_review(metadata):
        raise InvalidState(details={"reason": "METADATA_REVIEW_REQUIRED"})
    ready = {
        item.kind
        for item in projections
        if item.generation == version.generation and item.state is ProjectionState.READY
    }
    if not set(REQUIRED_PROJECTIONS).issubset(ready):
        raise InvalidState(details={"reason": "REQUIRED_PROJECTION_NOT_READY"})
    now = utc_now()
    return (
        replace(document, active_version_id=version.id, updated_at=now),
        replace(version, lifecycle=VersionLifecycle.SEARCHABLE),
    )
