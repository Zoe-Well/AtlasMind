"""Structured Agent capability compiles only server-controlled read-only queries."""

from __future__ import annotations

from typing import Any, cast

import pytest
from pydantic import ValidationError

from atlasmind.application.rag_capabilities import AgentRAGCapabilities, StructuredSearchInput
from atlasmind.domain.common import AuthorizationDenied, BudgetExceeded
from atlasmind.tools.sql_query import SemanticQuery, StructuredDataset, StructuredQueryCompiler


def dataset() -> StructuredDataset:
    return StructuredDataset(
        name="orders",
        version="2026-08",
        table="business_orders",
        metrics={"order_count": "COUNT(*)"},
        dimensions={"region": "region_code", "status": "order_status"},
        scope_column="knowledge_scope_id",
        max_rows=50,
    )


def test_compiler_uses_allowlisted_identifiers_and_parameterized_values() -> None:
    compiled = StructuredQueryCompiler((dataset(),)).compile(
        SemanticQuery(
            dataset="orders",
            metric="order_count",
            dimensions=("region",),
            filters={"status": "PAID' OR true --"},
            limit=20,
        ),
        scope_ids=frozenset({"scope-a"}),
    )

    assert "FROM business_orders" in compiled.statement
    assert "COUNT(*) AS value" in compiled.statement
    assert "knowledge_scope_id = ANY(:scope_ids)" in compiled.statement
    assert "order_status = :filter_0" in compiled.statement
    assert "PAID' OR true --" not in compiled.statement
    assert compiled.parameters == {
        "scope_ids": ["scope-a"],
        "limit": 20,
        "filter_0": "PAID' OR true --",
    }


@pytest.mark.parametrize(
    ("query", "reason"),
    [
        (SemanticQuery(dataset="unknown", metric="order_count"), "DATASET_NOT_AVAILABLE"),
        (SemanticQuery(dataset="orders", metric="raw_sql"), "METRIC_NOT_AVAILABLE"),
        (
            SemanticQuery(
                dataset="orders",
                metric="order_count",
                dimensions=("secret",),
                limit=20,
            ),
            "DIMENSION_NOT_AVAILABLE",
        ),
        (
            SemanticQuery(
                dataset="orders",
                metric="order_count",
                filters={"secret": "x"},
                limit=20,
            ),
            "FILTER_NOT_AVAILABLE",
        ),
    ],
)
def test_compiler_rejects_non_allowlisted_semantics(
    query: SemanticQuery,
    reason: str,
) -> None:
    with pytest.raises(AuthorizationDenied) as error:
        StructuredQueryCompiler((dataset(),)).compile(
            query,
            scope_ids=frozenset({"scope-a"}),
        )
    assert error.value.details["reason"] == reason


def test_compiler_requires_scope_and_enforces_row_budget() -> None:
    compiler = StructuredQueryCompiler((dataset(),))
    with pytest.raises(AuthorizationDenied):
        compiler.compile(
            SemanticQuery(dataset="orders", metric="order_count"),
            scope_ids=frozenset(),
        )
    with pytest.raises(BudgetExceeded):
        compiler.compile(
            SemanticQuery(dataset="orders", metric="order_count", limit=51),
            scope_ids=frozenset({"scope-a"}),
        )


def test_public_structured_tool_input_rejects_raw_sql_and_scope() -> None:
    with pytest.raises(ValidationError):
        StructuredSearchInput.model_validate(
            {
                "dataset": "orders",
                "metric": "order_count",
                "sql": "DROP TABLE business_orders",
            }
        )
    with pytest.raises(ValidationError):
        StructuredSearchInput.model_validate(
            {
                "dataset": "orders",
                "metric": "order_count",
                "scope_ids": ["forged"],
            }
        )


def test_structured_tool_is_hidden_until_server_dataset_is_configured() -> None:
    dependency = cast(Any, object())
    without_dataset = AgentRAGCapabilities(dependency, dependency, dependency)
    with_dataset = AgentRAGCapabilities(
        dependency,
        dependency,
        dependency,
        structured_datasets=(dataset(),),
    )

    assert "query_structured_data" not in {item.name for item in without_dataset.tool_specs}
    assert "query_structured_data" in {item.name for item in with_dataset.tool_specs}
