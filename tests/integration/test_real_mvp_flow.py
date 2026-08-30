"""Real PostgreSQL, MinIO and Neo4j MVP flow.

Run with ``ATLASMIND_RUN_REAL_MVP=1`` after starting the Compose dependencies.
The deterministic AI boundary keeps the test repeatable while every knowledge artifact is real.
"""

# ruff: noqa: E501, RUF001 -- SQL and Chinese fixture content stay readable inline.

from __future__ import annotations

import asyncio
import os
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from atlasmind.agent.decisions import AgentDecision, AgentObservation, AgentToolSpec
from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.identity.models import Action
from atlasmind.infrastructure.ai_ports import RankedText
from atlasmind.infrastructure.openai_compatible import (
    ExtractedEntity,
    ExtractedRelation,
    GraphExtraction,
    GroundedAnswer,
)
from atlasmind.runtime import LOCAL_PRINCIPAL_ID, LOCAL_SCOPE_ID, create_runtime
from atlasmind.settings import Settings

pytestmark = pytest.mark.skipif(
    os.getenv("ATLASMIND_RUN_REAL_MVP") != "1",
    reason="real MVP dependencies were not requested",
)


def auth_context(correlation_id: str) -> AuthContext:
    now = datetime.now(UTC)
    return AuthContext(
        principal_id=LOCAL_PRINCIPAL_ID,
        role_codes=frozenset({"local-super-admin"}),
        scope_ids=frozenset({LOCAL_SCOPE_ID}),
        allowed_actions=frozenset(Action),
        authz_revision=1,
        policy_revision=1,
        correlation_id=correlation_id,
        issued_at=now,
        expires_at=now + timedelta(hours=8),
    )


class RepeatableAI:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [
            [
                float("PostgreSQL" in text or "Postgres" in text),
                float("AtlasMind" in text),
                float("Platform Team" in text),
            ]
            for text in texts
        ]

    async def rerank(
        self,
        query: str,
        texts: dict[str, str],
        *,
        limit: int,
    ) -> list[RankedText]:
        del query
        return [
            RankedText(identifier, 1.0 - index / 100) for index, identifier in enumerate(texts)
        ][:limit]

    async def decide_agent_action(
        self,
        query: str,
        tools: Sequence[AgentToolSpec],
        observations: Sequence[AgentObservation],
        *,
        remaining_steps: int,
        remaining_tools: int,
    ) -> AgentDecision:
        del remaining_steps, remaining_tools
        available = {tool.name for tool in tools}
        assert "knowledge_search" in available
        assert "search_graph" not in available
        if not observations:
            return AgentDecision(
                action="CALL_TOOL",
                tool="knowledge_search",
                arguments={"query": query},
                reason_code="TEST_DOCUMENT_FIRST",
            )
        return AgentDecision(action="ANSWER", reason_code="TEST_EVIDENCE_SUFFICIENT")

    async def extract_graph(self, content: str, *, locator: str) -> GraphExtraction:
        del locator
        if "Postgres" in content and "Platform Team" in content:
            return GraphExtraction(
                entities=(
                    ExtractedEntity(
                        name="Postgres",
                        entity_type="SYSTEM",
                        aliases=("PostgreSQL",),
                        confidence=0.99,
                    ),
                    ExtractedEntity(
                        name="Platform Team",
                        entity_type="ORG_UNIT",
                        aliases=(),
                        confidence=0.99,
                    ),
                ),
                relations=(
                    ExtractedRelation(
                        source="Postgres",
                        target="Platform Team",
                        relation_type="OWNED_BY",
                        confidence=0.98,
                    ),
                ),
                extraction_version="test-v1",
            )
        if "AtlasMind" not in content or "PostgreSQL" not in content:
            return GraphExtraction(entities=(), relations=(), extraction_version="test-v1")
        return GraphExtraction(
            entities=(
                ExtractedEntity(
                    name="AtlasMind", entity_type="PRODUCT", aliases=(), confidence=0.99
                ),
                ExtractedEntity(
                    name="PostgreSQL", entity_type="SYSTEM", aliases=(), confidence=0.99
                ),
            ),
            relations=(
                ExtractedRelation(
                    source="AtlasMind",
                    target="PostgreSQL",
                    relation_type="USES",
                    confidence=0.99,
                ),
            ),
            extraction_version="test-v1",
        )

    async def answer(
        self,
        query: str,
        evidence: dict[str, str],
        *,
        graph_facts: tuple[str, ...] = (),
    ) -> GroundedAnswer:
        del query
        if not evidence:
            return GroundedAnswer(
                answer="当前授权范围内没有可用证据。",
                citation_ids=(),
            )
        del graph_facts
        citation_id = next(iter(evidence))
        return GroundedAnswer(
            answer="AtlasMind 使用 PostgreSQL 保存规范知识状态。",
            citation_ids=(citation_id,),
        )


