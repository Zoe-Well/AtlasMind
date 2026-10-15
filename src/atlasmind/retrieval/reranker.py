"""Bounded reranking with deterministic timeout degradation."""

from __future__ import annotations

import asyncio

import httpx

from atlasmind.infrastructure.ai_ports import Reranker
from atlasmind.retrieval.hybrid import RetrievalCandidate


async def rerank_candidates(
    query: str,
    candidates: list[RetrievalCandidate],
    adapter: Reranker,
    *,
    limit: int,
    timeout_ms: int,
    metrics: dict[str, int] | None = None,
) -> list[RetrievalCandidate]:
    bounded = candidates[: max(limit * 4, limit)]
    by_id = {candidate.chunk.id: candidate for candidate in bounded}
    try:
        rankings = await asyncio.wait_for(
            adapter.rerank(
                query, {key: value.chunk.content for key, value in by_id.items()}, limit=limit
            ),
            timeout=timeout_ms / 1000,
        )
    except (TimeoutError, ValueError, httpx.HTTPError) as exc:
        if metrics is not None:
            metrics["rerank_degraded"] = 1
            reason = (
                "timeout"
                if isinstance(exc, TimeoutError)
                else "invalid_response"
                if isinstance(exc, ValueError)
                else "transport_error"
            )
            metrics[f"rerank_{reason}"] = 1
        return bounded[:limit]
    return [
        RetrievalCandidate(by_id[item.identifier].chunk, item.score, "reranker")
        for item in rankings
        if item.identifier in by_id
    ][:limit]
