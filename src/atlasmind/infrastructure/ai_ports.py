"""Backend-independent AI ports and deterministic test adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class Generator(Protocol):
    async def generate(self, prompt: str, *, max_tokens: int) -> str: ...


@dataclass(frozen=True, slots=True)
class RankedText:
    identifier: str
    score: float


class Reranker(Protocol):
    async def rerank(
        self, query: str, texts: dict[str, str], *, limit: int
    ) -> list[RankedText]: ...


class DeterministicEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), float(sum(map(ord, text)) % 997)] for text in texts]


class DeterministicGenerator:
    def __init__(self, response: str = "") -> None:
        self.response = response

    async def generate(self, prompt: str, *, max_tokens: int) -> str:
        del prompt, max_tokens
        return self.response


class DeterministicReranker:
    async def rerank(self, query: str, texts: dict[str, str], *, limit: int) -> list[RankedText]:
        tokens = set(query.casefold().split())
        ranked = [
            RankedText(identifier, float(len(tokens & set(text.casefold().split()))))
            for identifier, text in texts.items()
        ]
        return sorted(ranked, key=lambda item: (-item.score, item.identifier))[:limit]
