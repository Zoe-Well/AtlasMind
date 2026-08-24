"""PostgreSQL persistence boundary for core RAG entities."""

from __future__ import annotations

from hashlib import sha256

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from atlasmind.domain.knowledge import AgentRun, Citation, Evidence, KnowledgeChunk


class KnowledgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_chunk(self, chunk: KnowledgeChunk) -> None:
        await self._session.execute(
            text("""INSERT INTO knowledge_chunks
            (id, document_version_id, ordinal, content, locator, scope_ids, generation, active)
            VALUES (:id, :version, :ordinal, :content, :locator, :scopes, :generation, :active)"""),
            {
                "id": chunk.id,
                "version": chunk.document_version_id,
                "ordinal": chunk.ordinal,
                "content": chunk.content,
                "locator": chunk.locator,
                "scopes": list(chunk.scope_ids),
                "generation": chunk.generation,
                "active": chunk.active,
            },
        )

    async def add_run(self, run: AgentRun) -> None:
        await self._session.execute(
            text("""INSERT INTO agent_runs (
                id, principal_id, correlation_id, query_digest, scope_ids,
                authz_revision, state, created_at
            ) VALUES (
                :id, :principal, :correlation, :query, :scopes,
                :revision, :state, :created
            )"""),
            {
                "id": run.id,
                "principal": run.principal_id,
                "correlation": run.correlation_id,
                "query": f"sha256:{sha256(run.query.encode()).hexdigest()}",
                "scopes": list(run.scope_ids),
                "revision": run.authz_revision,
                "state": run.state.value,
                "created": run.created_at,
            },
        )

    async def add_evidence(self, run_id: str, evidence: Evidence) -> None:
        await self._session.execute(
            text("""INSERT INTO evidence_records
            (id, run_id, source_type, source_id, source_version, locator, scope_ids,
             content_digest, validity, authz_revision, verified_at)
            VALUES (:id, :run, :type, :source, :version, :locator, :scopes,
                    :digest, :validity, :revision, :verified)"""),
            {
                "id": evidence.id,
                "run": run_id,
                "type": evidence.source.type,
                "source": evidence.source.canonical_id,
                "version": evidence.source.version,
                "locator": evidence.source.locator,
                "scopes": list(evidence.scope_ids),
                "digest": evidence.digest,
                "validity": evidence.validity.value,
                "revision": evidence.authz_revision,
                "verified": evidence.verified_at,
            },
        )

    async def add_citation(self, run_id: str, citation: Citation) -> None:
        await self._session.execute(
            text("""INSERT INTO citations (id, run_id, evidence_id, claim, support)
            VALUES (:id, :run, :evidence, :claim, :support)"""),
            {
                "id": citation.id,
                "run": run_id,
                "evidence": citation.evidence_id,
                "claim": citation.claim,
                "support": citation.support,
            },
        )
