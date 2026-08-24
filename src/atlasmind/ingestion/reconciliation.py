"""Lease recovery and derived-projection reconciliation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime

from atlasmind.ingestion.models import (
    DocumentStatus,
    IngestionJob,
    IngestionState,
    ManagedDocument,
    ManagedDocumentVersion,
    Projection,
    ProjectionState,
    VersionLifecycle,
)


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    recovered_job_ids: tuple[str, ...]
    retired_projection_ids: tuple[str, ...]
    orphan_projection_ids: tuple[str, ...]


def reconcile(
    *,
    now: datetime,
    documents: Mapping[str, ManagedDocument],
    versions: Mapping[str, ManagedDocumentVersion],
    jobs: dict[str, IngestionJob],
    projections: dict[str, Projection],
) -> ReconciliationReport:
    recovered: list[str] = []
    retired: list[str] = []
    orphaned: list[str] = []
    for job_id, job in tuple(jobs.items()):
        if (
            job.state is IngestionState.RUNNING
            and job.lease_until is not None
            and job.lease_until <= now
        ):
            jobs[job_id] = replace(
                job,
                state=IngestionState.QUEUED,
                lease_owner=None,
                lease_until=None,
            )
            recovered.append(job_id)
    for projection_id, projection in tuple(projections.items()):
        version = versions.get(projection.document_version_id)
        if version is None:
            projections.pop(projection_id)
            orphaned.append(projection_id)
            continue
        document = documents.get(version.document_id)
        should_retire = (
            document is None
            or document.status is not DocumentStatus.ACTIVE
            or version.lifecycle
            in {
                VersionLifecycle.SUPERSEDED,
                VersionLifecycle.REVOKED,
                VersionLifecycle.FAILED,
            }
        )
        if should_retire and projection.state is not ProjectionState.RETIRED:
            projections[projection_id] = replace(projection, state=ProjectionState.RETIRED)
            retired.append(projection_id)
    return ReconciliationReport(tuple(recovered), tuple(retired), tuple(orphaned))
