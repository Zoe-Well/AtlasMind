"""PostgreSQL migration/reindex and isolation tests; isolated DB supplied by the runner."""

# ruff: noqa: E501 -- keep fixture SQL column lists readable.

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from atlasmind.ingestion.embeddings import EmbeddingBuilder, QueryEmbeddingCache
from atlasmind.ingestion.reindex import rebuild
from atlasmind.retrieval.advanced_workflow import (
    AdvancedRetrievalWorkflow,
    BM25RetrieverStrategy,
    ProcessedQuery,
    RetrievalWorkflowContext,
    VectorRetrieverStrategy,
    build_strategy_registry,
)
from atlasmind.retrieval.neighbors import neighbor_rows
from atlasmind.retrieval.strategy_policy import StrategySelection, default_advanced_retrieval_policy

pytestmark = pytest.mark.skipif(
    not os.getenv("ATLASMIND_MANUAL_TEST_DB"), reason="isolated DB required"
)


class Model:
    embedding_profile = "a" * 64

    def __init__(self):
        self.embedding_descriptor = {"model": "test", "revision": "1"}
        self.calls = 0
        self.query_embedding_cache = QueryEmbeddingCache()

    async def embed(self, texts):
        self.calls += 1
        return [[1.0, 0.0, 0.0] for _ in texts]


@pytest.fixture
async def fixture():
    engine = create_async_engine(os.environ["ATLASMIND_MANUAL_TEST_DB"])
    async with engine.connect() as conn:
        transaction = await conn.begin()
        try:
            scope, private, document, version = [uuid4() for _ in range(4)]
            await conn.execute(
                text(
                    "INSERT INTO knowledge_documents(id,title,source_key,scope_ids) "
                    "VALUES (:d,'检索测试',:key,:scopes)"
                ),
                {"d": document, "key": str(document), "scopes": [scope]},
            )
            await conn.execute(
                text(
                    "INSERT INTO document_versions(id,document_id,content_digest,scope_ids,searchable,generation,created_at) "
                    "VALUES (:v,:d,:digest,:scopes,true,1,now())"
                ),
                {"v": version, "d": document, "digest": "sha256:" + "f" * 64, "scopes": [scope]},
            )
            await conn.execute(
                text("UPDATE knowledge_documents SET active_version_id=:v WHERE id=:d"),
                {"v": version, "d": document},
            )
            ids = [uuid4() for _ in range(4)]
            for ordinal, (cid, content) in enumerate(
                zip(
                    ids,
                    ["商品上架需要总部审核", "请检查商品库存", "审核失败请联系客服", "退款说明"],
                    strict=True,
                )
            ):
                await conn.execute(
                    text(
                        "INSERT INTO knowledge_chunks(id,document_version_id,ordinal,content,locator,scope_ids,generation,embedding,search_vector,section_key) "
                        "VALUES (:c,:v,:i,:content,:locator,:scopes,1,'[1,0,0]',to_tsvector('simple',:content),:section)"
                    ),
                    {
                        "c": cid,
                        "v": version,
                        "i": ordinal,
                        "content": content,
                        "locator": f"paragraph={ordinal + 1}",
                        "scopes": [scope],
                        "section": "a" * 64 if ordinal < 2 else "b" * 64,
                    },
                )
            sessions = async_sessionmaker(conn, join_transaction_mode="create_savepoint")
            model = Model()
            context = RetrievalWorkflowContext(
                sessions,
                model,
                None,
                frozenset({str(scope)}),
                1,
                default_advanced_retrieval_policy(),
                None,
                build_strategy_registry(),
            )
            yield context, conn, ids, document, version, private
        finally:
            await transaction.rollback()
    await engine.dispose()


def query(value):
    return ProcessedQuery(value, value, (value,))


async def test_legacy_rebuild_preserves_citations_and_enables_chinese_and_model_filter(fixture):
    ctx, conn, ids, _, version, _ = fixture
    lexical, vector = BM25RetrieverStrategy(), VectorRetrieverStrategy()
    assert not (
        await lexical.execute(query("商品上架"), StrategySelection(id="bm25"), ctx)
    ).rankings[0]
    assert not (
        await vector.execute(query("商品上架"), StrategySelection(id="vector"), ctx)
    ).rankings[0]
    before = (
        await conn.execute(
            text(
                "SELECT id,content,locator FROM knowledge_chunks WHERE document_version_id=:v ORDER BY ordinal"
            ),
            {"v": version},
        )
    ).all()
    result = await rebuild(ctx.sessions, ctx.model, ctx.scopes)
    assert result["chunks"] == 4
    after = (
        await conn.execute(
            text(
                "SELECT id,content,locator FROM knowledge_chunks WHERE document_version_id=:v ORDER BY ordinal"
            ),
            {"v": version},
        )
    ).all()
    assert before == after
    hits = (await lexical.execute(query("商品上架"), StrategySelection(id="bm25"), ctx)).rankings[0]
    assert hits[0].chunk.id == str(ids[0])
    assert (
        len(
            (await vector.execute(query("商品上架"), StrategySelection(id="vector"), ctx)).rankings[
                0
            ]
        )
        == 4
    )
    ctx.model.embedding_profile = "b" * 64  # same dimensions, different model: never mix
    assert not (
        await vector.execute(query("商品上架"), StrategySelection(id="vector"), ctx)
    ).rankings[0]


