"""Persistent upload, indexing, graph projection and grounded QA for the real MVP."""

# ruff: noqa: E501 -- SQL remains readable when its column lists stay intact.

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from io import BytesIO
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from atlasmind.domain.common import (
    InvalidState,
    ModelCapabilityUnavailable,
    ResourceNotAvailable,
    utc_now,
)
from atlasmind.infrastructure.neo4j_runtime import GraphProjectionRecord, Neo4jRuntime
from atlasmind.infrastructure.object_store import S3ObjectStore
from atlasmind.infrastructure.openai_compatible import GraphExtraction, GroundedAnswer
from atlasmind.ingestion.chunking import DeterministicChunker, IngestedChunk
from atlasmind.ingestion.file_validation import FileValidator
from atlasmind.ingestion.parsers import ParserRegistry


class RealAI(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def answer(
        self,
        query: str,
        evidence: dict[str, str],
        *,
        graph_facts: tuple[str, ...],
    ) -> GroundedAnswer: ...


class RealGraphExtractor(Protocol):
    async def extract_graph(self, content: str, *, locator: str) -> GraphExtraction: ...


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    id: str
    document_version_id: str
    content: str
    locator: str
    scope_ids: frozenset[str]
    score: float


class PersistentKnowledgeService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        object_store: S3ObjectStore,
        graph: Neo4jRuntime,
        ai: RealAI,
        graph_extractor: RealGraphExtractor,
        *,
        worker_id: str = "atlasmind-real-ingestion",
        missing_ai_capabilities: tuple[str, ...] = (),
    ) -> None:
        self._sessions = session_factory
        self._objects = object_store
        self._graph = graph
        self._ai = ai
        self._graph_extractor = graph_extractor
        self._worker_id = worker_id
        self._missing_ai_capabilities = missing_ai_capabilities
        self._validator = FileValidator()
        self._parsers = ParserRegistry()
        self._chunker = DeterministicChunker()

    def _require_ai_capabilities(self) -> None:
        if self._missing_ai_capabilities:
            raise ModelCapabilityUnavailable(
                details={"missingCapabilities": list(self._missing_ai_capabilities)}
            )

    async def upload(
        self,
        *,
        title: str,
        source_key: str,
        file_name: str,
        media_type: str,
        content: bytes,
        scope_ids: frozenset[str],
        metadata: Mapping[str, object],
        actor_id: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        self._require_ai_capabilities()
        if not title.strip() or not source_key.strip() or not scope_ids:
            raise ValueError("title, source key and scopes are required")
        validated = self._validator.validate(file_name, media_type, content)
        actor_uuid = UUID(actor_id)
        scope_uuids = [UUID(value) for value in sorted(scope_ids)]

        async with self._sessions() as session, session.begin():
            prior = (
                (
                    await session.execute(
                        text(
                            """
                        SELECT job.id AS job_id, job.state, job.current_stage, job.attempt,
                               job.failure_code, job.created_at, job.finished_at,
                               version.id AS version_id, document.id AS document_id,
                               document.title, document.source_key, document.status,
                               document.active_version_id, document.scope_ids, document.created_at AS document_created_at
                          FROM ingestion_jobs job
                          JOIN document_versions version ON version.id = job.document_version_id
                          JOIN knowledge_documents document ON document.id = version.document_id
                         WHERE job.idempotency_key = :key
                        """
                        ),
                        {"key": idempotency_key},
                    )
                )
                .mappings()
                .first()
            )
            if prior is not None:
                return self._accepted_from_row(prior)
            existing = (
                await session.execute(
                    text("SELECT id FROM knowledge_documents WHERE source_key = :source_key"),
                    {"source_key": source_key},
                )
            ).scalar_one_or_none()
            if existing is not None:
                raise InvalidState(details={"reason": "SOURCE_KEY_EXISTS"})

        await self._objects.ensure_bucket()
        try:
            await self._objects.put_immutable(
                validated.object_key,
                BytesIO(content),
                size_bytes=validated.size_bytes,
            )
        except InvalidState as exc:
            if exc.details.get("reason") != "OBJECT_ALREADY_EXISTS":
                raise

        document_id = uuid4()
        version_id = uuid4()
        job_id = uuid4()
        intent_id = uuid4()
        now = utc_now()
        async with self._sessions() as session, session.begin():
            await session.execute(
                text(
                    """
                    INSERT INTO knowledge_documents
                        (id, title, source_key, owner_principal_id, scope_ids, status,
                         active, created_at, updated_at)
                    VALUES (:id, :title, :source_key, :owner, :scopes, 'ACTIVE', true, :now, :now)
                    """
                ),
                {
                    "id": document_id,
                    "title": title.strip(),
                    "source_key": source_key.strip(),
                    "owner": actor_uuid,
                    "scopes": scope_uuids,
                    "now": now,
                },
            )
            await session.execute(
                text(
                    """
                    INSERT INTO document_versions
                        (id, document_id, content_digest, scope_ids, searchable, generation,
                         created_at, version_label, object_key, media_type, size_bytes,
                         metadata_schema_version, lifecycle_state)
                    VALUES (:id, :document_id, :digest, :scopes, false, 1, :now, 'v1',
                            :object_key, :media_type, :size_bytes, 1, 'UPLOADED')
                    """
                ),
                {
                    "id": version_id,
                    "document_id": document_id,
                    "digest": validated.content_digest,
                    "scopes": scope_uuids,
                    "now": now,
                    "object_key": validated.object_key,
                    "media_type": validated.media_type,
                    "size_bytes": validated.size_bytes,
                },
            )
            await session.execute(
                text(
                    """
                    INSERT INTO ingestion_jobs
                        (id, document_version_id, state, current_stage, attempt, max_attempts,
                         idempotency_key, created_at)
                    VALUES (:id, :version_id, 'QUEUED', 'VALIDATING', 0, 5, :key, :now)
                    """
                ),
                {"id": job_id, "version_id": version_id, "key": idempotency_key, "now": now},
            )
            await session.execute(
                text(
                    """
                    INSERT INTO object_write_intents
                        (id, document_version_id, object_key, content_digest, size_bytes, state, created_at)
                    VALUES (:id, :version_id, :object_key, :digest, :size_bytes, 'COMMITTED', :now)
                    """
                ),
                {
                    "id": intent_id,
                    "version_id": version_id,
                    "object_key": validated.object_key,
                    "digest": validated.content_digest,
                    "size_bytes": validated.size_bytes,
                    "now": now,
                },
            )
            for key, value in metadata.items():
                if value is None:
                    continue
                await session.execute(
                    text(
                        """
                        INSERT INTO document_metadata
                            (document_version_id, key, value, origin, review_status)
                        VALUES (:version_id, :key, CAST(:value AS jsonb), 'USER', 'CONFIRMED')
                        ON CONFLICT (document_version_id, key)
                        DO UPDATE SET value = EXCLUDED.value, review_status = 'CONFIRMED'
                        """
                    ),
                    {"version_id": version_id, "key": str(key), "value": json.dumps(value)},
                )
        return {
            "document": {
                "id": str(document_id),
                "title": title.strip(),
                "sourceKey": source_key.strip(),
                "status": "ACTIVE",
                "activeVersionId": None,
                "knowledgeScopes": sorted(scope_ids),
                "createdAt": now.isoformat(),
            },
            "versionId": str(version_id),
            "ingestionJob": self._job_dict(
                job_id, version_id, "QUEUED", "VALIDATING", 0, None, now, None
            ),
        }

    async def process_next(self) -> dict[str, object] | None:
        if self._missing_ai_capabilities:
            return None
        claimed = await self._claim_next()
        if claimed is None:
            return None
        try:
            return await self._process_claimed(claimed)
        except Exception as exc:
            code = getattr(exc, "reason", exc.__class__.__name__.upper())
            async with self._sessions() as session, session.begin():
                await session.execute(
                    text(
                        """
                        UPDATE ingestion_jobs
                           SET state = 'FAILED', failure_code = :code, finished_at = :now,
                               lease_owner = NULL, lease_until = NULL
                         WHERE id = :id
                        """
                    ),
                    {"id": claimed["id"], "code": str(code)[:100], "now": utc_now()},
                )
                await session.execute(
                    text("UPDATE document_versions SET lifecycle_state = 'FAILED' WHERE id = :id"),
                    {"id": claimed["version_id"]},
                )
            return await self.get_job(str(claimed["id"]))

    async def _claim_next(self) -> dict[str, Any] | None:
        now = utc_now()
        async with self._sessions() as session, session.begin():
            row = (
                (
                    await session.execute(
                        text(
                            """
                        SELECT job.id, job.document_version_id AS version_id, version.document_id,
                               version.object_key, version.media_type, version.generation,
                               version.scope_ids, job.attempt, job.created_at
                          FROM ingestion_jobs job
                          JOIN document_versions version ON version.id = job.document_version_id
                         WHERE job.state = 'QUEUED'
                           AND (job.lease_until IS NULL OR job.lease_until < :now)
                         ORDER BY job.created_at
                         FOR UPDATE OF job SKIP LOCKED
                         LIMIT 1
                        """
                        ),
                        {"now": now},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            await session.execute(
                text(
                    """
                    UPDATE ingestion_jobs
                       SET state = 'RUNNING', current_stage = 'VALIDATING',
                           attempt = attempt + 1, started_at = COALESCE(started_at, :now),
                           lease_owner = :worker, lease_until = :lease_until, failure_code = NULL
                     WHERE id = :id
                    """
                ),
                {
                    "id": row["id"],
                    "now": now,
                    "worker": self._worker_id,
                    "lease_until": now + timedelta(minutes=5),
                },
            )
            return dict(row)

    async def _process_claimed(self, claimed: dict[str, Any]) -> dict[str, object]:
        version_id = str(claimed["version_id"])
        scope_ids = frozenset(map(str, claimed["scope_ids"]))
        content = await self._objects.get_bytes(str(claimed["object_key"]))
        self._validator.validate("source.bin", str(claimed["media_type"]), content)
        parsed = self._parsers.parse(str(claimed["media_type"]), content)
        chunks = self._chunker.chunk(
            parsed,
            document_version_id=version_id,
            scope_ids=scope_ids,
            generation=int(claimed["generation"]),
        )
        embeddings = await self._ai.embed([chunk.content for chunk in chunks])
        extractions = [
            await self._graph_extractor.extract_graph(chunk.content, locator=chunk.locator)
            for chunk in chunks
        ]
        entity_names = list(
            dict.fromkeys(
                entity.name for extraction in extractions for entity in extraction.entities
            )
        )
        entity_vectors = await self._ai.embed(entity_names) if entity_names else []
        entity_embeddings = dict(zip(entity_names, entity_vectors, strict=True))

        graph_records: list[GraphProjectionRecord] = []
        async with self._sessions() as session, session.begin():
            await self._set_stage(session, claimed["id"], version_id, "PARSING")
            await self._set_stage(session, claimed["id"], version_id, "CHUNKING")
            await self._set_stage(session, claimed["id"], version_id, "LEXICAL_INDEX")
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                await session.execute(
                    text(
                        """
                        INSERT INTO knowledge_chunks
                            (id, document_version_id, ordinal, content, locator, scope_ids,
                             generation, active, embedding, search_vector)
                        VALUES (:id, :version_id, :ordinal, :content, :locator, :scopes,
                                :generation, true, CAST(:embedding AS vector),
                                to_tsvector('simple', :content))
                        ON CONFLICT (document_version_id, ordinal)
                        DO UPDATE SET content = EXCLUDED.content, locator = EXCLUDED.locator,
                                      scope_ids = EXCLUDED.scope_ids,
                                      embedding = EXCLUDED.embedding,
                                      search_vector = EXCLUDED.search_vector,
                                      active = true
                        """
                    ),
                    {
                        "id": UUID(chunk.id),
                        "version_id": UUID(version_id),
                        "ordinal": chunk.ordinal,
                        "content": chunk.content,
                        "locator": chunk.locator,
                        "scopes": [UUID(value) for value in sorted(chunk.scope_ids)],
                        "generation": chunk.generation,
                        "embedding": self._vector_literal(embedding),
                    },
                )
            await self._set_stage(session, claimed["id"], version_id, "VECTOR_INDEX")
            for chunk, extraction in zip(chunks, extractions, strict=True):
                graph_records.extend(
                    await self._persist_graph(session, chunk, extraction, entity_embeddings)
                )
            await self._set_stage(session, claimed["id"], version_id, "GRAPH_INDEX")
            await self._upsert_projection(session, version_id, "LEXICAL", len(chunks))
            await self._upsert_projection(session, version_id, "VECTOR", len(chunks))
            await self._upsert_projection(session, version_id, "GRAPH", len(graph_records))
            await self._graph.project(tuple(graph_records))
            now = utc_now()
            await self._set_stage(session, claimed["id"], version_id, "ACTIVATING")
            await session.execute(
                text(
                    """
                    UPDATE document_versions
                       SET searchable = true, lifecycle_state = 'SEARCHABLE'
                     WHERE id = :version_id
                    """
                ),
                {"version_id": UUID(version_id)},
            )
            await session.execute(
                text(
                    """
                    UPDATE knowledge_documents
                       SET active_version_id = :version_id, updated_at = :now
                     WHERE id = :document_id
                    """
                ),
                {
                    "version_id": UUID(version_id),
                    "document_id": claimed["document_id"],
                    "now": now,
                },
            )
            await session.execute(
                text(
                    """
                    UPDATE ingestion_jobs
                       SET state = 'SEARCHABLE', current_stage = 'ACTIVATING', finished_at = :now,
                           lease_owner = NULL, lease_until = NULL, failure_code = NULL
                     WHERE id = :id
                    """
                ),
                {"id": claimed["id"], "now": now},
            )
        return await self.get_job(str(claimed["id"]))

    async def _persist_graph(
        self,
        session: AsyncSession,
        chunk: IngestedChunk,
        extraction: GraphExtraction,
        entity_embeddings: dict[str, list[float]],
    ) -> list[GraphProjectionRecord]:
        entity_ids: dict[str, UUID] = {}
        entity_types: dict[str, str] = {}
        for entity in extraction.entities:
            entity_id = uuid4()
            resolved = (
                await session.execute(
                    text(
                        """
                        INSERT INTO graph_entities
                            (id, canonical_name, entity_type, aliases, status)
                        VALUES (:id, :name, :type, :aliases, 'ACTIVE')
                        ON CONFLICT (canonical_name, entity_type)
                        DO UPDATE SET aliases =
                            ARRAY(SELECT DISTINCT value FROM unnest(graph_entities.aliases || EXCLUDED.aliases) value)
                        RETURNING id
                        """
                    ),
                    {
                        "id": entity_id,
                        "name": entity.name,
                        "type": entity.entity_type,
                        "aliases": list(entity.aliases),
                    },
                )
            ).scalar_one()
            entity_ids[entity.name] = resolved
            entity_types[entity.name] = entity.entity_type
            await session.execute(
                text(
                    """
                    INSERT INTO entity_mentions
                        (id, entity_id, chunk_id, document_version_id, surface, locator,
                         confidence, scope_ids, extraction_version, review_status)
                    VALUES (:id, :entity_id, :chunk_id, :version_id, :surface, :locator,
                            1, :scopes, :version, 'AUTO')
                    """
                ),
                {
                    "id": uuid4(),
                    "entity_id": resolved,
                    "chunk_id": UUID(chunk.id),
                    "version_id": UUID(chunk.document_version_id),
                    "surface": entity.name,
                    "locator": chunk.locator,
                    "scopes": [UUID(value) for value in sorted(chunk.scope_ids)],
                    "version": extraction.extraction_version,
                },
            )
        records: list[GraphProjectionRecord] = []
        for relation in extraction.relations:
            source_id = entity_ids.get(relation.source)
            target_id = entity_ids.get(relation.target)
            if source_id is None or target_id is None:
                continue
            relation_id = (
                await session.execute(
                    text(
                        """
                        INSERT INTO graph_relations
                            (id, source_entity_id, target_entity_id, relation_type,
                             confidence, status, extraction_version)
                        VALUES (:id, :source, :target, :type, :confidence, 'ACTIVE', :version)
                        ON CONFLICT (source_entity_id, target_entity_id, relation_type, extraction_version)
                        DO UPDATE SET confidence = GREATEST(graph_relations.confidence, EXCLUDED.confidence),
                                      status = 'ACTIVE'
                        RETURNING id
                        """
                    ),
                    {
                        "id": uuid4(),
                        "source": source_id,
                        "target": target_id,
                        "type": relation.relation_type,
                        "confidence": relation.confidence,
                        "version": extraction.extraction_version,
                    },
                )
            ).scalar_one()
            await session.execute(
                text(
                    """
                    INSERT INTO relation_evidence
                        (id, relation_id, chunk_id, document_version_id, locator, scope_ids, generation)
                    VALUES (:id, :relation_id, :chunk_id, :version_id, :locator, :scopes, :generation)
                    ON CONFLICT (relation_id, chunk_id) DO NOTHING
                    """
                ),
                {
                    "id": uuid4(),
                    "relation_id": relation_id,
                    "chunk_id": UUID(chunk.id),
                    "version_id": UUID(chunk.document_version_id),
                    "locator": chunk.locator,
                    "scopes": [UUID(value) for value in sorted(chunk.scope_ids)],
                    "generation": chunk.generation,
                },
            )
            records.append(
                GraphProjectionRecord(
                    relation_id=str(relation_id),
                    source_id=str(source_id),
                    source_name=relation.source,
                    source_type=entity_types[relation.source],
                    source_embedding=tuple(entity_embeddings[relation.source]),
                    target_id=str(target_id),
                    target_name=relation.target,
                    target_type=entity_types[relation.target],
                    target_embedding=tuple(entity_embeddings[relation.target]),
                    relation_type=relation.relation_type,
                    document_version_id=chunk.document_version_id,
                    chunk_id=chunk.id,
                    locator=chunk.locator,
                    scope_ids=tuple(sorted(chunk.scope_ids)),
                    generation=chunk.generation,
                    confidence=relation.confidence,
                )
            )
        return records

    async def ask(
        self,
        *,
        query: str,
        mode: str,
        principal_id: str,
        scope_ids: frozenset[str],
        authz_revision: int,
        correlation_id: str,
    ) -> dict[str, object]:
        self._require_ai_capabilities()
        if not query.strip() or not scope_ids:
            raise ValueError("query and scopes are required")
        run_id = uuid4()
        now = utc_now()
        query_digest = f"sha256:{sha256(query.encode()).hexdigest()}"
        async with self._sessions() as session, session.begin():
            await session.execute(
                text(
                    """
                    INSERT INTO agent_runs
                        (id, principal_id, correlation_id, query_digest, scope_ids, authz_revision,
                         state, created_at, task_type, budgets, usage)
                    VALUES (:id, :principal, :correlation, :digest, :scopes, :revision,
                            'RUNNING', :now, :task_type, CAST('{}' AS jsonb), CAST('{}' AS jsonb))
                    """
                ),
                {
                    "id": run_id,
                    "principal": UUID(principal_id),
                    "correlation": UUID(correlation_id),
                    "digest": query_digest,
                    "scopes": [UUID(value) for value in sorted(scope_ids)],
                    "revision": authz_revision,
                    "now": now,
                    "task_type": "GRAPH" if mode == "GRAPH" else "SIMPLE",
                },
            )
        try:
            embedding = (await self._ai.embed([query]))[0]
            chunks = await self._retrieve(query, embedding, scope_ids)
            evidence = {chunk.id: chunk.content for chunk in chunks}
            graph_facts = await self._graph.facts(
                query,
                query_embedding=embedding,
                scope_ids=scope_ids,
                document_version_ids=frozenset(chunk.document_version_id for chunk in chunks),
            )
            grounded = await self._ai.answer(query, evidence, graph_facts=graph_facts)
            result = await self._complete_run(
                run_id,
                grounded,
                chunks,
                authz_revision,
                graph_facts,
                correlation_id,
            )
            return result
        except Exception as exc:
            async with self._sessions() as session, session.begin():
                reason = f"{exc.__class__.__name__}: {exc}"[:100]
                await session.execute(
                    text(
                        """
                        UPDATE agent_runs
                           SET state = 'FAILED', degradation_reason = :reason, finished_at = :now
                         WHERE id = :id
                        """
                    ),
                    {"id": run_id, "reason": reason, "now": utc_now()},
                )
            raise

    async def _retrieve(
        self,
        query: str,
        embedding: list[float],
        scope_ids: frozenset[str],
    ) -> tuple[RetrievedChunk, ...]:
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        text(
                            """
                        SELECT chunk.id, chunk.document_version_id, chunk.content, chunk.locator,
                               chunk.scope_ids,
                               ts_rank_cd(chunk.search_vector, websearch_to_tsquery('simple', :query))
                               + GREATEST(0, 1 - (chunk.embedding <=> CAST(:embedding AS vector))) AS score
                          FROM knowledge_chunks chunk
                          JOIN document_versions version ON version.id = chunk.document_version_id
                          JOIN knowledge_documents document ON document.id = version.document_id
                         WHERE chunk.active = true
                           AND version.searchable = true
                           AND document.active = true
                           AND document.active_version_id = version.id
                           AND chunk.scope_ids && :scopes
                         ORDER BY score DESC, chunk.id
                         LIMIT 8
                        """
                        ),
                        {
                            "query": query,
                            "embedding": self._vector_literal(embedding),
                            "scopes": [UUID(value) for value in sorted(scope_ids)],
                        },
                    )
                )
                .mappings()
                .all()
            )
        return tuple(
            RetrievedChunk(
                id=str(row["id"]),
                document_version_id=str(row["document_version_id"]),
                content=str(row["content"]),
                locator=str(row["locator"]),
                scope_ids=frozenset(map(str, row["scope_ids"])),
                score=float(row["score"] or 0),
            )
            for row in rows
        )

    async def _complete_run(
        self,
        run_id: UUID,
        answer: GroundedAnswer,
        chunks: tuple[RetrievedChunk, ...],
        authz_revision: int,
        graph_facts: tuple[str, ...],
        correlation_id: str,
    ) -> dict[str, object]:
        by_id = {chunk.id: chunk for chunk in chunks}
        citation_rows: list[dict[str, object]] = []
        async with self._sessions() as session, session.begin():
            for chunk_id in answer.citation_ids:
                chunk = by_id[chunk_id]
                evidence_id = uuid4()
                citation_id = uuid4()
                await session.execute(
                    text(
                        """
                        INSERT INTO evidence_records
                            (id, run_id, source_type, source_id, source_version, locator,
                             scope_ids, content_digest, validity, authz_revision, verified_at)
                        VALUES (:id, :run_id, 'DOCUMENT', :source_id, :version, :locator,
                                :scopes, :digest, 'VALID', :revision, :now)
                        """
                    ),
                    {
                        "id": evidence_id,
                        "run_id": run_id,
                        "source_id": UUID(chunk.id),
                        "version": UUID(chunk.document_version_id),
                        "locator": chunk.locator,
                        "scopes": [UUID(value) for value in sorted(chunk.scope_ids)],
                        "digest": f"sha256:{sha256(chunk.content.encode()).hexdigest()}",
                        "revision": authz_revision,
                        "now": utc_now(),
                    },
                )
                await session.execute(
                    text(
                        """
                        INSERT INTO citations (id, run_id, evidence_id, claim, support)
                        VALUES (:id, :run_id, :evidence_id, :claim, 'SUPPORTED')
                        """
                    ),
                    {
                        "id": citation_id,
                        "run_id": run_id,
                        "evidence_id": evidence_id,
                        "claim": answer.answer,
                    },
                )
                citation_rows.append(
                    self._citation_dict(citation_id, evidence_id, chunk, answer.answer)
                )
            status = "SUFFICIENT" if citation_rows else "INSUFFICIENT"
            now = utc_now()
            await session.execute(
                text(
                    """
                    UPDATE agent_runs
                       SET state = 'COMPLETED', answer = :answer, evidence_status = :status,
                           usage = CAST(:usage AS jsonb), finished_at = :now
                     WHERE id = :id
                    """
                ),
                {
                    "id": run_id,
                    "answer": answer.answer,
                    "status": status,
                    "usage": json.dumps(
                        {"retrievedChunks": len(chunks), "graphFacts": len(graph_facts)}
                    ),
                    "now": now,
                },
            )
        return {
            "id": str(run_id),
            "correlationId": correlation_id,
            "state": "COMPLETED",
            "taskType": "GRAPH" if graph_facts else "SIMPLE",
            "createdAt": now.isoformat(),
            "finishedAt": now.isoformat(),
            "answer": {
                "text": answer.answer,
                "confidence": "HIGH" if len(citation_rows) > 1 else "MEDIUM",
                "evidenceStatus": status,
                "limitations": [] if citation_rows else ["INSUFFICIENT_EVIDENCE"],
                "citations": citation_rows,
            },
            "pendingApproval": None,
            "failure": None,
            "links": {"self": f"/v1/agent-runs/{run_id}", "approval": None},
        }

    async def get_job(self, job_id: str) -> dict[str, object]:
        async with self._sessions() as session:
            row = (
                (
                    await session.execute(
                        text(
                            """
                        SELECT id, document_version_id, state, current_stage, attempt,
                               failure_code, created_at, finished_at
                          FROM ingestion_jobs WHERE id = :id
                        """
                        ),
                        {"id": UUID(job_id)},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise ResourceNotAvailable()
        return self._job_dict(
            row["id"],
            row["document_version_id"],
            row["state"],
            row["current_stage"],
            row["attempt"],
            row["failure_code"],
            row["created_at"],
            row["finished_at"],
        )

    async def retry_job(self, job_id: str) -> dict[str, object]:
        self._require_ai_capabilities()
        async with self._sessions() as session, session.begin():
            retried = (
                await session.execute(
                    text(
                        """
                    UPDATE ingestion_jobs
                       SET state = 'QUEUED', current_stage = 'VALIDATING', failure_code = NULL,
                           finished_at = NULL, lease_owner = NULL, lease_until = NULL
                     WHERE id = :id AND state = 'FAILED' AND attempt < max_attempts
                    RETURNING id
                    """
                    ),
                    {"id": UUID(job_id)},
                )
            ).scalar_one_or_none()
            if retried is None:
                raise InvalidState(details={"reason": "JOB_NOT_RETRYABLE"})
        return await self.get_job(job_id)

    async def get_document(self, document_id: str, scope_ids: frozenset[str]) -> dict[str, object]:
        async with self._sessions() as session:
            row = (
                (
                    await session.execute(
                        text(
                            """
                        SELECT id, title, source_key, status, active_version_id, scope_ids, created_at
                          FROM knowledge_documents
                         WHERE id = :id AND scope_ids && :scopes
                        """
                        ),
                        {
                            "id": UUID(document_id),
                            "scopes": [UUID(value) for value in sorted(scope_ids)],
                        },
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise ResourceNotAvailable()
        return self._document_dict(row)

    async def revoke_document(
        self, document_id: str, scope_ids: frozenset[str]
    ) -> dict[str, object]:
        document = await self.get_document(document_id, scope_ids)
        version_id = document["activeVersionId"]
        async with self._sessions() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE knowledge_documents SET status = 'REVOKED', active = false, updated_at = :now WHERE id = :id"
                ),
                {"id": UUID(document_id), "now": utc_now()},
            )
            await session.execute(
                text(
                    "UPDATE document_versions SET searchable = false, lifecycle_state = 'REVOKED' WHERE document_id = :id"
                ),
                {"id": UUID(document_id)},
            )
            await session.execute(
                text(
                    "UPDATE knowledge_chunks SET active = false WHERE document_version_id IN "
                    "(SELECT id FROM document_versions WHERE document_id = :id)"
                ),
                {"id": UUID(document_id)},
            )
        if version_id:
            await self._graph.revoke_document_version(str(version_id))
        return {**document, "status": "REVOKED"}

    async def graph_conflicts(self, scope_ids: frozenset[str]) -> dict[str, object]:
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        text(
                            """
                        SELECT DISTINCT relation.id
                          FROM graph_relations relation
                          JOIN relation_evidence evidence ON evidence.relation_id = relation.id
                          JOIN document_versions version ON version.id = evidence.document_version_id
                          JOIN knowledge_documents document ON document.active_version_id = version.id
                         WHERE relation.status = 'CONFLICTED'
                           AND version.searchable = true
                           AND document.active = true
                           AND evidence.scope_ids && :scopes
                         ORDER BY relation.id
                        """
                        ),
                        {"scopes": [UUID(value) for value in sorted(scope_ids)]},
                    )
                )
                .scalars()
                .all()
            )
        return {"relations": [str(value) for value in rows]}

    async def get_run(self, run_id: str, principal_id: str) -> dict[str, object]:
        async with self._sessions() as session:
            run = (
                (
                    await session.execute(
                        text(
                            """
                        SELECT id, correlation_id, state, task_type, answer, evidence_status,
                               created_at, finished_at, degradation_reason
                          FROM agent_runs
                         WHERE id = :id AND principal_id = :principal
                        """
                        ),
                        {"id": UUID(run_id), "principal": UUID(principal_id)},
                    )
                )
                .mappings()
                .first()
            )
            if run is None:
                raise ResourceNotAvailable()
            rows = (
                (
                    await session.execute(
                        text(
                            """
                        SELECT citation.id, citation.evidence_id, citation.claim, citation.support,
                               evidence.source_type, evidence.source_id, evidence.source_version,
                               evidence.locator
                          FROM citations citation
                          JOIN evidence_records evidence ON evidence.id = citation.evidence_id
                         WHERE citation.run_id = :run_id
                         ORDER BY citation.id
                        """
                        ),
                        {"run_id": UUID(run_id)},
                    )
                )
                .mappings()
                .all()
            )
        citations = [
            {
                "id": str(row["id"]),
                "claim": row["claim"],
                "support": row["support"],
                "source": {
                    "type": row["source_type"],
                    "canonicalId": str(row["source_id"]),
                    "version": str(row["source_version"]),
                    "locator": row["locator"],
                },
            }
            for row in rows
        ]
        answer = None
        if run["answer"] is not None:
            answer = {
                "text": run["answer"],
                "confidence": "MEDIUM",
                "evidenceStatus": run["evidence_status"] or "INSUFFICIENT",
                "limitations": [],
                "citations": citations,
            }
        return {
            "id": str(run["id"]),
            "correlationId": str(run["correlation_id"]),
            "state": run["state"],
            "taskType": run["task_type"],
            "createdAt": run["created_at"].isoformat(),
            "finishedAt": run["finished_at"].isoformat() if run["finished_at"] else None,
            "answer": answer,
            "pendingApproval": None,
            "failure": (
                {"code": run["degradation_reason"], "message": "Run failed", "retryable": True}
                if run["state"] == "FAILED"
                else None
            ),
            "links": {"self": f"/v1/agent-runs/{run_id}", "approval": None},
        }

    async def cancel_run(self, run_id: str, principal_id: str) -> dict[str, object]:
        async with self._sessions() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE agent_runs SET state = 'CANCELLED', finished_at = :now "
                    "WHERE id = :id AND principal_id = :principal AND state IN ('QUEUED', 'RUNNING')"
                ),
                {"id": UUID(run_id), "principal": UUID(principal_id), "now": utc_now()},
            )
        return await self.get_run(run_id, principal_id)

    @staticmethod
    async def _set_stage(
        session: AsyncSession, job_id: object, version_id: str, stage: str
    ) -> None:
        await session.execute(
            text("UPDATE ingestion_jobs SET current_stage = :stage WHERE id = :id"),
            {"id": job_id, "stage": stage},
        )
        lifecycle = {
            "PARSING": "PARSING",
            "CHUNKING": "CHUNKING",
            "LEXICAL_INDEX": "INDEXING",
            "VECTOR_INDEX": "INDEXING",
            "GRAPH_INDEX": "INDEXING",
            "ACTIVATING": "ACTIVATING",
        }.get(stage, "VALIDATING")
        await session.execute(
            text("UPDATE document_versions SET lifecycle_state = :state WHERE id = :id"),
            {"id": UUID(version_id), "state": lifecycle},
        )

    @staticmethod
    async def _upsert_projection(
        session: AsyncSession, version_id: str, kind: str, count: int
    ) -> None:
        await session.execute(
            text(
                """
                INSERT INTO knowledge_projections
                    (id, document_version_id, projection_type, generation, adapter_version,
                     state, record_count, updated_at)
                VALUES (:id, :version_id, :kind, 1, 'real-mvp-v1', 'READY', :count, :now)
                ON CONFLICT (document_version_id, projection_type, generation)
                DO UPDATE SET state = 'READY', record_count = EXCLUDED.record_count,
                              updated_at = EXCLUDED.updated_at, error_code = NULL
                """
            ),
            {
                "id": uuid4(),
                "version_id": UUID(version_id),
                "kind": kind,
                "count": count,
                "now": utc_now(),
            },
        )

    @staticmethod
    def _vector_literal(vector: list[float]) -> str:
        return "[" + ",".join(format(float(value), ".12g") for value in vector) + "]"

    @staticmethod
    def _job_dict(
        job_id: Any,
        version_id: Any,
        state: Any,
        stage: Any,
        attempt: Any,
        failure_code: Any,
        created_at: Any,
        finished_at: Any,
    ) -> dict[str, object]:
        return {
            "id": str(job_id),
            "documentVersionId": str(version_id),
            "state": str(state),
            "currentStage": str(stage),
            "attempt": int(attempt),
            "failure": (
                {"code": str(failure_code), "message": str(failure_code), "retryable": True}
                if failure_code
                else None
            ),
            "createdAt": created_at.isoformat(),
            "finishedAt": finished_at.isoformat() if finished_at else None,
        }

    @classmethod
    def _accepted_from_row(cls, row: Any) -> dict[str, object]:
        return {
            "document": {
                "id": str(row["document_id"]),
                "title": row["title"],
                "sourceKey": row["source_key"],
                "status": row["status"],
                "activeVersionId": (
                    str(row["active_version_id"]) if row["active_version_id"] else None
                ),
                "knowledgeScopes": list(map(str, row["scope_ids"])),
                "createdAt": row["document_created_at"].isoformat(),
            },
            "versionId": str(row["version_id"]),
            "ingestionJob": cls._job_dict(
                row["job_id"],
                row["version_id"],
                row["state"],
                row["current_stage"],
                row["attempt"],
                row["failure_code"],
                row["created_at"],
                row["finished_at"],
            ),
        }

    @staticmethod
    def _document_dict(row: Any) -> dict[str, object]:
        return {
            "id": str(row["id"]),
            "title": row["title"],
            "sourceKey": row["source_key"],
            "status": row["status"],
            "activeVersionId": str(row["active_version_id"]) if row["active_version_id"] else None,
            "knowledgeScopes": list(map(str, row["scope_ids"])),
            "createdAt": row["created_at"].isoformat(),
        }

    @staticmethod
    def _citation_dict(
        citation_id: UUID,
        evidence_id: UUID,
        chunk: RetrievedChunk,
        claim: str,
    ) -> dict[str, object]:
        del evidence_id
        return {
            "id": str(citation_id),
            "claim": claim,
            "support": "SUPPORTED",
            "source": {
                "type": "DOCUMENT",
                "canonicalId": chunk.id,
                "version": chunk.document_version_id,
                "locator": chunk.locator,
            },
        }
