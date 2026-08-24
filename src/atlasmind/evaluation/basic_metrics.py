"""Deterministic retrieval and citation metrics."""

from __future__ import annotations

from math import log2


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 1.0
    return len(set(retrieved[:k]) & relevant) / len(relevant)


def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    for rank, identifier in enumerate(retrieved, start=1):
        if identifier in relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved: list[str], relevance: dict[str, float], k: int) -> float:
    actual = sum(
        relevance.get(identifier, 0.0) / log2(rank + 1)
        for rank, identifier in enumerate(retrieved[:k], 1)
    )
    ideal_values = sorted(relevance.values(), reverse=True)[:k]
    ideal = sum(value / log2(rank + 1) for rank, value in enumerate(ideal_values, 1))
    return actual / ideal if ideal else 1.0


def citation_accuracy(supported_claims: int, total_claims: int) -> float:
    return supported_claims / total_claims if total_claims else 1.0


def insufficient_answer_accuracy(predicted: list[bool], expected: list[bool]) -> float:
    if len(predicted) != len(expected):
        raise ValueError("metric inputs must have equal length")
    if not predicted:
        return 1.0
    return sum(left == right for left, right in zip(predicted, expected, strict=True)) / len(
        predicted
    )
