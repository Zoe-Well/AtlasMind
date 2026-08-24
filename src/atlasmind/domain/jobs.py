"""Persistent job, lease, attempt, and idempotency primitives."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum

from atlasmind.domain.common import InvalidState, utc_now


class JobState(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class Job:
    id: str
    kind: str
    idempotency_key: str
    state: JobState = JobState.QUEUED
    attempt: int = 0
    max_attempts: int = 5
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None

    def claim(self, owner: str, lease_for: timedelta, *, now: datetime | None = None) -> Job:
        current = now or utc_now()
        if self.state not in {JobState.QUEUED, JobState.RUNNING}:
            raise InvalidState(details={"reason": "JOB_NOT_CLAIMABLE"})
        if self.lease_expires_at and self.lease_expires_at > current and self.lease_owner != owner:
            raise InvalidState(details={"reason": "JOB_LEASE_ACTIVE"})
        return replace(
            self,
            state=JobState.RUNNING,
            attempt=self.attempt + 1,
            lease_owner=owner,
            lease_expires_at=current + lease_for,
        )

    def fail(self) -> Job:
        state = JobState.DEAD_LETTER if self.attempt >= self.max_attempts else JobState.QUEUED
        return replace(self, state=state, lease_owner=None, lease_expires_at=None)
