"""Persistent upload, indexing, graph projection and grounded QA for the real MVP."""

# ruff: noqa: E501 -- SQL remains readable when its column lists stay intact.

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from io import BytesIO
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from atlasmind.agent.budgets import AgentBudgets
from atlasmind.agent.decisions import AgentDecision, AgentMode, AgentObservation, AgentToolSpec
from atlasmind.agent.events import AgentEventStore, AgentEventType, PersistedAgentEvent
from atlasmind.agent.langgraph_rag import (
    AgentGraphContext,
    LangGraphAgenticRAG,
)
from atlasmind.agent.models import AgentRunState, RunStep
from atlasmind.agent.state import AgentState
from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.application.agent_run_persistence import AgentRunPersistence
from atlasmind.application.rag_capabilities import AgentRAGCapabilities
from atlasmind.domain.common import (
    InvalidState,
    ModelCapabilityUnavailable,
    ResourceNotAvailable,
    utc_now,
)
from atlasmind.graph.entity_resolution import (
    ResolutionCandidate,
    choose_unambiguous_candidate,
    configured_canonical_name,
    normalize_entity_name,
    normalized_entity_names,
)
from atlasmind.graph.policy import (
    DEFAULT_ENTITY_TYPES,
    DEFAULT_RELATION_TYPES,
    GraphPolicy,
    default_graph_policy,
)
from atlasmind.identity.models import Action, AuthorizationSnapshot
from atlasmind.infrastructure.ai_ports import RankedText
from atlasmind.infrastructure.neo4j_runtime import (
    GraphProjectionRecord,
    Neo4jRuntime,
    RetrievedGraphPath,
)
from atlasmind.infrastructure.object_store import S3ObjectStore
from atlasmind.infrastructure.openai_compatible import (
    ExtractedEntity,
    GraphExtraction,
    GroundedAnswer,
)
from atlasmind.ingestion.chunking import DeterministicChunker, IngestedChunk
from atlasmind.ingestion.file_validation import FileValidator
from atlasmind.ingestion.parsers import ParserRegistry
from atlasmind.observability.audit import AuditEvent
from atlasmind.retrieval.strategy_policy import AdvancedRetrievalPolicy
from atlasmind.tools.contracts import (
    CapabilityDescriptor,
    CapabilityKind,
    RiskLevel,
)
from atlasmind.tools.execution_gateway import CapabilityRegistry, ExecutionGateway
from atlasmind.tools.sql_query import StructuredDataset

logger = logging.getLogger(__name__)


