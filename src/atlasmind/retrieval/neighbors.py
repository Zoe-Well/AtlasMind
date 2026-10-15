"""Adjacent canonical chunks with independent citations and full scope checks."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from atlasmind.retrieval.hybrid import RetrievalCandidate


async def neighbor_rows(
    sessions: async_sessionmaker[AsyncSession],
    anchors: list[RetrievalCandidate],
    scopes: frozenset[str],
    limit: int,
) -> list[RowMapping]:
    if not scopes or limit <= 0:
        return []
    async with sessions() as session:
        return (
            (
                await session.execute(
                    text("""
            SELECT * FROM (
            SELECT DISTINCT ON (c.id) c.id, c.document_version_id, c.ordinal, c.content,
                   c.locator, c.scope_ids, c.generation, 0.0 AS score,
                   array_position(CAST(:ids AS uuid[]),anchor.id) AS anchor_rank
            FROM knowledge_chunks anchor
            JOIN knowledge_chunks c ON c.document_version_id = anchor.document_version_id
                AND c.section_key = anchor.section_key
                AND abs(c.ordinal - anchor.ordinal) = 1
            JOIN document_versions v ON v.id = c.document_version_id
            JOIN knowledge_documents d ON d.active_version_id = v.id AND d.id = v.document_id
            WHERE anchor.id = ANY(:ids) AND c.id != ALL(:ids)
              AND anchor.active AND c.active AND v.searchable AND d.active
              AND cardinality(anchor.scope_ids)>0 AND anchor.scope_ids <@ :scopes
              AND cardinality(c.scope_ids)>0 AND c.scope_ids <@ :scopes
              AND cardinality(v.scope_ids)>0 AND v.scope_ids <@ :scopes
              AND cardinality(d.scope_ids)>0 AND d.scope_ids <@ :scopes
            ORDER BY c.id, anchor_rank
            ) adjacent ORDER BY anchor_rank,ordinal,id
            LIMIT :limit
        """),
                    {
                        "ids": [UUID(item.chunk.id) for item in anchors],
                        "scopes": [UUID(value) for value in scopes],
                        "limit": limit,
                    },
                )
            )
            .mappings()
            .all()
        )
