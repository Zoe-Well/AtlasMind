"""PostgreSQL lexical retrieval and replaceable Chinese/English tokenization."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Protocol

import jieba
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from atlasmind.domain.knowledge import KnowledgeChunk
from atlasmind.retrieval.hybrid import RetrievalCandidate


class Tokenizer(Protocol):
    def tokenize(self, value: str) -> list[str]: ...


LEXICAL_VERSION = "jieba-0.42.1-commerce-v1"
BUSINESS_WORDS = (
    "易富路",
    "售后",
    "上下架",
    "上架",
    "下架",
    "改价",
    "自提",
    "结算",
    "退款",
    "到账",
    "商户",
    "总部",
    "运费",
)


@lru_cache(maxsize=1)
def _tokenizer() -> jieba.Tokenizer:
    tokenizer = jieba.Tokenizer()
    tokenizer.initialize()
    for word in BUSINESS_WORDS:
        tokenizer.add_word(word, freq=100000)
    return tokenizer


class BasicMultilingualTokenizer:
    """Shared, versioned indexing/query tokenizer; name retained for existing callers."""

    def tokenize(self, value: str) -> list[str]:
        return [
            token.casefold()
            for token in _tokenizer().cut_for_search(value, HMM=False)
            if re.search(r"[\w\u4e00-\u9fff]", token)
        ]

    def document(self, value: str) -> str:
        return " ".join(self.tokenize(value))

    def query(self, value: str) -> str:
        # Escape every token as an operand; user syntax never controls the tsquery.
        tokens = list(dict.fromkeys(self.tokenize(value)))[:64]
        return " OR ".join('"' + token.replace('"', "") + '"' for token in tokens)


class PgLexicalRetriever:
    def __init__(self, session: AsyncSession, tokenizer: Tokenizer | None = None) -> None:
        self._session = session
        self._tokenizer = tokenizer or BasicMultilingualTokenizer()

    async def retrieve(
        self,
        query: str,
        *,
        scope_ids: frozenset[str],
        active_generation: int,
        limit: int,
    ) -> list[RetrievalCandidate]:
        if not scope_ids:
            return []
        normalized = " OR ".join(
            '"' + token.replace('"', "") + '"' for token in self._tokenizer.tokenize(query)
        )
        result = await self._session.execute(
            text("""SELECT id, document_version_id, ordinal, content, locator, scope_ids,
                   generation,
                   ts_rank(search_vector, websearch_to_tsquery('simple', :query), 2) AS score
            FROM knowledge_chunks
            WHERE active = TRUE AND generation = :generation AND scope_ids && :scopes
              AND search_vector @@ websearch_to_tsquery('simple', :query)
            ORDER BY score DESC LIMIT :limit"""),
            {
                "query": normalized,
                "generation": active_generation,
                "scopes": list(scope_ids),
                "limit": limit,
            },
        )
        return [
            RetrievalCandidate(
                KnowledgeChunk(
                    id=row.id,
                    document_version_id=row.document_version_id,
                    ordinal=row.ordinal,
                    content=row.content,
                    locator=row.locator,
                    scope_ids=frozenset(row.scope_ids),
                    generation=row.generation,
                ),
                float(row.score),
                "lexical",
            )
            for row in result
        ]


class InMemoryLexicalRetriever:
    def __init__(self, chunks: list[KnowledgeChunk], tokenizer: Tokenizer | None = None) -> None:
        self._chunks = chunks
        self._tokenizer = tokenizer or BasicMultilingualTokenizer()

    async def retrieve(
        self,
        query: str,
        *,
        scope_ids: frozenset[str],
        active_generation: int,
        limit: int,
    ) -> list[RetrievalCandidate]:
        query_tokens = set(self._tokenizer.tokenize(query))
        scored: list[RetrievalCandidate] = []
        for chunk in self._chunks:
            if (
                not chunk.active
                or chunk.generation != active_generation
                or not chunk.scope_ids & scope_ids
            ):
                continue
            overlap = len(query_tokens & set(self._tokenizer.tokenize(chunk.content)))
            if overlap:
                scored.append(RetrievalCandidate(chunk, float(overlap), "lexical"))
        return sorted(scored, key=lambda item: (-item.score, item.chunk.id))[:limit]
