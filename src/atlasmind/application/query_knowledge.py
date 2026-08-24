"""Simple authorized knowledge query use case."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.application.answer_composer import AnswerComposer
from atlasmind.domain.common import new_id, utc_now
from atlasmind.domain.knowledge import (
    AgentRun,
    Evidence,
    EvidenceValidity,
    RunState,
    SourceReference,
)
from atlasmind.identity.models import AuthorizationSnapshot
from atlasmind.retrieval.authorization import RetrievalAuthorization
from atlasmind.retrieval.pipeline import RetrievalPipeline


class QueryKnowledge:
    def __init__(self, pipeline: RetrievalPipeline) -> None:
        self._pipeline = pipeline
        self._composer = AnswerComposer()
        self._authorization = RetrievalAuthorization()

    async def execute(
        self,
        query: str,
        context: AuthContext,
        current: AuthorizationSnapshot,
        *,
        active_generation: int,
    ) -> AgentRun:
        run = AgentRun(
            principal_id=context.principal_id,
            query=query,
            correlation_id=context.correlation_id,
            scope_ids=context.scope_ids & current.active_scope_ids,
            authz_revision=context.authz_revision,
            state=RunState.RUNNING,
        )
        candidates = await self._pipeline.retrieve(
            query,
            context,
            current,
            active_generation=active_generation,
        )
        evidence: list[Evidence] = []
        for candidate in candidates:
            chunk = candidate.chunk
            self._authorization.review_evidence(
                context,
                evidence_scope_ids=chunk.scope_ids,
                current=current,
            )
            evidence.append(
                Evidence(
                    id=new_id(),
                    source=SourceReference(
                        "DOCUMENT",
                        chunk.id,
                        chunk.document_version_id,
                        chunk.locator,
                    ),
                    scope_ids=chunk.scope_ids,
                    content=chunk.content,
                    digest=f"sha256:{sha256(chunk.content.encode()).hexdigest()}",
                    validity=EvidenceValidity.VALID,
                    authz_revision=current.revision,
                    verified_at=utc_now(),
                )
            )
        answer = self._composer.compose(evidence)
        return replace(
            run,
            state=RunState.COMPLETED,
            answer=answer.text,
            evidence_status=answer.evidence_status,
            citations=answer.citations,
        )
