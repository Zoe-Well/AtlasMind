"""Authorized citation resolution without source enumeration."""

from __future__ import annotations

from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.domain.common import ResourceNotAvailable
from atlasmind.domain.knowledge import Citation, Evidence, SourceReference
from atlasmind.identity.models import AuthorizationSnapshot
from atlasmind.retrieval.authorization import RetrievalAuthorization


class CitationService:
    def __init__(self) -> None:
        self._authorization = RetrievalAuthorization()

    def resolve(
        self,
        citation: Citation,
        evidence: Evidence,
        context: AuthContext,
        current: AuthorizationSnapshot,
    ) -> SourceReference:
        try:
            citation.validate_against(evidence)
            self._authorization.review_evidence(
                context,
                evidence_scope_ids=evidence.scope_ids,
                current=current,
            )
        except (ValueError, Exception) as exc:
            raise ResourceNotAvailable() from exc
        return citation.source
