"""Bounded lease-based worker loop primitives."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from atlasmind.domain.common import utc_now
from atlasmind.domain.jobs import Job, JobState


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    initial_seconds: float = 1.0
    maximum_seconds: float = 60.0

    def delay(self, attempt: int) -> float:
        multiplier = float(2 ** max(attempt - 1, 0))
        return min(self.initial_seconds * multiplier, self.maximum_seconds)


async def claim_next_job(
    session: AsyncSession,
    *,
    worker_id: str,
    lease_for: timedelta,
) -> Job | None:
    """Atomically claim one available job without blocking competing workers."""
    now = utc_now()
    result = await session.execute(
        text("""SELECT id, kind, idempotency_key, state, attempt, max_attempts,
                      lease_owner, lease_expires_at
               FROM jobs
               WHERE state IN ('QUEUED', 'RUNNING')
                 AND available_at <= :now
                 AND (lease_expires_at IS NULL OR lease_expires_at <= :now)
               ORDER BY available_at, created_at
               FOR UPDATE SKIP LOCKED
               LIMIT 1"""),
        {"now": now},
    )
    row = result.first()
    if row is None:
        return None
    job = Job(
        id=row.id,
        kind=row.kind,
        idempotency_key=row.idempotency_key,
        state=JobState(row.state),
        attempt=row.attempt,
        max_attempts=row.max_attempts,
        lease_owner=row.lease_owner,
        lease_expires_at=row.lease_expires_at,
    ).claim(worker_id, lease_for, now=now)
    await session.execute(
        text("""UPDATE jobs
               SET state = :state, attempt = :attempt,
                   lease_owner = :owner, lease_expires_at = :expires
               WHERE id = :id"""),
        {
            "id": job.id,
            "state": job.state.value,
            "attempt": job.attempt,
            "owner": job.lease_owner,
            "expires": job.lease_expires_at,
        },
    )
    return job


async def renew_lease(
    session: AsyncSession,
    job: Job,
    *,
    worker_id: str,
    lease_for: timedelta,
) -> None:
    result = await session.execute(
        text("""UPDATE jobs SET lease_expires_at = :expires
               WHERE id = :id AND state = 'RUNNING' AND lease_owner = :owner"""),
        {"id": job.id, "owner": worker_id, "expires": utc_now() + lease_for},
    )
    if getattr(result, "rowcount", 0) != 1:
        raise RuntimeError("job lease is no longer owned by this worker")


async def run_worker(
    claim: Callable[[], Awaitable[Job | None]],
    process: Callable[[Job], Awaitable[None]],
    record_failure: Callable[[Job, Exception], Awaitable[None]],
    *,
    retry: RetryPolicy | None = None,
    stop: asyncio.Event | None = None,
) -> None:
    stop_event = stop or asyncio.Event()
    retry_policy = retry or RetryPolicy()
    while not stop_event.is_set():
        job = await claim()
        if job is None:
            await asyncio.sleep(0.1)
            continue
        try:
            await process(job)
        except Exception as exc:  # worker boundary must isolate individual jobs
            await record_failure(job, exc)
            await asyncio.sleep(retry_policy.delay(job.attempt))
