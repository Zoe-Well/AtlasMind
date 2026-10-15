"""Concrete risks: duplicate inputs, batch retries, scope/model cache leakage and bad vectors."""

from unittest.mock import AsyncMock

import httpx
import pytest

from atlasmind.ingestion.embeddings import EmbeddingBuilder, QueryEmbeddingCache, query_embeddings
from atlasmind.retrieval.lexical_pg import BasicMultilingualTokenizer


class Model:
    def __init__(self):
        self.embed = AsyncMock(side_effect=lambda texts: [[float(len(t)), 1.0] for t in texts])


async def test_batches_deduplicate_and_respect_count_and_char_limits():
    model = Model()
    vectors, metrics = await EmbeddingBuilder(None, model, batch_size=2, batch_chars=6).build(
        ["abc", "def", "abc", "long", "x"], frozenset({"scope"})
    )
    assert model.embed.await_args_list[0].args[0] == ["abc", "def"]
    assert model.embed.await_args_list[1].args[0] == ["long", "x"]
    assert len(vectors) == 5 and vectors[0] == vectors[2]
    assert metrics["embedding_calls"] == 2


async def test_retry_only_failed_batch_and_never_retry_validation_failure():
    model = Model()
    model.embed.side_effect = [[[1, 2]], httpx.ReadTimeout("temporary"), [[2, 3]]]
    vectors, metrics = await EmbeddingBuilder(None, model, batch_size=1).build(
        ["one", "two"], frozenset({"scope"})
    )
    assert vectors == [[1, 2], [2, 3]] and metrics["embedding_calls"] == 3
    assert [call.args[0] for call in model.embed.await_args_list] == [["one"], ["two"], ["two"]]
    model.embed.reset_mock(side_effect=True)
    model.embed.side_effect = ValueError("bad")
    with pytest.raises(ValueError):
        await EmbeddingBuilder(None, model).build(["one"], frozenset())
    assert model.embed.await_count == 1


@pytest.mark.parametrize("vectors", [[], [[float("nan")]], [[float("inf")]], [[]]])
async def test_invalid_embedding_never_enters_cache(vectors):
    model = Model()
    model.embed.side_effect = None
    model.embed.return_value = vectors
    with pytest.raises(ValueError):
        await EmbeddingBuilder(None, model).build(["one"], frozenset())


async def test_query_cache_scope_model_and_expiry(monkeypatch):
    now = [1.0]
    monkeypatch.setattr("atlasmind.ingestion.embeddings.monotonic", lambda: now[0])
    model = Model()
    model.embedding_profile = "a" * 64
    model.query_embedding_cache = QueryEmbeddingCache(ttl=60, capacity=2)
    first, hits = await query_embeddings(model, ["secret"], frozenset({"a"}))
    assert hits == 0
    first[0][0] = -99  # callers cannot mutate cached values
    second, hits = await query_embeddings(model, ["secret"], frozenset({"a"}))
    assert hits == 1 and second[0][0] != -99
    assert (await query_embeddings(model, ["secret"], frozenset({"b"})))[1] == 0
    model.embedding_profile = "b" * 64
    assert (await query_embeddings(model, ["secret"], frozenset({"a"})))[1] == 0
    now[0] += 61
    assert (await query_embeddings(model, ["secret"], frozenset({"a"})))[1] == 0
    assert len(model.query_embedding_cache.values) <= 2
    assert all("secret" not in key for key in model.query_embedding_cache.values)


def test_chinese_index_query_share_tokens_and_query_syntax_is_escaped():
    tokenizer = BasicMultilingualTokenizer()
    assert {"商品", "上架", "总部", "审核"}.issubset(tokenizer.tokenize("商品上架需要总部审核"))
    assert "退款" in tokenizer.document("退款何时到账")
    assert '"退款"' in tokenizer.query('退款 OR "到账" -上架')
    assert tokenizer.query('" - ()') == ""