class RealAI(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def rerank(
        self,
        query: str,
        texts: dict[str, str],
        *,
        limit: int,
    ) -> list[RankedText]: ...

    async def complete_json(
        self,
        prompt: str,
        *,
        max_tokens: int = 1_200,
    ) -> dict[str, object]: ...

    async def decide_agent_action(
        self,
        query: str,
        tools: Sequence[AgentToolSpec],
        observations: Sequence[AgentObservation],
        *,
        remaining_steps: int,
        remaining_tools: int,
    ) -> AgentDecision: ...

    async def answer(
        self,
        query: str,
        evidence: dict[str, str],
        *,
        graph_facts: tuple[str, ...] = (),
    ) -> GroundedAnswer: ...


class RealGraphExtractor(Protocol):
    async def extract_graph(self, content: str, *, locator: str) -> GraphExtraction: ...


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    id: str
    document_version_id: str
    document_title: str
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
        structured_datasets: tuple[StructuredDataset, ...] = (),
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
        self._agent_graph = LangGraphAgenticRAG()
        self._rag_capabilities = AgentRAGCapabilities(
            session_factory,
            ai,
            graph,
            structured_datasets=structured_datasets,
        )
        registry = CapabilityRegistry()
        self._register_capabilities(registry)
        self._agent_persistence = AgentRunPersistence(session_factory, self._append_audit)
        self._agent_events = AgentEventStore(session_factory)
        self._agent_tasks: dict[str, asyncio.Task[None]] = {}
        self._gateway = ExecutionGateway(
            registry,
            self._agent_persistence.audit_capability,
        )

    async def close(self) -> None:
        active = tuple(self._agent_tasks.items())
        tasks = tuple(task for _, task in active)
        for run_id, task in active:
            interrupted = await self._mark_run_interrupted(run_id)
            if interrupted:
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _mark_run_interrupted(self, run_id: str) -> bool:
        async with self._sessions() as session, session.begin():
            row = (
                (
                    await session.execute(
                        text(
                            """
                        UPDATE agent_runs
                        SET state = 'FAILED', degradation_reason = 'AGENT_SHUTDOWN',
                            finished_at = :now
                        WHERE id = :id AND state IN ('QUEUED', 'RUNNING')
                        RETURNING correlation_id, trace_id
                        """
                        ),
                        {"id": UUID(run_id), "now": utc_now()},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return False
        await self._agent_events.append(
            run_id=run_id,
            event_type=AgentEventType.RUN_ERROR,
            correlation_id=str(row["correlation_id"]),
            trace_id=str(row["trace_id"]) if row["trace_id"] else None,
            data={
                "message": "Agent 服务已停止。本次运行未完成。",
                "code": "AGENT_SHUTDOWN",
            },
        )
        return True

    def _register_capabilities(self, registry: CapabilityRegistry) -> None:
        def descriptor(name: str, kind: CapabilityKind) -> CapabilityDescriptor:
            return CapabilityDescriptor(
                name=name,
                version="1",
                kind=kind,
                required_actions=frozenset({Action.READ, Action.CITE}),
                risk_level=RiskLevel.LOW,
                side_effect=False,
                timeout_ms=8_000,
                max_result_bytes=500_000,
                max_items=40,
            )

        registry.register(
            descriptor("knowledge_search", CapabilityKind.RETRIEVAL),
            self._rag_capabilities.knowledge_search,
        )
        if any(item.name == "query_structured_data" for item in self._rag_capabilities.tool_specs):
            registry.register(
                descriptor("query_structured_data", CapabilityKind.STRUCTURED_QUERY),
                self._rag_capabilities.query_structured_data,
            )

    def _tools_for_mode(self, mode: str) -> tuple[AgentToolSpec, ...]:
        tools = self._rag_capabilities.tool_specs
        if mode == "SIMPLE":
            return tuple(item for item in tools if item.name == "knowledge_search")
        if mode == "GRAPH":
            return tuple(item for item in tools if item.name == "knowledge_search")
        return tools

    def _require_ai_capabilities(self) -> None:
        if self._missing_ai_capabilities:
            raise ModelCapabilityUnavailable(
                details={"missingCapabilities": list(self._missing_ai_capabilities)}
            )

    async def get_graph_policy(self) -> GraphPolicy:
        async with self._sessions() as session:
            row = (
                (
                    await session.execute(
                        text(
                            """
                            SELECT version, configuration
                              FROM retrieval_policies
                             WHERE name = 'graph-assist' AND active = true
                             ORDER BY version DESC
                             LIMIT 1
                            """
                        )
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return default_graph_policy()
        return GraphPolicy.model_validate(
            {"version": int(row["version"]), **dict(row["configuration"])}
        )

    async def update_graph_policy(
        self,
        configuration: Mapping[str, object],
        *,
        context: AuthContext,
    ) -> GraphPolicy:
        if Action.MANAGE not in context.allowed_actions:
            raise ResourceNotAvailable()
        raw_entities = configuration.get("allowed_entity_types", ())
        raw_relations = configuration.get("allowed_relation_types", ())
        if not isinstance(raw_entities, (list, tuple, set, frozenset)) or not isinstance(
            raw_relations, (list, tuple, set, frozenset)
        ):
            raise ValueError("graph policy allowlists must be collections")
        requested_entities = frozenset(str(value).strip().upper() for value in raw_entities)
        requested_relations = frozenset(str(value).strip().upper() for value in raw_relations)
        if not requested_entities.issubset(DEFAULT_ENTITY_TYPES):
            raise ValueError("graph policy contains unsupported entity types")
        if not requested_relations.issubset(DEFAULT_RELATION_TYPES):
            raise ValueError("graph policy contains unsupported relation types")

        async with self._sessions() as session, session.begin():
            await session.execute(text("SELECT pg_advisory_xact_lock(hashtext('graph-assist'))"))
            current_version = (
                await session.execute(
                    text(
                        """
                        SELECT version
                          FROM retrieval_policies
                         WHERE name = 'graph-assist'
                         ORDER BY version DESC
                         LIMIT 1
                         FOR UPDATE
                        """
                    )
                )
            ).scalar_one_or_none()
            version = int(current_version or 0) + 1
            policy = GraphPolicy.model_validate({"version": version, **dict(configuration)})
            policy_id = uuid4()
            await session.execute(
                text("UPDATE retrieval_policies SET active = false WHERE name = 'graph-assist'")
            )
            await session.execute(
                text(
                    """
                    INSERT INTO retrieval_policies (id, name, version, configuration, active)
                    VALUES (:id, 'graph-assist', :version, CAST(:configuration AS jsonb), true)
                    """
                ),
                {
                    "id": policy_id,
                    "version": version,
                    "configuration": json.dumps(policy.as_configuration()),
                },
            )
            await self._append_audit(
                session,
                event_type="GRAPH_POLICY_UPDATED",
                actor_id=context.principal_id,
                correlation_id=context.correlation_id,
                resource_type="RETRIEVAL_POLICY",
                resource_id=str(policy_id),
                decision="ALLOWED",
                reason_code="KNOWLEDGE_MANAGE",
                payload={"version": version},
            )
        return policy

    async def get_rag_policy(self) -> AdvancedRetrievalPolicy:
        return await self._rag_capabilities.active_retrieval_policy()

    async def get_rag_strategy_catalog(self) -> dict[str, object]:
        policy = await self.get_rag_policy()
        return {
            "policyVersion": policy.version,
            "strategies": self._rag_capabilities.retrieval_workflow.registry.catalog(policy),
        }

    async def update_rag_policy(
        self,
        configuration: Mapping[str, object],
        *,
        context: AuthContext,
    ) -> AdvancedRetrievalPolicy:
        if Action.MANAGE not in context.allowed_actions:
            raise ResourceNotAvailable()
        async with self._sessions() as session, session.begin():
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext('knowledge-search'))")
            )
            current_version = (
                await session.execute(
                    text(
                        """
                        SELECT version
                          FROM retrieval_policies
                         WHERE name = 'knowledge-search'
                         ORDER BY version DESC
                         LIMIT 1
                         FOR UPDATE
                        """
                    )
                )
            ).scalar_one_or_none()
            version = int(current_version or 0) + 1
            policy = AdvancedRetrievalPolicy.model_validate(
                {"version": version, **dict(configuration)}
            )
            self._rag_capabilities.retrieval_workflow.registry.validate_policy(policy)
            await session.execute(
                text("UPDATE retrieval_policies SET active = false WHERE name = 'knowledge-search'")
            )
            await session.execute(
                text(
                    """
                    INSERT INTO retrieval_policies (id, name, version, configuration, active)
                    VALUES (:id, 'knowledge-search', :version,
                            CAST(:configuration AS jsonb), true)
                    """
                ),
                {
                    "id": uuid4(),
                    "version": version,
                    "configuration": json.dumps(policy.as_configuration()),
                },
            )
            await self._append_audit(
                session,
                event_type="RAG_POLICY_UPDATED",
                actor_id=context.principal_id,
                correlation_id=context.correlation_id,
                resource_type="RETRIEVAL_POLICY",
                resource_id="knowledge-search",
                decision="ALLOWED",
                reason_code="KNOWLEDGE_MANAGE",
                payload={"version": version},
            )
        return policy

    async def reconcile_graph_lifecycle(self) -> dict[str, int]:
        """Reconcile provenance activity and the disposable Neo4j projection."""

        async with self._sessions() as session, session.begin():
            active_versions = frozenset(
                map(
                    str,
                    (
                        await session.execute(
                            text(
                                """
                                SELECT version.id
                                  FROM document_versions version
                                  JOIN knowledge_documents document
                                    ON document.active_version_id = version.id
                                 WHERE document.active = true
                                   AND version.searchable = true
                                """
                            )
                        )
                    )
                    .scalars()
                    .all(),
                )
            )
            stale_versions = tuple(
                map(
                    str,
                    (
                        await session.execute(
                            text(
                                """
                                SELECT DISTINCT document_version_id
                                  FROM relation_evidence
                                 WHERE active = true
                                   AND NOT (document_version_id = ANY(:active_versions))
                                """
                            ),
                            {"active_versions": [UUID(value) for value in sorted(active_versions)]},
                        )
                    )
                    .scalars()
                    .all(),
                )
            )
            for version_id in stale_versions:
                await self._retire_graph_version(session, UUID(version_id))
        await self._graph.reconcile_active_versions(active_versions)
        return {"activeVersions": len(active_versions), "retiredVersions": len(stale_versions)}

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
        correlation_id: str | None = None,
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
            await self._append_audit(
                session,
                event_type="KNOWLEDGE_DOCUMENT_UPLOADED",
                actor_id=actor_id,
                correlation_id=correlation_id or str(uuid4()),
                resource_type="KNOWLEDGE_DOCUMENT",
                resource_id=str(document_id),
                decision="ALLOWED",
                reason_code="LOCAL_SUPER_ADMIN",
                payload={"versionId": str(version_id), "sourceKey": source_key.strip()},
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

    async def add_version(
        self,
        *,
        document_id: str,
        file_name: str,
        media_type: str,
        content: bytes,
        scope_ids: frozenset[str],
        metadata: Mapping[str, object],
        actor_id: str,
        idempotency_key: str,
        correlation_id: str,
        version_label: str | None = None,
    ) -> dict[str, object]:
        self._require_ai_capabilities()
        document = await self.get_document(document_id, scope_ids)
        validated = self._validator.validate(file_name, media_type, content)
        await self._objects.ensure_bucket()
        try:
            await self._objects.put_immutable(
                validated.object_key, BytesIO(content), size_bytes=validated.size_bytes
            )
        except InvalidState as exc:
            if exc.details.get("reason") != "OBJECT_ALREADY_EXISTS":
                raise

        now = utc_now()
        version_id = uuid4()
        job_id = uuid4()
        scope_uuids = [UUID(value) for value in sorted(scope_ids)]
        async with self._sessions() as session, session.begin():
            prior = (
                await session.execute(
                    text(
                        """
                    SELECT document_version_id FROM ingestion_jobs
                     WHERE idempotency_key = :key LIMIT 1
                    """
                    ),
                    {"key": idempotency_key},
                )
            ).scalar_one_or_none()
            if prior is not None:
                raise InvalidState(details={"reason": "IDEMPOTENCY_KEY_REUSED"})
            generation = int(
                (
                    await session.execute(
                        text(
                            "SELECT COALESCE(MAX(generation), 0) + 1 FROM document_versions WHERE document_id = :id"
                        ),
                        {"id": UUID(document_id)},
                    )
                ).scalar_one()
            )
            resolved_label = (version_label or f"v{generation}").strip()
            await session.execute(
                text(
                    """
                    INSERT INTO document_versions
                        (id, document_id, content_digest, scope_ids, searchable, generation,
                         created_at, version_label, object_key, media_type, size_bytes,
                         metadata_schema_version, lifecycle_state, created_by,
                         supersedes_version_id)
                    VALUES (:id, :document_id, :digest, :scopes, false, :generation,
                            :now, :label, :object_key, :media_type, :size_bytes, 1,
                            'UPLOADED', :actor, :supersedes)
                    """
                ),
                {
                    "id": version_id,
                    "document_id": UUID(document_id),
                    "digest": validated.content_digest,
                    "scopes": scope_uuids,
                    "generation": generation,
                    "now": now,
                    "label": resolved_label,
                    "object_key": validated.object_key,
                    "media_type": validated.media_type,
                    "size_bytes": validated.size_bytes,
                    "actor": UUID(actor_id),
                    "supersedes": (
                        UUID(str(document["activeVersionId"]))
                        if document["activeVersionId"]
                        else None
                    ),
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
                    "id": uuid4(),
                    "version_id": version_id,
                    "object_key": validated.object_key,
                    "digest": validated.content_digest,
                    "size_bytes": validated.size_bytes,
                    "now": now,
                },
            )
            for key, value in metadata.items():
                if value is not None:
                    await session.execute(
                        text(
                            """
                            INSERT INTO document_metadata
                                (document_version_id, key, value, origin, review_status)
                            VALUES (:version_id, :key, CAST(:value AS jsonb), 'USER', 'CONFIRMED')
                            """
                        ),
                        {"version_id": version_id, "key": str(key), "value": json.dumps(value)},
                    )
            await self._append_audit(
                session,
                event_type="KNOWLEDGE_DOCUMENT_VERSION_UPLOADED",
                actor_id=actor_id,
                correlation_id=correlation_id,
                resource_type="KNOWLEDGE_DOCUMENT",
                resource_id=document_id,
                decision="ALLOWED",
                reason_code="LOCAL_SUPER_ADMIN",
                payload={"versionId": str(version_id), "versionLabel": resolved_label},
            )
        refreshed = await self.get_document(document_id, scope_ids)
        return {
            "document": refreshed,
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
            logger.exception(
                "ingestion job failed",
                extra={
                    "ingestion_job_id": str(claimed["id"]),
                    "document_version_id": str(claimed["version_id"]),
                    "failure_code": str(code)[:100],
                },
            )
            async with self._sessions() as session, session.begin():
                await session.execute(
                    text(
                        """
                        UPDATE ingestion_jobs
                           SET state = 'FAILED', failure_code = :code, finished_at = :now,
                               failure_detail_ref = :detail,
                               lease_owner = NULL, lease_until = NULL
                         WHERE id = :id
                        """
                    ),
                    {
                        "id": claimed["id"],
                        "code": str(code)[:100],
                        "detail": (
                            f"error:{exc.__class__.__module__}.{exc.__class__.__name__}"
                        )[:1024],
                        "now": utc_now(),
                    },
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
                           lease_owner = :worker, lease_until = :lease_until,
                           failure_code = NULL, failure_detail_ref = NULL
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
        await self._record_stage(claimed["id"], version_id, "PARSING")
        parsed = self._parsers.parse(str(claimed["media_type"]), content)
        await self._record_stage(claimed["id"], version_id, "CHUNKING")
        chunks = self._chunker.chunk(
            parsed,
            document_version_id=version_id,
            scope_ids=scope_ids,
            generation=int(claimed["generation"]),
        )
        await self._record_stage(claimed["id"], version_id, "LEXICAL_INDEX")
        await self._record_stage(claimed["id"], version_id, "VECTOR_INDEX")
        embeddings = await self._ai.embed([chunk.content for chunk in chunks])
        graph_policy = await self.get_graph_policy()
        await self._record_stage(claimed["id"], version_id, "GRAPH_INDEX")
        extractions: list[GraphExtraction] = []
        for chunk in chunks:
            extracted = await self._graph_extractor.extract_graph(
                chunk.content, locator=chunk.locator
            )
            entities = tuple(
                entity
                for entity in extracted.entities
                if entity.entity_type in graph_policy.allowed_entity_types
                and entity.confidence >= graph_policy.minimum_entity_confidence
            )
            entity_names_in_scope = {entity.name for entity in entities}
            relations = tuple(
                relation
                for relation in extracted.relations
                if relation.relation_type in graph_policy.allowed_relation_types
                and relation.confidence >= graph_policy.minimum_relation_confidence
                and relation.source in entity_names_in_scope
                and relation.target in entity_names_in_scope
                and relation.source != relation.target
            )
            extractions.append(
                GraphExtraction(
                    entities=entities,
                    relations=relations,
                    extraction_version=extracted.extraction_version,
                )
            )
        entity_names = list(
            dict.fromkeys(
                entity.name for extraction in extractions for entity in extraction.entities
            )
        )
        entity_vectors = await self._ai.embed(entity_names) if entity_names else []
        entity_embeddings = dict(zip(entity_names, entity_vectors, strict=True))

        graph_records: list[GraphProjectionRecord] = []
        old_version_id: str | None = None
        async with self._sessions() as session, session.begin():
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
            for chunk, extraction in zip(chunks, extractions, strict=True):
                graph_records.extend(
                    await self._persist_graph(
                        session,
                        chunk,
                        extraction,
                        entity_embeddings,
                        graph_policy,
                        UUID(str(claimed["document_id"])),
                    )
                )
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
            old_version = (
                await session.execute(
                    text(
                        """
                        SELECT active_version_id
                          FROM knowledge_documents
                         WHERE id = :document_id
                         FOR UPDATE
                        """
                    ),
                    {"document_id": claimed["document_id"]},
                )
            ).scalar_one_or_none()
            if old_version is not None and str(old_version) != version_id:
                old_version_id = str(old_version)
                await self._retire_graph_version(session, UUID(old_version_id))
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
        if old_version_id is not None:
            await self._graph.revoke_document_version(old_version_id)
        return await self.get_job(str(claimed["id"]))

    @staticmethod
    async def _retire_graph_version(session: AsyncSession, version_id: UUID) -> None:
        now = utc_now()
        await session.execute(
            text(
                """
                UPDATE entity_mentions
                   SET active = false, review_status = 'RETIRED'
                 WHERE document_version_id = :version_id AND active = true
                """
            ),
            {"version_id": version_id},
        )
        await session.execute(
            text(
                """
                UPDATE relation_evidence
                   SET active = false, decision = 'RETIRED', retired_at = :now
                 WHERE document_version_id = :version_id AND active = true
                """
            ),
            {"version_id": version_id, "now": now},
        )
        await session.execute(
            text(
                """
                UPDATE graph_relations relation
                   SET status = 'RETIRED', valid_until = :now
                 WHERE NOT EXISTS (
                     SELECT 1
                       FROM relation_evidence evidence
                      WHERE evidence.relation_id = relation.id
                        AND evidence.active = true
                        AND evidence.decision = 'ELIGIBLE'
                 )
                """
            ),
            {"now": now},
        )
        await session.execute(
            text(
                """
                UPDATE graph_entities entity
                   SET status = 'RETIRED', updated_at = :now
                 WHERE entity.status = 'ACTIVE'
                   AND NOT EXISTS (
                       SELECT 1
                         FROM entity_mentions mention
                        WHERE mention.entity_id = entity.id AND mention.active = true
                   )
                """
            ),
            {"now": now},
        )

    async def _persist_graph(
        self,
        session: AsyncSession,
        chunk: IngestedChunk,
        extraction: GraphExtraction,
        entity_embeddings: dict[str, list[float]],
        policy: GraphPolicy,
        source_document_id: UUID,
    ) -> list[GraphProjectionRecord]:
        entity_ids: dict[str, UUID] = {}
        entity_types: dict[str, str] = {}
        entity_names: dict[str, str] = {}
        for entity in extraction.entities:
            resolved, canonical_name = await self._resolve_graph_entity(
                session,
                entity,
                entity_embeddings[entity.name],
                policy,
            )
            entity_ids[entity.name] = resolved
            entity_types[entity.name] = entity.entity_type
            entity_names[entity.name] = canonical_name
            await session.execute(
                text(
                    """
                    INSERT INTO entity_mentions
                        (id, entity_id, chunk_id, document_version_id, surface, locator,
                         confidence, scope_ids, extraction_version, review_status,
                         active, policy_version, source_document_id)
                    VALUES (:id, :entity_id, :chunk_id, :version_id, :surface, :locator,
                            :confidence, :scopes, :version, 'ELIGIBLE', true, :policy_version,
                            :source_document_id)
                    """
                ),
                {
                    "id": uuid4(),
                    "entity_id": resolved,
                    "chunk_id": UUID(chunk.id),
                    "version_id": UUID(chunk.document_version_id),
                    "surface": entity.name,
                    "locator": chunk.locator,
                    "confidence": entity.confidence,
                    "scopes": [UUID(value) for value in sorted(chunk.scope_ids)],
                    "version": extraction.extraction_version,
                    "policy_version": policy.version,
                    "source_document_id": source_document_id,
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
                    VALUES (:id, :source, :target, :type, :confidence, 'SUPPORTED', :version)
                    ON CONFLICT (source_entity_id, target_entity_id, relation_type)
                    DO UPDATE SET confidence = GREATEST(graph_relations.confidence, EXCLUDED.confidence),
                                  status = 'SUPPORTED',
                                  extraction_version = EXCLUDED.extraction_version
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
                        (id, relation_id, chunk_id, document_version_id, locator, scope_ids,
                         generation, confidence, extraction_version, policy_version,
                         decision, active, source_document_id)
                    VALUES (:id, :relation_id, :chunk_id, :version_id, :locator, :scopes,
                            :generation, :confidence, :extraction_version, :policy_version,
                            'ELIGIBLE', true, :source_document_id)
                    ON CONFLICT (relation_id, chunk_id) DO UPDATE
                    SET confidence = EXCLUDED.confidence,
                        extraction_version = EXCLUDED.extraction_version,
                        policy_version = EXCLUDED.policy_version,
                        decision = 'ELIGIBLE',
                        active = true,
                        retired_at = NULL
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
                    "confidence": relation.confidence,
                    "extraction_version": extraction.extraction_version,
                    "policy_version": policy.version,
                    "source_document_id": source_document_id,
                },
            )
            records.append(
                GraphProjectionRecord(
                    relation_id=str(relation_id),
                    source_id=str(source_id),
                    source_name=entity_names[relation.source],
                    source_type=entity_types[relation.source],
                    source_embedding=tuple(entity_embeddings[relation.source]),
                    target_id=str(target_id),
                    target_name=entity_names[relation.target],
                    target_type=entity_types[relation.target],
                    target_embedding=tuple(entity_embeddings[relation.target]),
                    relation_type=relation.relation_type,
                    document_version_id=chunk.document_version_id,
                    chunk_id=chunk.id,
                    locator=chunk.locator,
                    scope_ids=tuple(sorted(chunk.scope_ids)),
                    generation=chunk.generation,
                    confidence=relation.confidence,
                    extraction_version=extraction.extraction_version,
                    policy_version=policy.version,
                    source_aliases=next(
                        entity.aliases
                        for entity in extraction.entities
                        if entity.name == relation.source
                    ),
                    target_aliases=next(
                        entity.aliases
                        for entity in extraction.entities
                        if entity.name == relation.target
                    ),
                    source_document_id=str(source_document_id),
                )
            )
        return records

    async def _resolve_graph_entity(
        self,
        session: AsyncSession,
        entity: ExtractedEntity,
        embedding: list[float],
        policy: GraphPolicy,
    ) -> tuple[UUID, str]:
        """Resolve aliases across documents while preserving ambiguous entities."""

        configured_name = configured_canonical_name(
            entity.name,
            entity.aliases,
            policy.allowed_aliases,
        )
        if configured_name != entity.name:
            entity = ExtractedEntity(
                name=configured_name,
                entity_type=entity.entity_type,
                aliases=tuple(dict.fromkeys((entity.name, *entity.aliases))),
                confidence=entity.confidence,
            )
        normalized = normalize_entity_name(entity.name)
        if not normalized:
            raise ValueError("graph entity name must contain searchable characters")
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"{entity.entity_type}:{normalized}"},
        )
        candidates = (
            (
                await session.execute(
                    text(
                        """
                    SELECT id, canonical_name, aliases,
                           similarity(normalized_name, :normalized) AS lexical_score,
                           CASE
                             WHEN embedding IS NOT NULL
                              AND vector_dims(embedding) = vector_dims(CAST(:embedding AS vector))
                             THEN GREATEST(0, 1 - (embedding <=> CAST(:embedding AS vector)))
                             ELSE 0
                           END AS semantic_score
                    FROM graph_entities
                    WHERE entity_type = :type AND status IN ('ACTIVE', 'RETIRED')
                    ORDER BY GREATEST(
                        similarity(normalized_name, :normalized),
                        CASE
                          WHEN embedding IS NOT NULL
                           AND vector_dims(embedding) = vector_dims(CAST(:embedding AS vector))
                          THEN GREATEST(0, 1 - (embedding <=> CAST(:embedding AS vector)))
                          ELSE 0
                        END
                    ) DESC, id
                    LIMIT 20
                    FOR UPDATE
                    """
                    ),
                    {
                        "type": entity.entity_type,
                        "normalized": normalized,
                        "embedding": self._vector_literal(embedding),
                    },
                )
            )
            .mappings()
            .all()
        )
        incoming_names = normalized_entity_names(entity.name, entity.aliases)
        matches = [
            row
            for row in candidates
            if incoming_names
            & normalized_entity_names(str(row["canonical_name"]), tuple(map(str, row["aliases"])))
        ]
        if len(matches) == 1:
            resolved = matches[0]
            aliases = list(
                dict.fromkeys(
                    (
                        *map(str, resolved["aliases"]),
                        entity.name,
                        *map(str, entity.aliases),
                    )
                )
            )
            await session.execute(
                text(
                    """
                    UPDATE graph_entities
                       SET aliases = :aliases,
                           embedding = CAST(:embedding AS vector),
                           status = 'ACTIVE',
                           updated_at = :now
                     WHERE id = :id
                    """
                ),
                {
                    "id": resolved["id"],
                    "aliases": aliases,
                    "embedding": self._vector_literal(embedding),
                    "now": utc_now(),
                },
            )
            return UUID(str(resolved["id"])), str(resolved["canonical_name"])

        if not matches:
            selected = choose_unambiguous_candidate(
                tuple(
                    ResolutionCandidate(
                        entity_id=str(row["id"]),
                        canonical_name=str(row["canonical_name"]),
                        aliases=tuple(map(str, row["aliases"])),
                        lexical_score=float(row["lexical_score"] or 0),
                        semantic_score=float(row["semantic_score"] or 0),
                    )
                    for row in candidates
                )
            )
            if selected is not None:
                aliases = list(dict.fromkeys((*selected.aliases, entity.name, *entity.aliases)))
                await session.execute(
                    text(
                        """
                        UPDATE graph_entities
                           SET aliases = :aliases,
                               embedding = CAST(:embedding AS vector),
                               status = 'ACTIVE',
                               updated_at = :now
                         WHERE id = :id
                        """
                    ),
                    {
                        "id": UUID(selected.entity_id),
                        "aliases": aliases,
                        "embedding": self._vector_literal(embedding),
                        "now": utc_now(),
                    },
                )
                return UUID(selected.entity_id), selected.canonical_name

        created = (
            await session.execute(
                text(
                    """
                    INSERT INTO graph_entities
                        (id, canonical_name, normalized_name, entity_type, aliases, status,
                         embedding)
                    VALUES (:id, :name, :normalized, :type, :aliases, 'ACTIVE',
                            CAST(:embedding AS vector))
                    ON CONFLICT (normalized_name, entity_type)
                    DO UPDATE SET aliases =
                        ARRAY(SELECT DISTINCT value FROM unnest(graph_entities.aliases || EXCLUDED.aliases) value),
                        status = 'ACTIVE', embedding = EXCLUDED.embedding, updated_at = now()
                    RETURNING id
                    """
                ),
                {
                    "id": uuid4(),
                    "name": entity.name,
                    "normalized": normalized,
                    "type": entity.entity_type,
                    "aliases": list(entity.aliases),
                    "embedding": self._vector_literal(embedding),
                },
            )
        ).scalar_one()
        return UUID(str(created)), entity.name

    async def ask(
        self,
        *,
        query: str,
        mode: AgentMode,
        context: AuthContext,
        trace_id: str | None = None,
        _on_created: Callable[[dict[str, object]], Awaitable[None]] | None = None,
    ) -> dict[str, object]:
        self._require_ai_capabilities()
        if not query.strip() or not context.scope_ids:
            raise ValueError("query and scopes are required")

        run_id = uuid4()
        now = utc_now()
        budgets = AgentBudgets(max_steps=12, max_tools=4, timeout_ms=60_000)
        query_digest = f"sha256:{sha256(query.encode()).hexdigest()}"
        async with self._sessions() as session, session.begin():
            await session.execute(
                text(
                    """
                    INSERT INTO agent_runs
                        (id, principal_id, correlation_id, trace_id, query_digest, scope_ids,
                         authz_revision, state, created_at, task_type, budgets, usage)
                    VALUES
                        (:id, :principal, :correlation, :trace_id, :digest, :scopes,
                         :revision, 'RUNNING', :now, 'SIMPLE',
                         CAST(:budgets AS jsonb), CAST('{}' AS jsonb))
                    """
                ),
                {
                    "id": run_id,
                    "principal": UUID(context.principal_id),
                    "correlation": UUID(context.correlation_id),
                    "trace_id": trace_id,
                    "digest": query_digest,
                    "scopes": [UUID(value) for value in sorted(context.scope_ids)],
                    "revision": context.authz_revision,
                    "now": now,
                    "budgets": json.dumps(
                        {
                            "maxSteps": budgets.max_steps,
                            "maxTools": budgets.max_tools,
                            "timeoutMs": budgets.timeout_ms,
                            "maxTokens": budgets.max_tokens,
                            "maxResultBytes": budgets.max_result_bytes,
                        }
                    ),
                },
            )
            await self._append_audit(
                session,
                event_type="AGENT_RUN_STARTED",
                actor_id=context.principal_id,
                correlation_id=context.correlation_id,
                resource_type="AGENT_RUN",
                resource_id=str(run_id),
                decision="ALLOWED",
                reason_code="AUTHORIZED_SCOPE",
                payload={"queryDigest": query_digest, "mode": mode},
            )

        await self._agent_events.append(
            run_id=str(run_id),
            event_type=AgentEventType.RUN_STARTED,
            correlation_id=context.correlation_id,
            trace_id=trace_id,
            data={"threadId": str(run_id), "runId": str(run_id)},
        )
        if _on_created is not None:
            await _on_created(await self.get_run(str(run_id), context.principal_id))

        async def write_step(step: RunStep) -> None:
            await self._agent_persistence.write_step(step)

        async def write_event(event_type: AgentEventType, data: dict[str, object]) -> None:
            await self._agent_events.append(
                run_id=str(run_id),
                event_type=event_type,
                correlation_id=context.correlation_id,
                trace_id=trace_id,
                data=data,
            )

        graph_context = AgentGraphContext(
            gateway=self._gateway,
            auth_context=context,
            authorization_snapshot=AuthorizationSnapshot(
                revision=context.authz_revision,
                active_scope_ids=context.scope_ids,
            ),
            model=self._ai,
            tools=self._tools_for_mode(mode),
            write_step=write_step,
            write_event=write_event,
            max_iterations=6,
            retrieval_mode=mode,
        )
        state = AgentState(
            run_id=str(run_id),
            query=query,
            budgets=budgets,
            state=AgentRunState.RUNNING,
        )
        try:
            result = await self._agent_graph.run(state, graph_context)
            completed = await self._agent_persistence.complete(
                run_id,
                result,
                context=context,
                trace_id=trace_id,
                created_at=now,
            )
            answer = completed.get("answer")
            if isinstance(answer, dict):
                citations = answer.get("citations")
                if isinstance(citations, list) and citations:
                    await write_event(
                        AgentEventType.CUSTOM,
                        {"name": "atlasmind.citations", "value": citations},
                    )
                graph_paths = answer.get("graphPaths")
                if isinstance(graph_paths, list) and graph_paths:
                    await write_event(
                        AgentEventType.CUSTOM,
                        {"name": "atlasmind.graph_paths", "value": graph_paths},
                    )
            await write_event(AgentEventType.STATE_SNAPSHOT, {"snapshot": completed})
            if completed["state"] in {
                AgentRunState.FAILED.value,
                AgentRunState.TIMED_OUT.value,
            }:
                await write_event(
                    AgentEventType.RUN_ERROR,
                    {
                        "message": "Agent 未能完成本次运行。",
                        "code": result.terminal_reason or str(completed["state"]),
                    },
                )
            else:
                await write_event(
                    AgentEventType.RUN_FINISHED,
                    {
                        "threadId": str(run_id),
                        "runId": str(run_id),
                        "result": {"state": completed["state"]},
                        "outcome": {"type": "success"},
                    },
                )
            return completed
        except Exception as exc:
            failed_transition = False
            async with self._sessions() as session, session.begin():
                reason = f"{exc.__class__.__name__}: {exc}"[:100]
                failed_transition = (
                    (
                        await session.execute(
                            text(
                                """
                        UPDATE agent_runs
                        SET state = 'FAILED', degradation_reason = :reason, finished_at = :now
                        WHERE id = :id AND state IN ('QUEUED', 'RUNNING')
                        RETURNING id
                                """
                            ),
                            {"id": run_id, "reason": reason, "now": utc_now()},
                        )
                    ).scalar_one_or_none()
                    is not None
                )
                if failed_transition:
                    await self._append_audit(
                        session,
                        event_type="AGENT_RUN_FAILED",
                        actor_id=context.principal_id,
                        correlation_id=context.correlation_id,
                        resource_type="AGENT_RUN",
                        resource_id=str(run_id),
                        decision="FAILED",
                        reason_code=exc.__class__.__name__.upper(),
                        payload={},
                    )
            if failed_transition:
                await write_event(
                    AgentEventType.RUN_ERROR,
                    {
                        "message": "Agent 未能完成本次运行。",
                        "code": exc.__class__.__name__.upper(),
                    },
                )
            raise

    async def start_ask(
        self,
        *,
        query: str,
        mode: AgentMode,
        context: AuthContext,
        trace_id: str | None = None,
    ) -> dict[str, object]:
        """Return an accepted run while the bounded graph continues in-process."""
        ready: asyncio.Future[dict[str, object]] = asyncio.get_running_loop().create_future()

        async def created(run: dict[str, object]) -> None:
            if not ready.done():
                ready.set_result(run)

        async def execute() -> None:
            try:
                await self.ask(
                    query=query,
                    mode=mode,
                    context=context,
                    trace_id=trace_id,
                    _on_created=created,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if not ready.done():
                    ready.set_exception(exc)

        task = asyncio.create_task(execute(), name="atlasmind-agent-run")
        initial = await ready
        run_id = str(initial["id"])
        self._agent_tasks[run_id] = task

        def discard(_task: asyncio.Task[None]) -> None:
            self._agent_tasks.pop(run_id, None)

        task.add_done_callback(discard)
        return initial

    async def list_run_events(
        self,
        run_id: str,
        principal_id: str,
        *,
        after: int,
        limit: int = 200,
    ) -> tuple[PersistedAgentEvent, ...]:
        return await self._agent_events.list_after(
            run_id=run_id,
            principal_id=principal_id,
            after=after,
            limit=limit,
        )

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
                        SELECT chunk.id, chunk.document_version_id, document.title AS document_title,
                               chunk.content, chunk.locator,
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
                           AND vector_dims(chunk.embedding) = vector_dims(CAST(:embedding AS vector))
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
                document_title=str(row["document_title"]),
                content=str(row["content"]),
                locator=str(row["locator"]),
                scope_ids=frozenset(map(str, row["scope_ids"])),
                score=float(row["score"] or 0),
            )
            for row in rows
        )

    async def _active_version_ids(self, scope_ids: frozenset[str]) -> frozenset[str]:
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        text(
                            """
                        SELECT version.id
                        FROM document_versions version
                        JOIN knowledge_documents document
                          ON document.active_version_id = version.id
                        WHERE version.searchable = true
                          AND document.active = true
                          AND version.scope_ids && :scopes
                        """
                        ),
                        {"scopes": [UUID(value) for value in sorted(scope_ids)]},
                    )
                )
                .scalars()
                .all()
            )
        return frozenset(map(str, rows))

    async def _retrieve_graph_chunks(
        self,
        paths: tuple[RetrievedGraphPath, ...],
        scope_ids: frozenset[str],
    ) -> tuple[RetrievedChunk, ...]:
        chunk_ids = tuple(dict.fromkeys(chunk_id for path in paths for chunk_id in path.chunk_ids))[
            :30
        ]
        if not chunk_ids:
            return ()
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        text(
                            """
                        SELECT chunk.id, chunk.document_version_id,
                               document.title AS document_title, chunk.content,
                               chunk.locator, chunk.scope_ids
                        FROM knowledge_chunks chunk
                        JOIN document_versions version
                          ON version.id = chunk.document_version_id
                        JOIN knowledge_documents document
                          ON document.active_version_id = version.id
                        WHERE chunk.id = ANY(:chunk_ids)
                          AND chunk.active = true
                          AND version.searchable = true
                          AND document.active = true
                          AND chunk.scope_ids && :scopes
                        """
                        ),
                        {
                            "chunk_ids": [UUID(value) for value in chunk_ids],
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
                document_title=str(row["document_title"]),
                content=str(row["content"]),
                locator=str(row["locator"]),
                scope_ids=frozenset(map(str, row["scope_ids"])),
                score=0,
            )
            for row in rows
        )

    async def _complete_run(
        self,
        run_id: UUID,
        answer: GroundedAnswer,
        chunks: tuple[RetrievedChunk, ...],
        authz_revision: int,
        graph_paths: tuple[RetrievedGraphPath, ...],
        correlation_id: str,
        principal_id: str,
        trace_id: str | None,
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
                        {
                            "retrievedChunks": len(chunks),
                            "graphFacts": len(graph_paths),
                            "graphPaths": [path.as_dict() for path in graph_paths],
                        }
                    ),
                    "now": now,
                },
            )
            await self._append_audit(
                session,
                event_type="AGENT_RUN_COMPLETED",
                actor_id=principal_id,
                correlation_id=correlation_id,
                resource_type="AGENT_RUN",
                resource_id=str(run_id),
                decision="COMPLETED",
                reason_code=status,
                payload={
                    "citationCount": len(citation_rows),
                    "retrievedChunks": len(chunks),
                    "graphFacts": len(graph_paths),
                },
            )
        return {
            "id": str(run_id),
            "correlationId": correlation_id,
            "traceId": trace_id,
            "state": "COMPLETED",
            "taskType": "GRAPH" if graph_paths else "SIMPLE",
            "createdAt": now.isoformat(),
            "finishedAt": now.isoformat(),
            "answer": {
                "text": answer.answer,
                "confidence": "HIGH" if len(citation_rows) > 1 else "MEDIUM",
                "evidenceStatus": status,
                "limitations": [] if citation_rows else ["INSUFFICIENT_EVIDENCE"],
                "citations": citation_rows,
                "graphPaths": [path.as_dict() for path in graph_paths],
            },
            "pendingApproval": None,
            "failure": None,
            "links": {"self": f"/v1/agent-runs/{run_id}", "approval": None},
        }

    async def list_documents(
        self, scope_ids: frozenset[str], *, limit: int = 100
    ) -> dict[str, object]:
        resolved_limit = max(1, min(limit, 200))
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        text(
                            """
                        SELECT id, title, source_key, status, active_version_id, scope_ids, created_at
                          FROM knowledge_documents
                         WHERE scope_ids && :scopes
                         ORDER BY created_at DESC, id DESC
                         LIMIT :limit
                        """
                        ),
                        {
                            "scopes": [UUID(value) for value in sorted(scope_ids)],
                            "limit": resolved_limit,
                        },
                    )
                )
                .mappings()
                .all()
            )
        return {"items": [self._document_dict(row) for row in rows], "total": len(rows)}

    async def list_runs(self, principal_id: str, *, limit: int = 50) -> dict[str, object]:
        resolved_limit = max(1, min(limit, 100))
        async with self._sessions() as session:
            run_ids = (
                (
                    await session.execute(
                        text(
                            """
                        SELECT id
                          FROM agent_runs
                         WHERE principal_id = :principal
                         ORDER BY created_at DESC, id DESC
                         LIMIT :limit
                        """
                        ),
                        {"principal": UUID(principal_id), "limit": resolved_limit},
                    )
                )
                .scalars()
                .all()
            )
        items = [await self.get_run(str(run_id), principal_id) for run_id in run_ids]
        return {"items": items, "total": len(items)}

    async def list_document_versions(
        self, document_id: str, scope_ids: frozenset[str]
    ) -> dict[str, object]:
        await self.get_document(document_id, scope_ids)
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        text(
                            """
                        SELECT version.id, version.version_label, version.lifecycle_state,
                               version.searchable, version.created_at, version.size_bytes,
                               job.id AS job_id, job.state AS job_state
                          FROM document_versions version
                          LEFT JOIN LATERAL (
                              SELECT id, state FROM ingestion_jobs
                               WHERE document_version_id = version.id
                               ORDER BY created_at DESC LIMIT 1
                          ) job ON true
                         WHERE version.document_id = :document_id
                         ORDER BY version.created_at DESC, version.id DESC
                        """
                        ),
                        {"document_id": UUID(document_id)},
                    )
                )
                .mappings()
                .all()
            )
        return {
            "items": [
                {
                    "id": str(row["id"]),
                    "versionLabel": row["version_label"],
                    "lifecycleState": row["lifecycle_state"],
                    "searchable": bool(row["searchable"]),
                    "sizeBytes": int(row["size_bytes"]),
                    "createdAt": row["created_at"].isoformat(),
                    "ingestionJobId": str(row["job_id"]) if row["job_id"] else None,
                    "ingestionState": row["job_state"],
                }
                for row in rows
            ],
            "total": len(rows),
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
                           failure_detail_ref = NULL,
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
        self,
        document_id: str,
        scope_ids: frozenset[str],
        *,
        actor_id: str,
        correlation_id: str,
    ) -> dict[str, object]:
        document = await self.get_document(document_id, scope_ids)
        version_ids: tuple[str, ...] = ()
        async with self._sessions() as session, session.begin():
            version_ids = tuple(
                map(
                    str,
                    (
                        await session.execute(
                            text("SELECT id FROM document_versions WHERE document_id = :id"),
                            {"id": UUID(document_id)},
                        )
                    )
                    .scalars()
                    .all(),
                )
            )
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
            for version_id in version_ids:
                await self._retire_graph_version(session, UUID(version_id))
            await self._append_audit(
                session,
                event_type="KNOWLEDGE_DOCUMENT_REVOKED",
                actor_id=actor_id,
                correlation_id=correlation_id,
                resource_type="KNOWLEDGE_DOCUMENT",
                resource_id=document_id,
                decision="ALLOWED",
                reason_code="LOCAL_SUPER_ADMIN",
                payload={"versionIds": list(version_ids)},
            )
        for version_id in version_ids:
            await self._graph.revoke_document_version(version_id)
        return {**document, "status": "REVOKED"}

    async def graph_snapshot(
        self,
        scope_ids: frozenset[str],
        *,
        limit: int = 200,
        query: str | None = None,
        entity_types: frozenset[str] | None = None,
        relation_types: frozenset[str] | None = None,
        minimum_confidence: float | None = None,
    ) -> dict[str, object]:
        resolved_limit = max(1, min(limit, 500))
        scope_values = [UUID(value) for value in sorted(scope_ids)]
        policy = await self.get_graph_policy()
        allowed_entity_types = policy.allowed_entity_types
        if entity_types is not None:
            allowed_entity_types = allowed_entity_types & entity_types
        allowed_relation_types = policy.allowed_relation_types
        if relation_types is not None:
            allowed_relation_types = allowed_relation_types & relation_types
        if not allowed_entity_types or not allowed_relation_types:
            return {
                "nodes": [],
                "edges": [],
                "mode": "GLOBAL",
                "truncated": False,
            }
        entity_confidence = max(
            policy.minimum_entity_confidence,
            minimum_confidence if minimum_confidence is not None else 0,
        )
        relation_confidence = max(
            policy.minimum_relation_confidence,
            minimum_confidence if minimum_confidence is not None else 0,
        )
        normalized_query = query.strip() if query else ""
        async with self._sessions() as session:
            node_rows = (
                (
                    await session.execute(
                        text(
                            """
                        SELECT entity.id, entity.canonical_name, entity.entity_type,
                               entity.aliases, COUNT(mention.id) AS mention_count,
                               COUNT(DISTINCT mention.document_version_id) AS document_count
                        FROM graph_entities entity
                        JOIN entity_mentions mention ON mention.entity_id = entity.id
                        JOIN document_versions version
                          ON version.id = mention.document_version_id
                        JOIN knowledge_documents document
                          ON document.active_version_id = version.id
                WHERE entity.status = 'ACTIVE'
                  AND mention.active = true
                  AND entity.entity_type = ANY(:entity_types)
                  AND mention.confidence >= :minimum_entity_confidence
                  AND (
                    :query = ''
                    OR entity.canonical_name ILIKE :query_pattern
                    OR EXISTS (
                      SELECT 1 FROM unnest(entity.aliases) alias
                      WHERE alias ILIKE :query_pattern
                    )
                  )
                  AND version.searchable = true
                          AND document.active = true
                          AND mention.scope_ids <@ :scopes
                        GROUP BY entity.id
                        ORDER BY document_count DESC, mention_count DESC,
                                 entity.canonical_name, entity.id
                        LIMIT :fetch_limit
                        """
                        ),
                        {
                            "scopes": scope_values,
                            "fetch_limit": resolved_limit + 1,
                            "entity_types": sorted(allowed_entity_types),
                            "minimum_entity_confidence": entity_confidence,
                            "query": normalized_query,
                            "query_pattern": f"%{normalized_query}%",
                        },
                    )
                )
                .mappings()
                .all()
            )
            truncated = len(node_rows) > resolved_limit
            node_rows = node_rows[:resolved_limit]
            node_ids = [row["id"] for row in node_rows]
            edge_rows: Sequence[RowMapping] = ()
            if node_ids:
                edge_rows = (
                    (
                        await session.execute(
                            text(
                                """
                            SELECT relation.id, relation.source_entity_id,
                                   relation.target_entity_id, relation.relation_type,
                                   relation.confidence, evidence.chunk_id,
                                   evidence.document_version_id, evidence.locator,
                                   document.id AS document_id, document.title AS document_title
                            FROM graph_relations relation
                            JOIN relation_evidence evidence
                              ON evidence.relation_id = relation.id
                            JOIN document_versions version
                              ON version.id = evidence.document_version_id
                            JOIN knowledge_documents document
                              ON document.active_version_id = version.id
                    WHERE relation.status = 'SUPPORTED'
                      AND evidence.active = true
                      AND evidence.decision = 'ELIGIBLE'
                      AND relation.relation_type = ANY(:relation_types)
                      AND evidence.confidence >= :minimum_relation_confidence
                              AND relation.source_entity_id = ANY(:node_ids)
                              AND relation.target_entity_id = ANY(:node_ids)
                              AND version.searchable = true
                              AND document.active = true
                              AND evidence.scope_ids <@ :scopes
                            ORDER BY relation.id, document.title, evidence.locator
                            LIMIT :edge_limit
                            """
                            ),
                            {
                                "node_ids": node_ids,
                                "scopes": scope_values,
                                "relation_types": sorted(allowed_relation_types),
                                "minimum_relation_confidence": relation_confidence,
                                "edge_limit": min(resolved_limit * 10, 2000),
                            },
                        )
                    )
                    .mappings()
                    .all()
                )

        edges: dict[str, dict[str, object]] = {}
        for row in edge_rows:
            relation_id = str(row["id"])
            edge = edges.setdefault(
                relation_id,
                {
                    "id": relation_id,
                    "source": str(row["source_entity_id"]),
                    "target": str(row["target_entity_id"]),
                    "type": str(row["relation_type"]),
                    "confidence": float(row["confidence"]),
                    "evidence": [],
                },
            )
            evidence = edge["evidence"]
            assert isinstance(evidence, list)
            evidence.append(
                {
                    "documentId": str(row["document_id"]),
                    "documentTitle": str(row["document_title"]),
                    "documentVersionId": str(row["document_version_id"]),
                    "chunkId": str(row["chunk_id"]),
                    "locator": str(row["locator"]),
                }
            )
        return {
            "nodes": [
                {
                    "id": str(row["id"]),
                    "name": str(row["canonical_name"]),
                    "type": str(row["entity_type"]),
                    "aliases": list(map(str, row["aliases"])),
                    "mentionCount": int(row["mention_count"]),
                    "documentCount": int(row["document_count"]),
                }
                for row in node_rows
            ],
            "edges": list(edges.values()),
            "mode": "GLOBAL",
            "truncated": truncated,
        }

    async def search_graph_entities(
        self,
        scope_ids: frozenset[str],
        *,
        query: str,
        entity_types: frozenset[str] | None = None,
        limit: int = 20,
    ) -> dict[str, object]:
        snapshot = await self.graph_snapshot(
            scope_ids,
            limit=max(1, min(limit, 50)),
            query=query,
            entity_types=entity_types,
        )
        return {"items": snapshot["nodes"], "truncated": snapshot["truncated"]}

    async def get_graph_entity(
        self, entity_id: str, scope_ids: frozenset[str]
    ) -> dict[str, object]:
        resolved_id = UUID(entity_id)
        scope_values = [UUID(value) for value in sorted(scope_ids)]
        policy = await self.get_graph_policy()
        async with self._sessions() as session:
            row = (
                (
                    await session.execute(
                        text(
                            """
                            SELECT entity.id, entity.canonical_name, entity.entity_type,
                                   entity.aliases, COUNT(mention.id) AS mention_count,
                                   COUNT(DISTINCT mention.document_version_id) AS document_count
                            FROM graph_entities entity
                            JOIN entity_mentions mention ON mention.entity_id = entity.id
                            JOIN document_versions version ON version.id = mention.document_version_id
                            JOIN knowledge_documents document ON document.active_version_id = version.id
                            WHERE entity.id = :entity_id
                              AND entity.status = 'ACTIVE'
                              AND entity.entity_type = ANY(:entity_types)
                              AND mention.active = true
                              AND mention.confidence >= :minimum_entity_confidence
                              AND mention.scope_ids <@ :scopes
                              AND version.searchable = true
                              AND document.active = true
                            GROUP BY entity.id
                            """
                        ),
                        {
                            "entity_id": resolved_id,
                            "entity_types": sorted(policy.allowed_entity_types),
                            "minimum_entity_confidence": policy.minimum_entity_confidence,
                            "scopes": scope_values,
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise ResourceNotAvailable()
            source_rows = (
                (
                    await session.execute(
                        text(
                            """
                            SELECT DISTINCT document.id AS document_id,
                                   document.title AS document_title,
                                   mention.document_version_id, mention.chunk_id,
                                   mention.locator, mention.surface, mention.confidence
                            FROM entity_mentions mention
                            JOIN document_versions version ON version.id = mention.document_version_id
                            JOIN knowledge_documents document ON document.active_version_id = version.id
                            WHERE mention.entity_id = :entity_id
                              AND mention.active = true
                              AND mention.confidence >= :minimum_entity_confidence
                              AND mention.scope_ids <@ :scopes
                              AND version.searchable = true
                              AND document.active = true
                            ORDER BY document.title, mention.locator
                            LIMIT 100
                            """
                        ),
                        {
                            "entity_id": resolved_id,
                            "minimum_entity_confidence": policy.minimum_entity_confidence,
                            "scopes": scope_values,
                        },
                    )
                )
                .mappings()
                .all()
            )
            degree = int(
                (
                    await session.execute(
                        text(
                            """
                            SELECT COUNT(DISTINCT relation.id)
                            FROM graph_relations relation
                            JOIN relation_evidence evidence ON evidence.relation_id = relation.id
                            JOIN document_versions version ON version.id = evidence.document_version_id
                            JOIN knowledge_documents document ON document.active_version_id = version.id
                            WHERE (relation.source_entity_id = :entity_id
                                   OR relation.target_entity_id = :entity_id)
                              AND relation.status = 'SUPPORTED'
                              AND relation.relation_type = ANY(:relation_types)
                              AND evidence.active = true
                              AND evidence.decision = 'ELIGIBLE'
                              AND evidence.confidence >= :minimum_relation_confidence
                              AND evidence.scope_ids <@ :scopes
                              AND version.searchable = true
                              AND document.active = true
                              AND EXISTS (
                                SELECT 1 FROM entity_mentions source_mention
                                JOIN document_versions source_version
                                  ON source_version.id = source_mention.document_version_id
                                JOIN knowledge_documents source_document
                                  ON source_document.active_version_id = source_version.id
                                JOIN graph_entities source_entity
                                  ON source_entity.id = source_mention.entity_id
                                WHERE source_mention.entity_id = relation.source_entity_id
                                  AND source_entity.status = 'ACTIVE'
                                  AND source_entity.entity_type = ANY(:entity_types)
                                  AND source_mention.active = true
                                  AND source_mention.confidence >= :minimum_entity_confidence
                                  AND source_mention.scope_ids <@ :scopes
                                  AND source_version.searchable = true
                                  AND source_document.active = true
                              )
                              AND EXISTS (
                                SELECT 1 FROM entity_mentions target_mention
                                JOIN document_versions target_version
                                  ON target_version.id = target_mention.document_version_id
                                JOIN knowledge_documents target_document
                                  ON target_document.active_version_id = target_version.id
                                JOIN graph_entities target_entity
                                  ON target_entity.id = target_mention.entity_id
                                WHERE target_mention.entity_id = relation.target_entity_id
                                  AND target_entity.status = 'ACTIVE'
                                  AND target_entity.entity_type = ANY(:entity_types)
                                  AND target_mention.active = true
                                  AND target_mention.confidence >= :minimum_entity_confidence
                                  AND target_mention.scope_ids <@ :scopes
                                  AND target_version.searchable = true
                                  AND target_document.active = true
                              )
                            """
                        ),
                        {
                            "entity_id": resolved_id,
                            "relation_types": sorted(policy.allowed_relation_types),
                            "minimum_relation_confidence": policy.minimum_relation_confidence,
                            "entity_types": sorted(policy.allowed_entity_types),
                            "minimum_entity_confidence": policy.minimum_entity_confidence,
                            "scopes": scope_values,
                        },
                    )
                ).scalar_one()
            )
        return {
            "id": str(row["id"]),
            "name": str(row["canonical_name"]),
            "type": str(row["entity_type"]),
            "aliases": list(map(str, row["aliases"])),
            "mentionCount": int(row["mention_count"]),
            "documentCount": int(row["document_count"]),
            "degree": degree,
            "properties": {},
            "sourceDocuments": [
                {
                    "documentId": str(source["document_id"]),
                    "documentTitle": str(source["document_title"]),
                    "documentVersionId": str(source["document_version_id"]),
                    "chunkId": str(source["chunk_id"]),
                    "locator": str(source["locator"]),
                    "surface": str(source["surface"]),
                    "confidence": float(source["confidence"]),
                }
                for source in source_rows
            ],
        }

    async def graph_neighbors(
        self,
        entity_id: str,
        scope_ids: frozenset[str],
        *,
        depth: int = 1,
        entity_types: frozenset[str] | None = None,
        relation_types: frozenset[str] | None = None,
        minimum_confidence: float | None = None,
        limit: int = 80,
    ) -> dict[str, object]:
        root_id = UUID(entity_id)
        await self.get_graph_entity(entity_id, scope_ids)
        policy = await self.get_graph_policy()
        allowed_entity_types = policy.allowed_entity_types
        if entity_types is not None:
            allowed_entity_types = allowed_entity_types & entity_types
        allowed_relation_types = policy.allowed_relation_types
        if relation_types is not None:
            allowed_relation_types = allowed_relation_types & relation_types
        if not allowed_entity_types or not allowed_relation_types:
            return {
                "nodes": [], "edges": [], "rootEntityId": entity_id,
                "depth": depth, "mode": "LOCAL", "truncated": False,
            }
        resolved_depth = max(1, min(depth, 3))
        resolved_limit = max(2, min(limit, 200))
        relation_confidence = max(
            policy.minimum_relation_confidence,
            minimum_confidence if minimum_confidence is not None else 0,
        )
        entity_confidence = max(
            policy.minimum_entity_confidence,
            minimum_confidence if minimum_confidence is not None else 0,
        )
        scope_values = [UUID(value) for value in sorted(scope_ids)]
        discovered: set[UUID] = {root_id}
        frontier: set[UUID] = {root_id}
        edge_rows: list[RowMapping] = []
        truncated = False
        async with self._sessions() as session:
            for _hop in range(resolved_depth):
                if not frontier or len(discovered) >= resolved_limit:
                    break
                rows = (
                    (
                        await session.execute(
                            text(
                                """
                                SELECT relation.id, relation.source_entity_id,
                                       relation.target_entity_id, relation.relation_type,
                                       relation.confidence, evidence.chunk_id,
                                       evidence.document_version_id, evidence.locator,
                                       document.id AS document_id,
                                       document.title AS document_title
                                FROM graph_relations relation
                                JOIN relation_evidence evidence ON evidence.relation_id = relation.id
                                JOIN document_versions version ON version.id = evidence.document_version_id
                                JOIN knowledge_documents document ON document.active_version_id = version.id
                                WHERE relation.status = 'SUPPORTED'
                                  AND relation.relation_type = ANY(:relation_types)
                                  AND evidence.active = true
                                  AND evidence.decision = 'ELIGIBLE'
                                  AND evidence.confidence >= :minimum_relation_confidence
                                  AND evidence.scope_ids <@ :scopes
                                  AND version.searchable = true
                                  AND document.active = true
                                  AND (relation.source_entity_id = ANY(:frontier)
                                       OR relation.target_entity_id = ANY(:frontier))
                                  AND EXISTS (
                                    SELECT 1 FROM graph_entities source_entity
                                    JOIN entity_mentions source_mention
                                      ON source_mention.entity_id = source_entity.id
                                    JOIN document_versions source_version
                                      ON source_version.id = source_mention.document_version_id
                                    JOIN knowledge_documents source_document
                                      ON source_document.active_version_id = source_version.id
                                    WHERE source_entity.id = relation.source_entity_id
                                      AND source_entity.status = 'ACTIVE'
                                      AND source_entity.entity_type = ANY(:entity_types)
                                      AND source_mention.active = true
                                      AND source_mention.confidence >= :minimum_entity_confidence
                                      AND source_mention.scope_ids <@ :scopes
                                      AND source_version.searchable = true
                                      AND source_document.active = true
                                  )
                                  AND EXISTS (
                                    SELECT 1 FROM graph_entities target_entity
                                    JOIN entity_mentions target_mention
                                      ON target_mention.entity_id = target_entity.id
                                    JOIN document_versions target_version
                                      ON target_version.id = target_mention.document_version_id
                                    JOIN knowledge_documents target_document
                                      ON target_document.active_version_id = target_version.id
                                    WHERE target_entity.id = relation.target_entity_id
                                      AND target_entity.status = 'ACTIVE'
                                      AND target_entity.entity_type = ANY(:entity_types)
                                      AND target_mention.active = true
                                      AND target_mention.confidence >= :minimum_entity_confidence
                                      AND target_mention.scope_ids <@ :scopes
                                      AND target_version.searchable = true
                                      AND target_document.active = true
                                  )
                                ORDER BY relation.confidence DESC, relation.id, evidence.locator
                                LIMIT :edge_limit
                                """
                            ),
                            {
                                "frontier": list(frontier),
                                "relation_types": sorted(allowed_relation_types),
                                "entity_types": sorted(allowed_entity_types),
                                "minimum_relation_confidence": relation_confidence,
                                "minimum_entity_confidence": entity_confidence,
                                "scopes": scope_values,
                                "edge_limit": resolved_limit * 20,
                            },
                        )
                    )
                    .mappings()
                    .all()
                )
                next_frontier: set[UUID] = set()
                for row in rows:
                    source_id = UUID(str(row["source_entity_id"]))
                    target_id = UUID(str(row["target_entity_id"]))
                    for candidate in (source_id, target_id):
                        if candidate not in discovered:
                            if len(discovered) >= resolved_limit:
                                truncated = True
                                continue
                            discovered.add(candidate)
                            next_frontier.add(candidate)
                    if source_id in discovered and target_id in discovered:
                        edge_rows.append(row)
                frontier = next_frontier
            node_rows = (
                (
                    await session.execute(
                        text(
                            """
                            SELECT entity.id, entity.canonical_name, entity.entity_type,
                                   entity.aliases, COUNT(mention.id) AS mention_count,
                                   COUNT(DISTINCT mention.document_version_id) AS document_count
                            FROM graph_entities entity
                            JOIN entity_mentions mention ON mention.entity_id = entity.id
                            JOIN document_versions version ON version.id = mention.document_version_id
                            JOIN knowledge_documents document ON document.active_version_id = version.id
                            WHERE entity.id = ANY(:node_ids)
                              AND entity.status = 'ACTIVE'
                              AND mention.active = true
                              AND mention.confidence >= :minimum_entity_confidence
                              AND mention.scope_ids <@ :scopes
                              AND version.searchable = true
                              AND document.active = true
                            GROUP BY entity.id
                            ORDER BY entity.canonical_name, entity.id
                            """
                        ),
                        {
                            "node_ids": list(discovered),
                            "minimum_entity_confidence": entity_confidence,
                            "scopes": scope_values,
                        },
                    )
                )
                .mappings()
                .all()
            )
        edges = self._serialize_graph_edges(edge_rows)
        return {
            "nodes": [self._serialize_graph_node(row) for row in node_rows],
            "edges": list(edges.values()),
            "rootEntityId": entity_id,
            "depth": resolved_depth,
            "mode": "LOCAL",
            "truncated": truncated,
        }

    async def get_graph_relation(
        self, relation_id: str, scope_ids: frozenset[str]
    ) -> dict[str, object]:
        resolved_id = UUID(relation_id)
        scope_values = [UUID(value) for value in sorted(scope_ids)]
        policy = await self.get_graph_policy()
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        text(
                            """
                            SELECT relation.id, relation.source_entity_id,
                                   relation.target_entity_id, relation.relation_type,
                                   relation.confidence, evidence.chunk_id,
                                   evidence.document_version_id, evidence.locator,
                                   document.id AS document_id,
                                   document.title AS document_title
                            FROM graph_relations relation
                            JOIN relation_evidence evidence ON evidence.relation_id = relation.id
                            JOIN document_versions version ON version.id = evidence.document_version_id
                            JOIN knowledge_documents document ON document.active_version_id = version.id
                            WHERE relation.id = :relation_id
                              AND relation.status = 'SUPPORTED'
                              AND relation.relation_type = ANY(:relation_types)
                              AND evidence.active = true
                              AND evidence.decision = 'ELIGIBLE'
                              AND evidence.confidence >= :minimum_relation_confidence
                              AND evidence.scope_ids <@ :scopes
                              AND version.searchable = true
                              AND document.active = true
                              AND EXISTS (
                                SELECT 1 FROM entity_mentions source_mention
                                JOIN document_versions source_version
                                  ON source_version.id = source_mention.document_version_id
                                JOIN knowledge_documents source_document
                                  ON source_document.active_version_id = source_version.id
                                JOIN graph_entities source_entity
                                  ON source_entity.id = source_mention.entity_id
                                WHERE source_mention.entity_id = relation.source_entity_id
                                  AND source_entity.status = 'ACTIVE'
                                  AND source_entity.entity_type = ANY(:entity_types)
                                  AND source_mention.active = true
                                  AND source_mention.confidence >= :minimum_entity_confidence
                                  AND source_mention.scope_ids <@ :scopes
                                  AND source_version.searchable = true
                                  AND source_document.active = true
                              )
                              AND EXISTS (
                                SELECT 1 FROM entity_mentions target_mention
                                JOIN document_versions target_version
                                  ON target_version.id = target_mention.document_version_id
                                JOIN knowledge_documents target_document
                                  ON target_document.active_version_id = target_version.id
                                JOIN graph_entities target_entity
                                  ON target_entity.id = target_mention.entity_id
                                WHERE target_mention.entity_id = relation.target_entity_id
                                  AND target_entity.status = 'ACTIVE'
                                  AND target_entity.entity_type = ANY(:entity_types)
                                  AND target_mention.active = true
                                  AND target_mention.confidence >= :minimum_entity_confidence
                                  AND target_mention.scope_ids <@ :scopes
                                  AND target_version.searchable = true
                                  AND target_document.active = true
                              )
                            ORDER BY document.title, evidence.locator
                            """
                        ),
                        {
                            "relation_id": resolved_id,
                            "relation_types": sorted(policy.allowed_relation_types),
                            "minimum_relation_confidence": policy.minimum_relation_confidence,
                            "entity_types": sorted(policy.allowed_entity_types),
                            "minimum_entity_confidence": policy.minimum_entity_confidence,
                            "scopes": scope_values,
                        },
                    )
                )
                .mappings()
                .all()
            )
        edges = self._serialize_graph_edges(rows)
        edge = edges.get(str(resolved_id))
        if edge is None:
            raise ResourceNotAvailable()
        return edge

    @staticmethod
    def _serialize_graph_node(row: RowMapping) -> dict[str, object]:
        return {
            "id": str(row["id"]),
            "name": str(row["canonical_name"]),
            "type": str(row["entity_type"]),
            "aliases": list(map(str, row["aliases"])),
            "mentionCount": int(row["mention_count"]),
            "documentCount": int(row["document_count"]),
        }

    @staticmethod
    def _serialize_graph_edges(rows: Sequence[RowMapping]) -> dict[str, dict[str, object]]:
        edges: dict[str, dict[str, object]] = {}
        for row in rows:
            relation_id = str(row["id"])
            edge = edges.setdefault(
                relation_id,
                {
                    "id": relation_id,
                    "source": str(row["source_entity_id"]),
                    "target": str(row["target_entity_id"]),
                    "type": str(row["relation_type"]),
                    "confidence": float(row["confidence"]),
                    "evidence": [],
                },
            )
            evidence = edge["evidence"]
            assert isinstance(evidence, list)
            item = {
                "documentId": str(row["document_id"]),
                "documentTitle": str(row["document_title"]),
                "documentVersionId": str(row["document_version_id"]),
                "chunkId": str(row["chunk_id"]),
                "locator": str(row["locator"]),
            }
            if item not in evidence:
                evidence.append(item)
        return edges

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
                      AND evidence.scope_ids <@ :scopes
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
                    SELECT id, correlation_id, trace_id, state, task_type, answer, evidence_status,
                           usage, created_at, finished_at, degradation_reason
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
                               evidence.source_type, evidence.locator,
                               COALESCE(
                                   evidence.source_metadata ->> 'canonicalId',
                                   evidence.source_id::text
                               ) AS canonical_source_id,
                               COALESCE(
                                   evidence.source_metadata ->> 'version',
                                   evidence.source_version::text
                               ) AS canonical_source_version,
                               COALESCE(
                                   evidence.source_title,
                                   evidence.source_metadata ->> 'canonicalId',
                                   evidence.source_id::text
                               ) AS source_title,
                               evidence.source_excerpt
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
            step_rows = (
                (
                    await session.execute(
                        text(
                            """
                            SELECT id, ordinal, kind, state, capability_name, result_ref,
                                   started_at, finished_at
                              FROM run_steps
                             WHERE run_id = :run_id
                             ORDER BY ordinal, id
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
                "claimLocator": row["claim"],
                "supportStatus": row["support"],
                "source": {
                    "type": row["source_type"],
                    "id": str(row["canonical_source_id"]),
                    "version": str(row["canonical_source_version"]),
                    "locator": row["locator"],
                    "title": str(row["source_title"]),
                    "excerpt": (
                        str(row["source_excerpt"])[:500]
                        if row["source_excerpt"] is not None
                        else None
                    ),
                },
            }
            for row in rows
        ]
        steps = [
            {
                "id": str(row["id"]),
                "ordinal": int(row["ordinal"]),
                "kind": row["kind"],
                "state": row["state"],
                "capabilityName": row["capability_name"],
                "resultRef": row["result_ref"],
                "startedAt": row["started_at"].isoformat() if row["started_at"] else None,
                "finishedAt": row["finished_at"].isoformat() if row["finished_at"] else None,
            }
            for row in step_rows
        ]
        answer = None
        if run["answer"] is not None:
            answer = {
                "text": run["answer"],
                "confidence": "MEDIUM",
                "evidenceStatus": run["evidence_status"] or "INSUFFICIENT",
                "limitations": [],
                "citations": citations,
                "graphPaths": list((run["usage"] or {}).get("graphPaths", ())),
            }
        budget_reasons = {
            "AGENT_TIMEOUT",
            "STEP_BUDGET_EXCEEDED",
            "TOOL_BUDGET_EXCEEDED",
        }
        return {
            "id": str(run["id"]),
            "correlationId": str(run["correlation_id"]),
            "traceId": run["trace_id"],
            "state": run["state"],
            "taskType": run["task_type"],
            "createdAt": run["created_at"].isoformat(),
            "finishedAt": run["finished_at"].isoformat() if run["finished_at"] else None,
            "answer": answer,
            "pendingApproval": None,
            "failure": (
                {
                    "code": (
                        "BUDGET_EXCEEDED"
                        if run["degradation_reason"] in budget_reasons
                        else "INTERNAL_ERROR"
                    ),
                    "message": "Run failed",
                    "retryable": run["degradation_reason"] == "AGENT_TIMEOUT",
                }
                if run["state"] in {"FAILED", "TIMED_OUT"}
                else None
            ),
            "steps": steps,
            "links": {"self": f"/v1/agent-runs/{run_id}", "approval": None},
        }

    async def cancel_run(self, run_id: str, principal_id: str) -> dict[str, object]:
        async with self._sessions() as session, session.begin():
            update = await session.execute(
                text(
                    "UPDATE agent_runs SET state = 'CANCELLED', finished_at = :now "
                    "WHERE id = :id AND principal_id = :principal "
                    "AND state IN ('QUEUED', 'RUNNING')"
                ),
                {"id": UUID(run_id), "principal": UUID(principal_id), "now": utc_now()},
            )
            cancelled = getattr(update, "rowcount", 0) > 0
        run = await self.get_run(run_id, principal_id)
        task = self._agent_tasks.get(run_id)
        if cancelled and task is not None and not task.done():
            task.cancel()
        if cancelled:
            await self._agent_events.append(
                run_id=run_id,
                event_type=AgentEventType.RUN_FINISHED,
                correlation_id=str(run["correlationId"]),
                trace_id=str(run["traceId"]) if run.get("traceId") else None,
                data={
                    "threadId": run_id,
                    "runId": run_id,
                    "result": {"state": AgentRunState.CANCELLED.value},
                    "outcome": {"type": "success"},
                },
            )
        return run

    @staticmethod
    async def _append_audit(
        session: AsyncSession,
        *,
        event_type: str,
        actor_id: str,
        correlation_id: str,
        resource_type: str,
        resource_id: str,
        decision: str,
        reason_code: str,
        payload: dict[str, object],
    ) -> None:
        previous_hash = (
            await session.execute(
                text(
                    """
                    SELECT event_hash FROM audit_events
                     ORDER BY occurred_at DESC, id DESC
                     LIMIT 1
                    """
                )
            )
        ).scalar_one_or_none() or "sha256:genesis"
        event = AuditEvent(
            event_type=event_type,
            actor_principal_id=actor_id,
            correlation_id=correlation_id,
            decision=decision,
            reason_code=reason_code,
            resource_type=resource_type,
            resource_id=resource_id,
            payload=payload,
            previous_hash=str(previous_hash),
        )
        await session.execute(
            text(
                """
                INSERT INTO audit_events
                    (id, event_type, occurred_at, actor_principal_id, correlation_id,
                     resource_type, resource_id, decision, reason_code, payload,
                     previous_hash, event_hash, classification)
                VALUES (:id, :event_type, :occurred_at, :actor, :correlation,
                        :resource_type, :resource_id, :decision, :reason_code,
                        CAST(:payload AS jsonb), :previous_hash, :event_hash, :classification)
                """
            ),
            {
                "id": UUID(event.event_id),
                "event_type": event.event_type,
                "occurred_at": event.occurred_at,
                "actor": UUID(event.actor_principal_id),
                "correlation": UUID(event.correlation_id),
                "resource_type": event.resource_type,
                "resource_id": UUID(event.resource_id),
                "decision": event.decision,
                "reason_code": event.reason_code,
                "payload": json.dumps(event.payload, sort_keys=True),
                "previous_hash": event.previous_hash,
                "event_hash": event.event_hash,
                "classification": event.classification,
            },
        )

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

    async def _record_stage(self, job_id: object, version_id: str, stage: str) -> None:
        """Commit observable stage progress before executing the next expensive operation."""

        async with self._sessions() as session, session.begin():
            await self._set_stage(session, job_id, version_id, stage)

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
            "claimLocator": claim,
            "supportStatus": "SUPPORTED",
            "source": {
                "type": "DOCUMENT",
                "id": chunk.id,
                "version": chunk.document_version_id,
                "locator": chunk.locator,
                "title": chunk.document_title,
                "excerpt": chunk.content[:500],
            },
        }