async def test_durable_cache_reuse_separates_scope_and_profile(fixture):
    ctx, _, _, _, _, private = fixture
    builder = EmbeddingBuilder(ctx.sessions, ctx.model)
    await builder.build(["重复内容"], ctx.scopes)
    _, counts = await builder.build(["重复内容", "重复内容"], ctx.scopes)
    assert counts["embedding_cache_hits"] == 2 and counts["embedding_calls"] == 0
    assert (await builder.build(["重复内容"], frozenset({str(private)})))[1]["embedding_calls"] == 1
    ctx.model.embedding_profile = "b" * 64
    assert (await builder.build(["重复内容"], ctx.scopes))[1]["embedding_calls"] == 1


async def test_changed_dimension_rejected_before_cache_write(fixture):
    ctx, conn, *_ = fixture
    builder = EmbeddingBuilder(ctx.sessions, ctx.model)
    await builder.build(["one"], ctx.scopes)

    async def wrong_dimension(texts):
        return [[1.0, 2.0] for _ in texts]

    ctx.model.embed = wrong_dimension
    with pytest.raises(ValueError, match="EMBEDDING_PROFILE_DIMENSION_CHANGED"):
        await builder.build(["two"], ctx.scopes)
    assert (
        await conn.execute(text("SELECT count(*) FROM knowledge_embedding_cache WHERE dimension=2"))
    ).scalar_one() == 0


@pytest.mark.parametrize(
    "table,flag",
    [
        ("knowledge_documents", "active"),
        ("document_versions", "searchable"),
        ("knowledge_chunks", "active"),
    ],
)
async def test_cached_vector_still_checks_current_activation(fixture, table, flag):
    ctx, conn, _, document, version, _ = fixture
    await rebuild(ctx.sessions, ctx.model, ctx.scopes)
    strategy = VectorRetrieverStrategy()
    assert (await strategy.execute(query("商品"), StrategySelection(id="vector"), ctx)).rankings[0]
    condition = "document_version_id=:id" if table == "knowledge_chunks" else "id=:id"
    await conn.execute(
        text(f"UPDATE {table} SET {flag}=false WHERE {condition}"),
        {"id": document if table == "knowledge_documents" else version},
    )
    assert not (
        await strategy.execute(query("商品"), StrategySelection(id="vector"), ctx)
    ).rankings[0]
    assert ctx.metrics["query_cache_hits"] == 1


@pytest.mark.parametrize("table", ["knowledge_chunks", "document_versions", "knowledge_documents"])
async def test_scope_restrictions_and_cached_query_cannot_bypass_revocation(fixture, table):
    ctx, conn, _, document, version, private = fixture
    await rebuild(ctx.sessions, ctx.model, ctx.scopes)
    vector = VectorRetrieverStrategy()
    assert (await vector.execute(query("商品"), StrategySelection(id="vector"), ctx)).rankings[0]
    condition = "document_version_id=:id" if table == "knowledge_chunks" else "id=:id"
    await conn.execute(
        text(f"UPDATE {table} SET scope_ids=array_append(scope_ids,:private) WHERE {condition}"),
        {"id": document if table == "knowledge_documents" else version, "private": private},
    )
    assert not (await vector.execute(query("商品"), StrategySelection(id="vector"), ctx)).rankings[
        0
    ]
    assert ctx.metrics["query_cache_hits"] == 1
    assert not (
        await BM25RetrieverStrategy().execute(query("商品"), StrategySelection(id="bm25"), ctx)
    ).rankings[0]


async def test_neighbors_bound_to_section_version_and_authorization(fixture):
    ctx, conn, ids, document, _, private = fixture
    await rebuild(ctx.sessions, ctx.model, ctx.scopes)
    anchors = (
        await BM25RetrieverStrategy().execute(query("上架"), StrategySelection(id="bm25"), ctx)
    ).rankings[0]
    rows = await neighbor_rows(ctx.sessions, anchors, ctx.scopes, 2)
    assert [row["id"] for row in rows] == [ids[1]]
    await conn.execute(
        text("UPDATE knowledge_chunks SET scope_ids=array_append(scope_ids,:p) WHERE id=:id"),
        {"p": private, "id": ids[1]},
    )
    assert not await neighbor_rows(ctx.sessions, anchors, ctx.scopes, 2)
    await conn.execute(
        text("UPDATE knowledge_documents SET active=false WHERE id=:d"), {"d": document}
    )
    assert not await neighbor_rows(ctx.sessions, anchors, ctx.scopes, 2)


async def test_metrics_exist_without_public_activity_writer(fixture):
    ctx, *_ = fixture
    await AdvancedRetrievalWorkflow._publish_activity(
        ctx,
        "retrieve-vector",
        stage="RETRIEVAL",
        status="DEGRADED",
        summary="test",
        strategy_id="vector",
        metrics={"durationMs": 12},
        degradation_code="VECTOR_RETRIEVAL_FAILED",
    )
    assert ctx.metrics == {"vector_durationMs": 12, "vector_degraded": 1}
