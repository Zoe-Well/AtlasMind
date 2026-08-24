"""Pre-retrieval filters and pre-return authorization revision review."""

from __future__ import annotations

from collections.abc import Iterable

from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.domain.common import AuthorizationDenied
from atlasmind.domain.knowledge import KnowledgeChunk
from atlasmind.identity.authorization import AuthorizationService
from atlasmind.identity.models import Action, AuthorizationSnapshot


class RetrievalAuthorization:
    def __init__(self) -> None:
        self._authorization = AuthorizationService()

    def filter_candidates(
        self,
        context: AuthContext,
        candidates: Iterable[KnowledgeChunk],
        *,
        current: AuthorizationSnapshot,
        active_generation: int,
    ) -> list[KnowledgeChunk]:
        authorized = self._authorization.authorize(
            context,
            action=Action.READ,
            requested_scope_ids=context.scope_ids,
            current=current,
        )
        return [
            chunk
            for chunk in candidates
            if chunk.active
            and chunk.generation == active_generation
            and bool(chunk.scope_ids & authorized)
        ]

    def review_evidence(
        self,
        context: AuthContext,
        *,
        evidence_scope_ids: frozenset[str],
        current: AuthorizationSnapshot,
    ) -> frozenset[str]:
        scopes = self._authorization.authorize(
            context,
            action=Action.CITE,
            requested_scope_ids=evidence_scope_ids,
            current=current,
        )
        if not evidence_scope_ids.issubset(scopes):
            raise AuthorizationDenied(details={"reason": "EVIDENCE_SCOPE_REVOKED"})
        return scopes
