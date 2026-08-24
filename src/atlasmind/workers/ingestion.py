"""Lease-aware persistent ingestion worker orchestration."""

from __future__ import annotations

from datetime import timedelta

from atlasmind.application.ingest_document import InMemoryIngestionService
from atlasmind.domain.common import utc_now
from atlasmind.ingestion.models import IngestionJob, IngestionState


class IngestionWorker:
    def __init__(
        self,
        service: InMemoryIngestionService,
        *,
        worker_id: str,
        lease_for: timedelta = timedelta(minutes=2),
    ) -> None:
        self.service = service
        self.worker_id = worker_id
        self.lease_for = lease_for

    def claim_next(self) -> IngestionJob | None:
        now = utc_now()
        for job in sorted(self.service.jobs.values(), key=lambda item: item.created_at):
            if job.state is IngestionState.QUEUED:
                claimed = job.__class__(
                    document_version_id=job.document_version_id,
                    idempotency_key=job.idempotency_key,
                    id=job.id,
                    state=job.state,
                    current_stage=job.current_stage,
                    attempt=job.attempt,
                    max_attempts=job.max_attempts,
                    lease_owner=self.worker_id,
                    lease_until=now + self.lease_for,
                    failure_code=job.failure_code,
                    created_at=job.created_at,
                    started_at=job.started_at,
                    finished_at=job.finished_at,
                )
                self.service.jobs[job.id] = claimed
                return claimed
        return None

    async def run_once(self) -> IngestionJob | None:
        job = self.claim_next()
        if job is None:
            return None
        return await self.service.process(job.id)
