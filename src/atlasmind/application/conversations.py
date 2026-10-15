"""Owner-scoped conversations; a turn reuses the authoritative AgentRun answer."""

from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from atlasmind.domain.common import InvalidState, ResourceNotAvailable


class ConversationStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def accept_turn(
        self,
        session: AsyncSession,
        *,
        conversation_id: str | None,
        principal_id: str,
        query: str,
        now: datetime,
    ) -> tuple[UUID, int]:
        """Call inside the same transaction as the run insert; lock prevents overlapping turns."""
        principal = UUID(principal_id)
        if conversation_id is None:
            identifier = uuid4()
            await session.execute(
                text("""
                INSERT INTO conversations (id, principal_id, title, created_at, updated_at)
                VALUES (:id, :principal, :title, :now, :now)
            """),
                {
                    "id": identifier,
                    "principal": principal,
                    "title": " ".join(query.split())[:120],
                    "now": now,
                },
            )
            return identifier, 1

        identifier = UUID(conversation_id)
        owner = (
            await session.execute(
                text("""
            SELECT id FROM conversations
            WHERE id = :id AND principal_id = :principal FOR UPDATE
        """),
                {"id": identifier, "principal": principal},
            )
        ).scalar_one_or_none()
        if owner is None:
            raise ResourceNotAvailable()
        active = (
            await session.execute(
                text("""
            SELECT id FROM agent_runs WHERE conversation_id = :id
            AND state IN ('QUEUED', 'RUNNING', 'WAITING_APPROVAL') LIMIT 1
        """),
                {"id": identifier},
            )
        ).scalar_one_or_none()
        if active is not None:
            raise InvalidState()
        ordinal = (
            await session.execute(
                text("""
            SELECT COALESCE(MAX(turn_index), 0) + 1 FROM agent_runs WHERE conversation_id = :id
        """),
                {"id": identifier},
            )
        ).scalar_one()
        await session.execute(
            text("UPDATE conversations SET updated_at = :now WHERE id = :id"),
            {"id": identifier, "now": now},
        )
        return identifier, int(ordinal)

    @staticmethod
    def summary(row: Mapping[str, Any]) -> dict[str, object]:
        return {
            "id": str(row["id"]),
            "title": row["title"],
            "createdAt": row["created_at"].isoformat(),
            "updatedAt": row["updated_at"].isoformat(),
        }

    async def list(
        self,
        principal_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, object]:
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        text("""
                SELECT id, title, created_at, updated_at FROM conversations
                WHERE principal_id = :principal ORDER BY updated_at DESC, id DESC
                LIMIT :limit OFFSET :offset
            """),
                        {"principal": UUID(principal_id), "limit": limit + 1, "offset": offset},
                    )
                )
                .mappings()
                .all()
            )
        return {
            "items": [self.summary(row) for row in rows[:limit]],
            "nextOffset": offset + limit if len(rows) > limit else None,
        }

    async def read(
        self,
        conversation_id: str,
        principal_id: str,
        *,
        read_run: Callable[[str, str], Awaitable[dict[str, object]]],
        limit: int = 50,
        before: int | None = None,
    ) -> dict[str, object]:
        async with self._sessions() as session:
            conversation = (
                (
                    await session.execute(
                        text("""
                SELECT id, title, created_at, updated_at FROM conversations
                WHERE id = :id AND principal_id = :principal
            """),
                        {"id": UUID(conversation_id), "principal": UUID(principal_id)},
                    )
                )
                .mappings()
                .first()
            )
            if conversation is None:
                raise ResourceNotAvailable()
            rows = (
                (
                    await session.execute(
                        text("""
                SELECT id, turn_index FROM agent_runs
                WHERE conversation_id = :id AND principal_id = :principal
                  AND (CAST(:before AS integer) IS NULL OR turn_index < :before)
                ORDER BY turn_index DESC LIMIT :limit
            """),
                        {
                            "id": UUID(conversation_id),
                            "principal": UUID(principal_id),
                            "before": before,
                            "limit": limit + 1,
                        },
                    )
                )
                .mappings()
                .all()
            )
        page = rows[:limit]
        return {
            "conversation": self.summary(conversation),
            "items": [await read_run(str(row["id"]), principal_id) for row in reversed(page)],
            "nextBefore": int(page[-1]["turn_index"]) if len(rows) > limit else None,
        }
