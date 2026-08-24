"""Versioned retrieval policy and bounded simple-query budgets."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QueryBudget:
    candidate_limit: int = 40
    result_limit: int = 8
    timeout_ms: int = 8_000
    max_context_characters: int = 24_000

    def __post_init__(self) -> None:
        if (
            min(
                self.candidate_limit,
                self.result_limit,
                self.timeout_ms,
                self.max_context_characters,
            )
            <= 0
        ):
            raise ValueError("query budgets must be positive")
        if self.result_limit > self.candidate_limit:
            raise ValueError("result limit cannot exceed candidate limit")


@dataclass(frozen=True, slots=True)
class RetrievalPolicy:
    name: str
    version: int
    enabled_backends: tuple[str, ...] = ("vector", "lexical")
    rrf_constant: int = 60
    budget: QueryBudget = QueryBudget()
    active: bool = True

    def __post_init__(self) -> None:
        if self.version < 1 or self.rrf_constant < 1 or not self.enabled_backends:
            raise ValueError("invalid retrieval policy")
