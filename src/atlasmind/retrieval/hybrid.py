"""Deterministic reciprocal-rank fusion across backend-independent candidates."""

from __future__ import annotations

from dataclasses import dataclass

from atlasmind.domain.knowledge import KnowledgeChunk


@dataclass(frozen=True, slots=True)
class RetrievalCandidate:
    chunk: KnowledgeChunk
    score: float
    method: str


def reciprocal_rank_fusion(
    rankings: list[list[RetrievalCandidate]], *, constant: int = 60, limit: int = 10
) -> list[RetrievalCandidate]:
    scores: dict[str, float] = {}
    chunks: dict[str, KnowledgeChunk] = {}
    methods: dict[str, set[str]] = {}
    for ranking in rankings:
        for rank, candidate in enumerate(ranking, start=1):
            identifier = candidate.chunk.id
            chunks[identifier] = candidate.chunk
            methods.setdefault(identifier, set()).add(candidate.method)
            scores[identifier] = scores.get(identifier, 0.0) + 1.0 / (constant + rank)
    ordered = sorted(scores, key=lambda identifier: (-scores[identifier], identifier))[:limit]
    return [
        RetrievalCandidate(
            chunks[identifier], scores[identifier], "+".join(sorted(methods[identifier]))
        )
        for identifier in ordered
    ]