def test_uploaded_document_builds_graph_and_answers_after_runtime_restart() -> None:
    asyncio.run(_real_mvp_flow())


async def _real_mvp_flow() -> None:
    try:
        settings = Settings()
        runtime = create_runtime(settings, ai=RepeatableAI())
    except Exception as exc:  # pragma: no cover - concise dependency diagnostics
        pytest.fail(f"setup failed: {type(exc).__name__}: {exc}", pytrace=False)
    source_key = f"real-mvp/{uuid4()}"
    source_content = (
        "# 架构\n\nAtlasMind 使用 PostgreSQL 保存规范知识状态，并将实体关系投影到 "
        f"Neo4j。\n\n测试来源：{source_key}"
    ).encode()
    query = f"AtlasMind 使用什么保存规范知识状态？测试来源 {source_key}"

    try:
        accepted = await runtime.knowledge.upload(
            title="AtlasMind 架构说明",
            source_key=source_key,
            file_name="architecture.md",
            media_type="text/markdown",
            content=source_content,
            scope_ids=frozenset({LOCAL_SCOPE_ID}),
            metadata={"businessOwner": "local-admin", "classification": "INTERNAL"},
            actor_id=LOCAL_PRINCIPAL_ID,
            idempotency_key=str(uuid4()),
        )
    except Exception as exc:  # pragma: no cover - diagnostic remains concise on service failure
        pytest.fail(f"upload failed: {type(exc).__name__}: {exc}", pytrace=False)
    try:
        processed = await runtime.knowledge.process_next()
    except Exception as exc:  # pragma: no cover - concise worker diagnostics
        pytest.fail(f"process failed: {type(exc).__name__}: {exc}", pytrace=False)

    assert processed is not None
    assert processed["state"] == "SEARCHABLE"
    assert processed["id"] == accepted["ingestionJob"]["id"]
    related = await runtime.knowledge.upload(
        title="Platform ownership",
        source_key=f"real-mvp/{uuid4()}",
        file_name="ownership.md",
        media_type="text/markdown",
        content=b"Postgres is owned by Platform Team.",
        scope_ids=frozenset({LOCAL_SCOPE_ID}),
        metadata={"classification": "INTERNAL"},
        actor_id=LOCAL_PRINCIPAL_ID,
        idempotency_key=str(uuid4()),
        correlation_id=str(uuid4()),
    )
    related_processed = await runtime.knowledge.process_next()
    assert related_processed is not None
    assert related_processed["state"] == "SEARCHABLE"
    graph_snapshot = await runtime.knowledge.graph_snapshot(frozenset({LOCAL_SCOPE_ID}), limit=200)
    assert any(
        node["name"] == "PostgreSQL" and node["documentCount"] >= 2
        for node in graph_snapshot["nodes"]
    )
    assert any(edge["type"] == "OWNED_BY" for edge in graph_snapshot["edges"])
    duplicate = await runtime.knowledge.upload(
        title="AtlasMind 架构说明副本",
        source_key=f"real-mvp/{uuid4()}",
        file_name="architecture.md",
        media_type="text/markdown",
        content=source_content,
        scope_ids=frozenset({LOCAL_SCOPE_ID}),
        metadata={"businessOwner": "local-admin", "classification": "INTERNAL"},
        actor_id=LOCAL_PRINCIPAL_ID,
        idempotency_key=str(uuid4()),
        correlation_id=str(uuid4()),
    )
    duplicate_processed = await runtime.knowledge.process_next()
    assert duplicate_processed is not None
    assert duplicate_processed["id"] == duplicate["ingestionJob"]["id"]
    await runtime.knowledge.revoke_document(
        duplicate["document"]["id"],
        frozenset({LOCAL_SCOPE_ID}),
        actor_id=LOCAL_PRINCIPAL_ID,
        correlation_id=str(uuid4()),
    )
    async with runtime.engine.begin() as connection:
        await connection.execute(
            text(
                """
                INSERT INTO knowledge_chunks
                    (id, document_version_id, ordinal, content, locator, scope_ids,
                     generation, active, embedding, search_vector)
                VALUES (:id, :version_id, 999, 'incompatible vector fixture',
                        'fixture:dimension-mismatch', :scopes, 1, true,
                        CAST('[0,0,0,0]' AS vector),
                        to_tsvector('simple', 'incompatible vector fixture'))
                """
            ),
            {
                "id": uuid4(),
                "version_id": UUID(str(accepted["versionId"])),
                "scopes": [UUID(LOCAL_SCOPE_ID)],
            },
        )

    restarted = create_runtime(settings, ai=RepeatableAI())
    try:
        query_embedding = (await restarted.ai.embed([query]))[0]
        graph_facts = await restarted.graph.facts(
            query,
            query_embedding=query_embedding,
            scope_ids=frozenset({LOCAL_SCOPE_ID}),
            document_version_ids=frozenset({str(accepted["versionId"]), str(related["versionId"])}),
        )
        assert graph_facts
        assert any("OWNED_BY" in fact and "USES" in fact for fact in graph_facts)
        run_correlation_id = str(uuid4())
        run_trace_id = uuid4().hex
        run = await restarted.knowledge.ask(
            query=query,
            mode="GRAPH",
            context=auth_context(run_correlation_id),
            trace_id=run_trace_id,
        )
    except Exception as exc:  # pragma: no cover - concise query diagnostics
        pytest.fail(f"query failed: {type(exc).__name__}: {exc}", pytrace=False)

    assert run["state"] == "COMPLETED"
    assert "PostgreSQL" in run["answer"]["text"]
    assert run["answer"]["citations"]
    assert any(path["relations"] == ["USES", "OWNED_BY"] for path in run["answer"]["graphPaths"])
    assert run["answer"]["citations"][0]["source"]["locator"]
    assert run["answer"]["citations"][0]["source"]["title"] == "AtlasMind 架构说明"
    assert "PostgreSQL" in run["answer"]["citations"][0]["source"]["excerpt"]

    async with restarted.engine.connect() as connection:
        persisted = (
            (
                await connection.execute(
                    text(
                        """
                    SELECT version.object_key,
                           (SELECT count(*) FROM knowledge_chunks WHERE document_version_id = version.id) AS chunk_count,
                           (SELECT count(*) FROM evidence_records WHERE run_id = :run_id) AS evidence_count,
                           (SELECT count(*) FROM citations WHERE run_id = :run_id) AS citation_count,
                           (SELECT count(*) FROM audit_events WHERE correlation_id = :correlation_id) AS audit_count,
                           (SELECT count(*) FROM agent_runs WHERE id = :run_id AND trace_id = :trace_id) AS trace_count
                      FROM document_versions version
                     WHERE version.id = :version_id
                    """
                    ),
                    {
                        "version_id": UUID(str(accepted["versionId"])),
                        "run_id": UUID(str(run["id"])),
                        "correlation_id": UUID(run_correlation_id),
                        "trace_id": run_trace_id,
                    },
                )
            )
            .mappings()
            .one()
        )
    assert persisted["chunk_count"] > 0
    assert persisted["evidence_count"] > 0
    assert persisted["citation_count"] > 0
    assert persisted["audit_count"] >= 2
    assert persisted["trace_count"] == 1
    stored_source = await restarted.object_store.get_bytes(persisted["object_key"])
    assert b"AtlasMind" in stored_source

    await restarted.knowledge.revoke_document(
        accepted["document"]["id"],
        frozenset({LOCAL_SCOPE_ID}),
        actor_id=LOCAL_PRINCIPAL_ID,
        correlation_id=str(uuid4()),
    )
    await restarted.knowledge.revoke_document(
        related["document"]["id"],
        frozenset({LOCAL_SCOPE_ID}),
        actor_id=LOCAL_PRINCIPAL_ID,
        correlation_id=str(uuid4()),
    )
    after_revoke = await restarted.knowledge.ask(
        query=query,
        mode="GRAPH",
        context=auth_context(str(uuid4())),
    )
    assert all(
        citation["source"]["version"] != accepted["versionId"]
        for citation in after_revoke["answer"]["citations"]
    )
    await runtime.close()
    await restarted.close()
