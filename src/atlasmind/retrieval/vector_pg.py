"""pgvector retrieval with mandatory scope and active-generation predicates."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from atlasmind.domain.knowledge import KnowledgeChunk
from atlasmind.retrieval.hybrid import RetrievalCandidate


class PgVectorRetriever:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def retrieve(
        self,
        embedding: Sequence[float],
        *,
        scope_ids: frozenset[str],
        active_generation: int,
        limit: int,
    ) -> list[RetrievalCandidate]:
        if not scope_ids:
            return []
        result = await self._session.execute(
            text("""SELECT id, document_version_id, ordinal, content, locator, scope_ids,
                   generation, 1 - (embedding <=> CAST(:embedding AS vector)) AS score
            FROM knowledge_chunks
            WHERE active = TRUE AND generation = :generation AND scope_ids && :scopes
              AND vector_dims(embedding) = vector_dims(CAST(:embedding AS vector))
            ORDER BY embedding <=> CAST(:embedding AS vector) LIMIT :limit"""),
            {
                "embedding": list(embedding),
                "generation": active_generation,
                "scopes": list(scope_ids),
                "limit": limit,
            },
        )
        return [
            RetrievalCandidate(
                KnowledgeChunk(
                    id=row.id,
                    document_version_id=row.document_version_id,
                    ordinal=row.ordinal,
                    content=row.content,
                    locator=row.locator,
                    scope_ids=frozenset(row.scope_ids),
                    generation=row.generation,
                ),
                float(row.score),
                "vector",
            )
            for row in result
        ]


class InMemoryVectorRetriever:
    def __init__(self, chunks: list[KnowledgeChunk]) -> None:
        self._chunks = chunks

    async def retrieve(
        self,
        embedding: Sequence[float],
        *,
        scope_ids: frozenset[str],
        active_generation: int,
        limit: int,
    ) -> list[RetrievalCandidate]:
        del embedding
        candidates = [
            chunk
            for chunk in self._chunks
            if chunk.active
            and chunk.generation == active_generation
            and chunk.scope_ids & scope_ids
        ]
        return [
            RetrievalCandidate(chunk, 1.0 / (index + 1), "vector")
            for index, chunk in enumerate(candidates[:limit])
        ]
