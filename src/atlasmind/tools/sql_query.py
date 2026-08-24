"""Allowlisted semantic requests compiled into parameterized read-only SQL."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from atlasmind.domain.common import AuthorizationDenied, BudgetExceeded


@dataclass(frozen=True, slots=True)
class StructuredDataset:
    name: str
    version: str
    table: str
    metrics: dict[str, str]
    dimensions: dict[str, str]
    scope_column: str
    max_rows: int = 100


@dataclass(frozen=True, slots=True)
class SemanticQuery:
    dataset: str
    metric: str
    dimensions: tuple[str, ...] = ()
    filters: dict[str, str | int | float] | None = None
    limit: int = 100


@dataclass(frozen=True, slots=True)
class CompiledQuery:
    statement: str
    parameters: dict[str, Any]
    dataset_version: str


class StructuredQueryCompiler:
    def __init__(self, datasets: tuple[StructuredDataset, ...]) -> None:
        self._datasets = {item.name: item for item in datasets}

    def compile(self, query: SemanticQuery, *, scope_ids: frozenset[str]) -> CompiledQuery:
        dataset = self._datasets.get(query.dataset)
        if dataset is None:
            raise AuthorizationDenied(details={"reason": "DATASET_NOT_AVAILABLE"})
        metric = dataset.metrics.get(query.metric)
        if metric is None:
            raise AuthorizationDenied(details={"reason": "METRIC_NOT_AVAILABLE"})
        if not scope_ids:
            raise AuthorizationDenied(details={"reason": "SCOPE_REQUIRED"})
        if query.limit > dataset.max_rows:
            raise BudgetExceeded(details={"reason": "ROW_BUDGET_EXCEEDED"})
        selected_dimensions: list[str] = []
        for name in query.dimensions:
            column = dataset.dimensions.get(name)
            if column is None:
                raise AuthorizationDenied(details={"reason": "DIMENSION_NOT_AVAILABLE"})
            selected_dimensions.append(column)
        parameters: dict[str, Any] = {"scope_ids": list(scope_ids), "limit": query.limit}
        predicates = [f"{dataset.scope_column} = ANY(:scope_ids)"]
        for index, (name, value) in enumerate(sorted((query.filters or {}).items())):
            column = dataset.dimensions.get(name)
            if column is None:
                raise AuthorizationDenied(details={"reason": "FILTER_NOT_AVAILABLE"})
            parameter = f"filter_{index}"
            predicates.append(f"{column} = :{parameter}")
            parameters[parameter] = value
        select = ", ".join([*selected_dimensions, f"{metric} AS value"])
        group_by = f" GROUP BY {', '.join(selected_dimensions)}" if selected_dimensions else ""
        statement = (
            f"SELECT {select} FROM {dataset.table} WHERE {' AND '.join(predicates)}"
            f"{group_by} LIMIT :limit"
        )
        return CompiledQuery(statement, parameters, dataset.version)
