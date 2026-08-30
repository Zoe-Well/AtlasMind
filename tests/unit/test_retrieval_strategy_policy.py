"""Advanced RAG planner/runtime boundary and Strategy dependency rules."""

from __future__ import annotations

import pytest

from atlasmind.retrieval.advanced_workflow import build_strategy_registry
from atlasmind.retrieval.strategy_policy import (
    RetrievalPlan,
    StrategyConfiguration,
    StrategySelection,
    default_advanced_retrieval_policy,
)


def selection(strategy_id: str, **parameters: object) -> StrategySelection:
    return StrategySelection(id=strategy_id, parameters=parameters)


def test_registry_contains_internal_operators_with_fixed_stages() -> None:
    registry = build_strategy_registry()

    assert registry.ids == {
        "query_rewrite",
        "multi_query",
        "hyde",
        "self_query",
        "vector",
        "bm25",
        "graph",
        "fusion",
        "rerank",
    }
    assert registry.descriptor("query_rewrite").stage.value == "QUERY_PROCESSING"
    assert registry.descriptor("graph").stage.value == "RETRIEVAL"
    assert registry.descriptor("fusion").stage.value == "FUSION"
    assert registry.descriptor("rerank").stage.value == "RERANK"


def test_planner_cannot_select_disabled_strategy_or_wrong_stage() -> None:
    registry = build_strategy_registry()
    policy = default_advanced_retrieval_policy()

    with pytest.raises(ValueError, match="disabled strategy"):
        registry.validate_plan(
            RetrievalPlan(
                reasonCode="TEST",
                queryProcessing=(selection("query_rewrite"),),
                retrievers=(selection("vector"),),
            ),
            policy,
        )

    with pytest.raises(ValueError, match="not valid"):
        registry.validate_plan(
            RetrievalPlan(
                reasonCode="TEST",
                queryProcessing=(selection("vector"),),
                retrievers=(selection("bm25"),),
            ),
            policy,
        )


def test_multi_query_and_hyde_are_mutually_exclusive() -> None:
    registry = build_strategy_registry()
    policy = default_advanced_retrieval_policy().model_copy(
        update={
            "strategies": {
                **default_advanced_retrieval_policy().strategies,
                "multi_query": StrategyConfiguration(
                    enabled=True,
                    settings={"count": 2},
                ),
                "hyde": StrategyConfiguration(enabled=True),
            }
        }
    )

    with pytest.raises(ValueError, match="conflicting strategy"):
        registry.validate_plan(
            RetrievalPlan(
                reasonCode="TEST",
                queryProcessing=(
                    selection("multi_query", count=2),
                    selection("hyde"),
                ),
                retrievers=(selection("vector"),),
            ),
            policy,
        )


def test_runtime_canonicalizes_order_and_requires_fusion_for_multiple_routes() -> None:
    registry = build_strategy_registry()
    base = default_advanced_retrieval_policy()
    policy = base.model_copy(
        update={
            "strategies": {
                **base.strategies,
                "query_rewrite": StrategyConfiguration(enabled=True),
                "self_query": StrategyConfiguration(
                    enabled=True,
                    settings={"allowedMetadataFields": ["classification", "businessOwner"]},
                ),
            }
        }
    )
    plan = registry.validate_plan(
        RetrievalPlan(
            reasonCode="TEST",
            queryProcessing=(selection("self_query"), selection("query_rewrite")),
            retrievers=(selection("bm25"), selection("vector")),
            postRetrieval=(selection("rerank"),),
        ),
        policy,
    )

    assert [item.id for item in plan.query_processing] == [
        "query_rewrite",
        "self_query",
    ]
    assert [item.id for item in plan.retrievers] == ["vector", "bm25"]
    assert plan.fusion_required is True
    assert plan.rerank is True

    without_fusion = policy.model_copy(
        update={
            "strategies": {
                **policy.strategies,
                "fusion": StrategyConfiguration(enabled=False),
            }
        }
    )
    with pytest.raises(ValueError, match="requires fusion"):
        registry.validate_plan(
            RetrievalPlan(
                reasonCode="TEST",
                retrievers=(selection("vector"), selection("bm25")),
            ),
            without_fusion,
        )


def test_hyde_requires_vector_and_rerank_cannot_appear_before_retrieval() -> None:
    registry = build_strategy_registry()
    base = default_advanced_retrieval_policy()
    policy = base.model_copy(
        update={
            "strategies": {
                **base.strategies,
                "hyde": StrategyConfiguration(enabled=True),
            }
        }
    )

    with pytest.raises(ValueError, match="HyDE requires"):
        registry.validate_plan(
            RetrievalPlan(
                reasonCode="TEST",
                queryProcessing=(selection("hyde"),),
                retrievers=(selection("bm25"),),
            ),
            policy,
        )

    with pytest.raises(ValueError, match="not valid"):
        registry.validate_plan(
            RetrievalPlan(
                reasonCode="TEST",
                queryProcessing=(selection("rerank"),),
                retrievers=(selection("vector"),),
            ),
            policy,
        )
