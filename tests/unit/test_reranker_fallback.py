"""Reranking failure must preserve deterministic RRF candidates."""

from __future__ import annotations

from atlasmind.domain.knowledge import KnowledgeChunk
from atlasmind.infrastructure.ai_ports import RankedText
from atlasmind.retrieval.hybrid import RetrievalCandidate
from atlasmind.retrieval.reranker import rerank_candidates


class InvalidReranker:
    async def rerank(
        self,
        query: str,
        texts: dict[str, str],
        *,
        limit: int,
    ) -> list[RankedText]:
        del query, texts, limit
        raise ValueError("invalid model response")


def candidate(identifier: str, score: float) -> RetrievalCandidate:
    return RetrievalCandidate(
        KnowledgeChunk(
            id=identifier,
            document_version_id="version-1",
            ordinal=1,
            content=f"content-{identifier}",
            locator="paragraph=1",
            scope_ids=frozenset({"scope-a"}),
            generation=1,
        ),
        score,
        "rrf",
    )


async def test_invalid_reranker_response_falls_back_to_rrf_order() -> None:
    candidates = [candidate("chunk-a", 0.9), candidate("chunk-b", 0.8)]
    metrics = {}
    ranked = await rerank_candidates(
        "question",
        candidates,
        InvalidReranker(),
        limit=2,
        timeout_ms=100,
        metrics=metrics,
    )

    assert [item.chunk.id for item in ranked] == ["chunk-a", "chunk-b"]
    assert metrics == {"rerank_degraded": 1, "rerank_invalid_response": 1}
