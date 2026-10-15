"""Internal LLM Strategy behavior remains bounded and outside the Agent tool surface."""

from __future__ import annotations

from typing import Any, cast
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from atlasmind.infrastructure.ai_ports import RankedText
from atlasmind.retrieval.advanced_workflow import (
    AdvancedRetrievalWorkflow,
    HyDEStrategy,
    MultiQueryStrategy,
    ProcessedQuery,
    QueryRewriteStrategy,
    RetrievalWorkflowContext,
    SelfQueryStrategy,
    build_strategy_registry,
)
from atlasmind.retrieval.strategy_policy import (
    RetrievalPlan,
    StrategyConfiguration,
    StrategySelection,
    default_advanced_retrieval_policy,
)


@pytest.mark.asyncio
async def test_fixed_service_plan_does_not_call_model_planner() -> None:
    model = ScriptedRetrievalModel([])
    current = replace(context(model), fixed_plan=RetrievalPlan(
        reasonCode="SERVICE_STANDARD_V1",
        retrievers=(StrategySelection(id="vector"), StrategySelection(id="bm25")),
        postRetrieval=(StrategySelection(id="rerank"),),
    ))
    workflow = object.__new__(AdvancedRetrievalWorkflow)
    workflow._publish_activity = AsyncMock()
    result = await workflow._plan({}, SimpleNamespace(context=current))
    assert result['draft_plan'] == current.fixed_plan
    assert model.prompts == []


class ScriptedRetrievalModel:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = responses
        self.prompts: list[str] = []

    async def complete_json(self, prompt: str, *, max_tokens: int = 1_200) -> dict[str, object]:
        del max_tokens
        self.prompts.append(prompt)
        return self.responses.pop(0)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]

    async def rerank(self, query: str, texts: dict[str, str], *, limit: int) -> list[RankedText]:
        del query
        return [RankedText(identifier, 1.0) for identifier in texts][:limit]


def context(model: ScriptedRetrievalModel) -> RetrievalWorkflowContext:
    base = default_advanced_retrieval_policy()
    policy = base.model_copy(
        update={
            "strategies": {
                **base.strategies,
                "query_rewrite": StrategyConfiguration(enabled=True),
                "multi_query": StrategyConfiguration(enabled=True, settings={"count": 2}),
                "hyde": StrategyConfiguration(enabled=True),
                "self_query": StrategyConfiguration(
                    enabled=True,
                    settings={"allowedMetadataFields": ["classification"]},
                ),
            }
        }
    )
    return RetrievalWorkflowContext(
        sessions=cast(Any, object()),
        model=model,
        graph=cast(Any, object()),
        scopes=frozenset({"00000000-0000-4000-8000-000000000010"}),
        authz_revision=1,
        policy=policy,
        graph_policy=cast(Any, object()),
        registry=build_strategy_registry(),
    )


@pytest.mark.asyncio
async def test_llm_query_strategies_transform_state_without_becoming_tools() -> None:
    model = ScriptedRetrievalModel(
        [
            {"rewrittenQuery": "AtlasMind PostgreSQL ownership"},
            {"filters": {"classification": "INTERNAL"}},
            {"queries": ["AtlasMind database owner", "Who owns PostgreSQL?"]},
        ]
    )
    runtime = context(model)
    current = ProcessedQuery(
        original_query="AtlasMind 的 PostgreSQL 谁负责?",
        canonical_query="AtlasMind 的 PostgreSQL 谁负责?",
        query_variants=("AtlasMind 的 PostgreSQL 谁负责?",),
    )
    current = await QueryRewriteStrategy().execute(
        current, StrategySelection(id="query_rewrite"), runtime
    )
    current = await SelfQueryStrategy().execute(
        current, StrategySelection(id="self_query"), runtime
    )
    current = await MultiQueryStrategy().execute(
        current,
        StrategySelection(id="multi_query", parameters={"count": 2}),
        runtime,
    )

    assert current.canonical_query == "AtlasMind PostgreSQL ownership"
    assert current.metadata_filters == {"classification": "INTERNAL"}
    assert len(current.query_variants) == runtime.policy.budget.max_query_variants
    assert len(model.prompts) == 3
    assert set(runtime.registry.ids).isdisjoint({"knowledge_search", "search_graph"})


@pytest.mark.asyncio
async def test_hyde_is_retrieval_only_and_self_query_rejects_unknown_fields() -> None:
    model = ScriptedRetrievalModel(
        [
            {"hypotheticalDocument": "AtlasMind stores ownership metadata in PostgreSQL."},
            {"filters": {"scope_ids": "forged"}},
        ]
    )
    runtime = context(model)
    current = ProcessedQuery("question", "question", ("question",))

    hyde = await HyDEStrategy().execute(current, StrategySelection(id="hyde"), runtime)
    assert hyde.hypothetical_document
    assert hyde.query_variants == ("question",)

    with pytest.raises(ValueError, match="outside the allowlist"):
        await SelfQueryStrategy().execute(current, StrategySelection(id="self_query"), runtime)
