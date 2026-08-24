"""Versioned, bounded lexical/vector retrieval pipeline."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol

from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.identity.models import AuthorizationSnapshot
from atlasmind.retrieval.authorization import RetrievalAuthorization
from atlasmind.retrieval.hybrid import RetrievalCandidate, reciprocal_rank_fusion
from atlasmind.retrieval.policy import RetrievalPolicy


class VectorBackend(Protocol):
    async def retrieve(
        self, embedding: Sequence[float], **kwargs: object
    ) -> list[RetrievalCandidate]: ...


class LexicalBackend(Protocol):
    async def retrieve(self, query: str, **kwargs: object) -> list[RetrievalCandidate]: ...


class RetrievalPipeline:
    def __init__(
        self,
        vector: VectorBackend,
        lexical: LexicalBackend,
        embed: Callable[[list[str]], Awaitable[list[list[float]]]],
        policy: RetrievalPolicy,
    ) -> None:
        self._vector = vector
        self._lexical = lexical
        self._embed = embed
        self.policy = policy
        self._authorization = RetrievalAuthorization()

    async def retrieve(
        self,
        query: str,
        context: AuthContext,
        current: AuthorizationSnapshot,
        *,
        active_generation: int,
    ) -> list[RetrievalCandidate]:
        scopes = context.scope_ids & current.active_scope_ids
        if not scopes:
            return []
        embedding = (await self._embed([query]))[0]
        kwargs = {
            "scope_ids": scopes,
            "active_generation": active_generation,
            "limit": self.policy.budget.candidate_limit,
        }
        vector = await self._vector.retrieve(embedding, **kwargs)
        lexical = await self._lexical.retrieve(query, **kwargs)
        fused = reciprocal_rank_fusion(
            [vector, lexical],
            constant=self.policy.rrf_constant,
            limit=self.policy.budget.result_limit,
        )
        filtered = self._authorization.filter_candidates(
            context,
            [item.chunk for item in fused],
            current=current,
            active_generation=active_generation,
        )
        allowed = {chunk.id for chunk in filtered}
        return [item for item in fused if item.chunk.id in allowed]
