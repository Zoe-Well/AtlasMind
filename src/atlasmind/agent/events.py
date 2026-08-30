"""AG-UI-aligned, replayable public AgentRun events."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from atlasmind.domain.common import ResourceNotAvailable, utc_now


class AgentEventType(StrEnum):
    """Subset of AG-UI event names used by AtlasMind."""

    RUN_STARTED = "RUN_STARTED"
    RUN_FINISHED = "RUN_FINISHED"
    RUN_ERROR = "RUN_ERROR"
    STEP_STARTED = "STEP_STARTED"
    STEP_FINISHED = "STEP_FINISHED"
    ACTIVITY_SNAPSHOT = "ACTIVITY_SNAPSHOT"
    TOOL_CALL_START = "TOOL_CALL_START"
    TOOL_CALL_ARGS = "TOOL_CALL_ARGS"
    TOOL_CALL_END = "TOOL_CALL_END"
    TOOL_CALL_RESULT = "TOOL_CALL_RESULT"
    TEXT_MESSAGE_START = "TEXT_MESSAGE_START"
    TEXT_MESSAGE_CONTENT = "TEXT_MESSAGE_CONTENT"
    TEXT_MESSAGE_END = "TEXT_MESSAGE_END"
    STATE_SNAPSHOT = "STATE_SNAPSHOT"
    CUSTOM = "CUSTOM"


TERMINAL_EVENT_TYPES = frozenset(
    {AgentEventType.RUN_FINISHED.value, AgentEventType.RUN_ERROR.value}
)


@dataclass(frozen=True, slots=True)
class PersistedAgentEvent:
    sequence: int
    event_type: str
    payload: dict[str, Any]
    created_at: datetime

    @property
    def is_terminal(self) -> bool:
        return self.event_type in TERMINAL_EVENT_TYPES

    def as_sse(self) -> bytes:
        data = json.dumps(self.payload, ensure_ascii=False, separators=(",", ":"))
        return f"id: {self.sequence}\nevent: {self.event_type}\ndata: {data}\n\n".encode()


class AgentEventStore:
    """PostgreSQL event log providing ordered replay for SSE consumers."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def append(
        self,
        *,
        run_id: str,
        event_type: AgentEventType,
        correlation_id: str,
        trace_id: str | None,
        data: dict[str, Any],
        visibility: str = "PUBLIC",
    ) -> PersistedAgentEvent:
        now = utc_now()
        event_id = str(uuid4())
        async with self._sessions() as session, session.begin():
            # Serializing on the parent run makes sequence assignment safe across workers.
            await session.execute(
                text("SELECT id FROM agent_runs WHERE id = :id FOR UPDATE"),
                {"id": UUID(run_id)},
            )
            sequence = int(
                (
                    await session.execute(
                        text(
                            "SELECT COALESCE(MAX(sequence), 0) + 1 "
                            "FROM agent_run_events WHERE run_id = :id"
                        ),
                        {"id": UUID(run_id)},
                    )
                ).scalar_one()
            )
            metadata: dict[str, Any] = {
                "schemaVersion": "1.0",
                "eventId": event_id,
                "sequence": sequence,
                "runId": run_id,
                "correlationId": correlation_id,
                "visibility": visibility,
            }
            if trace_id:
                metadata["traceId"] = trace_id
            payload = {
                "type": event_type.value,
                "timestamp": int(now.timestamp() * 1000),
                "metadata": metadata,
                **data,
            }
            await session.execute(
                text(
                    """
                    INSERT INTO agent_run_events
                        (id, run_id, sequence, event_type, payload, visibility, created_at)
                    VALUES
                        (:id, :run_id, :sequence, :event_type, CAST(:payload AS jsonb),
                         :visibility, :created_at)
                    """
                ),
                {
                    "id": UUID(event_id),
                    "run_id": UUID(run_id),
                    "sequence": sequence,
                    "event_type": event_type.value,
                    "payload": json.dumps(payload, ensure_ascii=False),
                    "visibility": visibility,
                    "created_at": now,
                },
            )
        return PersistedAgentEvent(sequence, event_type.value, payload, now)

    async def list_after(
        self,
        *,
        run_id: str,
        principal_id: str,
        after: int,
        limit: int = 200,
    ) -> tuple[PersistedAgentEvent, ...]:
        async with self._sessions() as session:
            owner = (
                await session.execute(
                    text("SELECT principal_id FROM agent_runs WHERE id = :id"),
                    {"id": UUID(run_id)},
                )
            ).scalar_one_or_none()
            if owner is None or str(owner) != principal_id:
                raise ResourceNotAvailable()
            rows = (
                (
                    await session.execute(
                        text(
                            """
                            SELECT sequence, event_type, payload, created_at
                            FROM agent_run_events
                            WHERE run_id = :run_id AND sequence > :after
                              AND visibility = 'PUBLIC'
                            ORDER BY sequence
                            LIMIT :limit
                            """
                        ),
                        {
                            "run_id": UUID(run_id),
                            "after": max(0, after),
                            "limit": max(1, min(limit, 500)),
                        },
                    )
                )
                .mappings()
                .all()
            )
        return tuple(
            PersistedAgentEvent(
                sequence=int(row["sequence"]),
                event_type=str(row["event_type"]),
                payload=dict(row["payload"]),
                created_at=row["created_at"],
            )
            for row in rows
        )
