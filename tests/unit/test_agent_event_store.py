"""Replay, ordering, and ownership contracts for public Agent events."""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from atlasmind.agent.events import AgentEventStore, AgentEventType
from atlasmind.domain.common import ResourceNotAvailable


class FakeResult:
    def __init__(
        self,
        *,
        scalar: object = None,
        rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.scalar = scalar
        self.rows = rows or []

    def scalar_one(self) -> object:
        return self.scalar

    def scalar_one_or_none(self) -> object:
        return self.scalar

    def mappings(self) -> FakeResult:
        return self

    def all(self) -> list[dict[str, object]]:
        return self.rows


class FakeTransaction:
    async def __aenter__(self) -> FakeTransaction:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None


class FakeSession:
    def __init__(self, results: list[FakeResult]) -> None:
        self.results = deque(results)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def begin(self) -> FakeTransaction:
        return FakeTransaction()

    async def execute(self, statement: object, parameters: dict[str, Any]) -> FakeResult:
        self.calls.append((str(statement), parameters))
        return self.results.popleft()


class FakeSessions:
    def __init__(self, *sessions: FakeSession) -> None:
        self.sessions = deque(sessions)

    def __call__(self) -> FakeSession:
        return self.sessions.popleft()


@pytest.mark.asyncio
async def test_append_allocates_next_per_run_sequence_and_encodes_sse() -> None:
    run_id = str(uuid4())
    correlation_id = str(uuid4())
    session = FakeSession([FakeResult(), FakeResult(scalar=4), FakeResult()])
    store = AgentEventStore(FakeSessions(session))  # type: ignore[arg-type]

    persisted = await store.append(
        run_id=run_id,
        event_type=AgentEventType.RUN_STARTED,
        correlation_id=correlation_id,
        trace_id="trace-1",
        data={"threadId": run_id, "runId": run_id},
    )

    assert persisted.sequence == 4
    assert persisted.payload["metadata"] == {
        "schemaVersion": "1.0",
        "eventId": persisted.payload["metadata"]["eventId"],
        "sequence": 4,
        "runId": run_id,
        "correlationId": correlation_id,
        "visibility": "PUBLIC",
        "traceId": "trace-1",
    }
    assert persisted.as_sse().startswith(b"id: 4\nevent: RUN_STARTED\ndata: ")
    assert "FOR UPDATE" in session.calls[0][0]
    assert session.calls[2][1]["sequence"] == 4


@pytest.mark.asyncio
async def test_list_after_replays_public_events_in_database_order_for_owner() -> None:
    run_id = str(uuid4())
    principal_id = str(uuid4())
    now = datetime.now(UTC)
    session = FakeSession(
        [
            FakeResult(scalar=UUID(principal_id)),
            FakeResult(
                rows=[
                    {
                        "sequence": 2,
                        "event_type": "STEP_STARTED",
                        "payload": {"type": "STEP_STARTED"},
                        "created_at": now,
                    },
                    {
                        "sequence": 3,
                        "event_type": "RUN_FINISHED",
                        "payload": {"type": "RUN_FINISHED"},
                        "created_at": now,
                    },
                ]
            ),
        ]
    )
    store = AgentEventStore(FakeSessions(session))  # type: ignore[arg-type]

    replay = await store.list_after(
        run_id=run_id,
        principal_id=principal_id,
        after=1,
    )

    assert [item.sequence for item in replay] == [2, 3]
    assert replay[-1].is_terminal is True
    assert session.calls[1][1]["after"] == 1


@pytest.mark.asyncio
async def test_list_after_hides_missing_and_foreign_runs() -> None:
    run_id = str(uuid4())
    principal_id = str(uuid4())
    foreign_owner = str(uuid4())

    for owner in (None, UUID(foreign_owner)):
        store = AgentEventStore(  # type: ignore[arg-type]
            FakeSessions(FakeSession([FakeResult(scalar=owner)]))
        )
        with pytest.raises(ResourceNotAvailable):
            await store.list_after(
                run_id=run_id,
                principal_id=principal_id,
                after=0,
            )
