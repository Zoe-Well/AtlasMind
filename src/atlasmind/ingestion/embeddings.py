"""Bounded embedding construction and scope-separated exact-input reuse."""

from __future__ import annotations

import asyncio
import json
import math
from collections import OrderedDict, deque
from hashlib import sha256
from time import monotonic, perf_counter
from typing import Any

import httpx
from sqlalchemy import text

PARSER_VERSION = "semantic-documents-v2"
CHUNKER_VERSION = "section-1500chars-4500bytes-v2"


def fingerprint(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def model_profile(model: Any) -> str | None:
    value = getattr(model, "embedding_profile", None)
    return value if isinstance(value, str) and len(value) == 64 else None


def vector_literal(vector: list[float]) -> str:
    if not vector or any(not math.isfinite(value) for value in vector):
        raise ValueError("INVALID_EMBEDDING_VECTOR")
    return "[" + ",".join(format(value, ".12g") for value in vector) + "]"


class QueryEmbeddingCache:
    """Only vectors, never evidence/answers. Keys contain no raw query or scope IDs."""

    def __init__(self, *, ttl: float = 60, capacity: int = 128) -> None:
        self.ttl, self.capacity = ttl, capacity
        self.values: OrderedDict[str, tuple[float, tuple[float, ...]]] = OrderedDict()

    def get(self, key: str) -> list[float] | None:
        item = self.values.get(key)
        if item is None:
            return None
        if item[0] <= monotonic():
            self.values.pop(key, None)
            return None
        self.values.move_to_end(key)
        return list(item[1])

    def put(self, key: str, vector: list[float]) -> None:
        vector_literal(vector)
        self.values[key] = (monotonic() + self.ttl, tuple(vector))
        self.values.move_to_end(key)
        while len(self.values) > self.capacity:
            self.values.popitem(last=False)


async def query_embeddings(
    model: Any, texts: list[str], scopes: frozenset[str]
) -> tuple[list[list[float]], int]:
    cache = getattr(model, "query_embedding_cache", None)
    if not isinstance(cache, QueryEmbeddingCache) or model_profile(model) is None:
        return await model.embed(texts), 0
    namespace = json.dumps([model_profile(model), sorted(scopes)], ensure_ascii=False)
    keys = [fingerprint(namespace + "\0" + value) for value in texts]
    values = [cache.get(key) for key in keys]
    missing = [i for i, value in enumerate(values) if value is None]
    if missing:
        vectors = await model.embed([texts[i] for i in missing])
        for index, vector in zip(missing, vectors, strict=True):
            cache.put(keys[index], vector)
            values[index] = vector
    return [value for value in values if value is not None], len(texts) - len(missing)


class EmbeddingBuilder:
    def __init__(
        self, sessions: Any, model: Any, *, batch_size: int = 16, batch_chars: int = 12000
    ) -> None:
        self.sessions, self.model = sessions, model
        if batch_size < 1 or batch_chars < 1:
            raise ValueError("INVALID_EMBEDDING_BATCH_BUDGET")
        self.batch_size, self.batch_chars = batch_size, batch_chars

    async def build(
        self, texts: list[str], scopes: frozenset[str]
    ) -> tuple[list[list[float]], dict[str, int]]:
        started = perf_counter()
        profile = model_profile(self.model)
        scope_key = fingerprint(json.dumps(sorted(scopes)))
        digests = [fingerprint(value) for value in texts]
        available: dict[str, list[float]] = {}
        expected_dimension: int | None = None
        if profile:
            async with self.sessions() as session:
                expected_dimension = (
                    await session.execute(
                        text(
                                "SELECT dimension FROM knowledge_embedding_cache "
                                "WHERE profile=:profile LIMIT 1"
                        ),
                        {"profile": profile},
                    )
                ).scalar_one_or_none()
                rows = (
                    await session.execute(
                        text(
                            "SELECT content_digest, embedding::text FROM knowledge_embedding_cache "
                            "WHERE profile=:profile AND scope_key=:scope "
                            "AND content_digest=ANY(:digests)"
                        ),
                        {"profile": profile, "scope": scope_key, "digests": digests},
                    )
                ).all()
                available = {row[0]: json.loads(row[1]) for row in rows}
        hits = sum(digest in available for digest in digests)
        if any(not value.strip() or len(value) > self.batch_chars for value in texts):
            raise ValueError("EMBEDDING_INPUT_OUTSIDE_BATCH_BUDGET")
        pending = deque(
            {
                digest: value
                for digest, value in zip(digests, texts, strict=True)
                if digest not in available
            }.items()
        )
        calls = 0
        while pending:
            batch: list[tuple[str, str]] = []
            chars = 0
            while pending and len(batch) < self.batch_size:
                if batch and chars + len(pending[0][1]) > self.batch_chars:
                    break
                item = pending.popleft()
                chars += len(item[1])
                batch.append(item)
            for attempt in range(2):
                try:
                    calls += 1
                    vectors = await self.model.embed([item[1] for item in batch])
                    break
                except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                    retryable = not isinstance(
                        exc, httpx.HTTPStatusError
                    ) or exc.response.status_code in {429, 500, 502, 503, 504}
                    if attempt or not retryable:
                        raise
                    await asyncio.sleep(0.25)
            if len(vectors) != len(batch):
                raise ValueError("EMBEDDING_BATCH_COUNT_MISMATCH")
            dimensions = {len(vector) for vector in vectors}
            if len(dimensions) != 1 or (
                expected_dimension is not None and dimensions != {expected_dimension}
            ):
                raise ValueError("EMBEDDING_PROFILE_DIMENSION_CHANGED")
            expected_dimension = len(vectors[0])
            for (digest, _), vector in zip(batch, vectors, strict=True):
                vector_literal(vector)
                available[digest] = vector
            if profile:
                async with self.sessions() as session, session.begin():
                    for (digest, _), vector in zip(batch, vectors, strict=True):
                        await session.execute(
                            text(
                                "INSERT INTO knowledge_embedding_cache"
                                "(profile,scope_key,content_digest,dimension,embedding) "
                                "VALUES (:profile,:scope,:digest,:dimension,"
                                "CAST(:vector AS vector)) "
                                "ON CONFLICT DO NOTHING"
                            ),
                            {
                                "profile": profile,
                                "scope": scope_key,
                                "digest": digest,
                                "dimension": len(vector),
                                "vector": vector_literal(vector),
                            },
                        )
            await asyncio.sleep(0)
        result = [available[digest] for digest in digests]
        if len({len(vector) for vector in result}) > 1:
            raise ValueError("EMBEDDING_PROFILE_DIMENSION_CHANGED")
        return result, {
            "embedding_calls": calls,
            "embedding_cache_hits": hits,
            "embedding_chunks": len(result),
            "embedding_ms": round((perf_counter() - started) * 1000),
        }
