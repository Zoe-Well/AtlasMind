"""Versioned, classified transactional outbox envelopes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from atlasmind.domain.common import new_id, utc_now


class DataClassification(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    event_id: str
    event_type: str
    schema_version: int
    occurred_at: datetime
    producer: str
    correlation_id: str
    aggregate_type: str
    aggregate_id: str
    aggregate_version: int
    classification: DataClassification
    payload: dict[str, Any]
    causation_id: str | None = None

    @classmethod
    def create(cls, **values: Any) -> EventEnvelope:
        return cls(event_id=new_id(), occurred_at=utc_now(), schema_version=1, **values)

    def validate(self) -> None:
        if not self.event_type.endswith(f".v{self.schema_version}"):
            raise ValueError("event type and schema version mismatch")
        forbidden = {"token", "secret", "password", "role_codes", "scope_ids"}
        if forbidden & {key.casefold() for key in self.payload}:
            raise ValueError("event payload contains forbidden authority or secret fields")


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: EventEnvelope) -> None:
        event.validate()
        await self._session.execute(
            text("""INSERT INTO outbox_events
            (id, event_type, schema_version, occurred_at, correlation_id, classification, payload)
            VALUES (:id, :type, :version, :at, :correlation, :classification, :payload)"""),
            {
                "id": event.event_id,
                "type": event.event_type,
                "version": event.schema_version,
                "at": event.occurred_at,
                "correlation": event.correlation_id,
                "classification": event.classification.value,
                "payload": event.payload,
            },
        )
