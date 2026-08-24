"""Real PostgreSQL, MinIO and Neo4j MVP flow.

Run with ``ATLASMIND_RUN_REAL_MVP=1`` after starting the Compose dependencies.
The deterministic AI boundary keeps the test repeatable while every knowledge artifact is real.
"""

# ruff: noqa: RUF001 -- Chinese fixture punctuation is intentional user content.

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest

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


class RepeatableAI:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [
            [
                float("PostgreSQL" in text),
                float("AtlasMind" in text),
                float(len(text) % 17) / 17,
            ]
            for text in texts
        ]

    async def extract_graph(self, content: str, *, locator: str) -> GraphExtraction:
        del locator
        if "AtlasMind" not in content or "PostgreSQL" not in content:
            return GraphExtraction(entities=(), relations=(), extraction_version="test-v1")
        return GraphExtraction(
            entities=(
                ExtractedEntity(name="AtlasMind", entity_type="PRODUCT", aliases=()),
                ExtractedEntity(name="PostgreSQL", entity_type="SYSTEM", aliases=()),
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
        graph_facts: tuple[str, ...],
    ) -> GroundedAnswer:
        del query
        assert graph_facts
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

    try:
        accepted = await runtime.knowledge.upload(
            title="AtlasMind 架构说明",
            source_key=source_key,
            file_name="architecture.md",
            media_type="text/markdown",
            content=(
                "# 架构\n\nAtlasMind 使用 PostgreSQL 保存规范知识状态，并将实体关系投影到 "
                f"Neo4j。\n\n测试来源：{source_key}"
            ).encode(),
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

    restarted = create_runtime(settings, ai=RepeatableAI())
    try:
        run = await restarted.knowledge.ask(
            query="AtlasMind 使用什么保存规范知识状态？",
            mode="GRAPH",
            principal_id=LOCAL_PRINCIPAL_ID,
            scope_ids=frozenset({LOCAL_SCOPE_ID}),
            authz_revision=1,
            correlation_id=str(uuid4()),
        )
    except Exception as exc:  # pragma: no cover - concise query diagnostics
        pytest.fail(f"query failed: {type(exc).__name__}: {exc}", pytrace=False)

    assert run["state"] == "COMPLETED"
    assert "PostgreSQL" in run["answer"]["text"]
    assert run["answer"]["citations"]
    assert run["answer"]["citations"][0]["source"]["locator"]
    await runtime.close()
    await restarted.close()
