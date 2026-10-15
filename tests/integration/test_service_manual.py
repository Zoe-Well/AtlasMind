"""Real PostgreSQL manual reads; dedicated synthetic rows are always rolled back."""

import os
from hashlib import sha256
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from atlasmind.api.service_manual import ManualListRequest, ManualReader, ManualReadRequest

pytestmark = pytest.mark.skipif(
    not os.getenv("ATLASMIND_MANUAL_TEST_DB"), reason="explicit local database required"
)


@pytest.fixture
async def fixture():
    engine = create_async_engine(os.environ["ATLASMIND_MANUAL_TEST_DB"])
    async with engine.connect() as conn:
        transaction = await conn.begin()
        try:
            scope, other, document, version, chunk1, chunk2 = [uuid4() for _ in range(6)]
            await conn.execute(
                text(
                    "INSERT INTO knowledge_documents(id,title,source_key,scope_ids) "
                    "VALUES (:d,'合成使用手册',:key,:scopes)"
                ),
                {"d": document, "key": str(document), "scopes": [scope]},
            )
            await conn.execute(
                text(
                    "INSERT INTO document_versions(id,document_id,content_digest,scope_ids,"
                    "searchable,generation,created_at) VALUES (:v,:d,:digest,:scopes,true,1,now())"
                ),
                {"v": version, "d": document, "digest": "sha256:" + "f" * 64, "scopes": [scope]},
            )
            await conn.execute(
                text("UPDATE knowledge_documents SET active_version_id=:v WHERE id=:d"),
                {"v": version, "d": document},
            )
            for i, chunk in enumerate([chunk1, chunk2]):
                await conn.execute(
                    text(
                        "INSERT INTO knowledge_chunks(id,document_version_id,ordinal,content,"
                        "locator,scope_ids,generation) "
                        "VALUES (:c,:v,:i,:content,:locator,:scopes,1)"
                    ),
                    {
                        "c": chunk,
                        "v": version,
                        "i": i,
                        "content": f"正文{i + 1}\n<script>仅作为文字</script>",
                        "locator": f"paragraph={i * 2 + 1}-{i * 2 + 2}",
                        "scopes": [scope],
                    },
                )
            reader = ManualReader(
                async_sessionmaker(conn, join_transaction_mode="create_savepoint"),
                frozenset({str(scope)}),
            )
            citation = dict(
                document_id=document,
                version_id=version,
                chunk_id=chunk2,
                digest="sha256:"
                + sha256("正文2\n<script>仅作为文字</script>".encode()).hexdigest(),
            )
            yield reader, conn, citation, other
        finally:
            await transaction.rollback()
    await engine.dispose()


async def test_manual_list_read_exact_reference_and_page(fixture):
    reader, _, ref, _ = fixture
    docs = await reader.documents(ManualListRequest(query="合成"))
    assert len(docs["data"]) == 1
    result = await reader.read(ManualReadRequest(**ref))
    assert result["page"] == 2 and result["total_pages"] == 2
    assert result["chunks"][0]["chunk_id"] == result["highlight_chunk_id"] == str(ref["chunk_id"])
    assert result["chunks"][0]["content"].startswith("正文2")
    earlier = await reader.read(ManualReadRequest(**ref, page=1))
    assert earlier["chunks"][0]["chunk_id"] != earlier["highlight_chunk_id"]
    assert (await reader.documents(ManualListRequest(query="%")))["data"] == []


@pytest.mark.parametrize("change", ["version_id", "chunk_id", "digest"])
async def test_wrong_or_obsolete_citation_never_reads_current_text(fixture, change):
    reader, _, ref, _ = fixture
    ref[change] = "sha256:" + "0" * 64 if change == "digest" else uuid4()
    with pytest.raises(HTTPException) as error:
        await reader.read(ManualReadRequest(**ref))
    assert error.value.status_code == 409


@pytest.mark.parametrize(
    "table,field",
    [
        ("knowledge_documents", "document_id"),
        ("document_versions", "version_id"),
        ("knowledge_chunks", "chunk_id"),
    ],
)
async def test_private_and_mixed_scope_hidden_at_every_layer(fixture, table, field):
    reader, conn, ref, other = fixture
    await conn.execute(
        text(f"UPDATE {table} SET scope_ids=array_append(scope_ids,:other) WHERE id=:id"),
        {"other": other, "id": ref[field]},
    )
    with pytest.raises(HTTPException) as error:
        await reader.read(ManualReadRequest(**ref))
    assert error.value.status_code in (404, 409)
    if table != "knowledge_chunks":
        assert (await reader.documents(ManualListRequest()))["data"] == []


async def test_revocation_hides_list_and_body(fixture):
    reader, conn, ref, _ = fixture
    await conn.execute(
        text("UPDATE knowledge_documents SET active=false WHERE id=:d"), {"d": ref["document_id"]}
    )
    assert (await reader.documents(ManualListRequest()))["data"] == []
    with pytest.raises(HTTPException) as error:
        await reader.read(ManualReadRequest(**ref))
    assert error.value.status_code == 404


async def test_full_document_preserves_context_and_distinguishes_reference_from_quote(fixture):
    reader, _, ref, _ = fixture
    legacy = await reader.read(ManualReadRequest(**ref, view="document"))
    assert legacy["highlight"] == {"start": 3, "end": 4, "mode": "reference"}
    assert len(legacy["nodes"]) == 4
    precise = await reader.read(
        ManualReadRequest(
            **ref,
            view="document",
            paragraph_start=3,
            paragraph_end=3,
            quote_digest="sha256:" + sha256("正文2".encode()).hexdigest(),
        )
    )
    assert precise["highlight"] == {"start": 3, "end": 3, "mode": "precise"}


@pytest.mark.parametrize(
    "start,end,digest", [(2, 3, sha256("正文2".encode()).hexdigest()), (3, 3, "0" * 64)]
)
async def test_precise_range_or_quote_tampering_rejected(fixture, start, end, digest):
    reader, _, ref, _ = fixture
    with pytest.raises(HTTPException) as error:
        await reader.read(
            ManualReadRequest(
                **ref,
                view="document",
                paragraph_start=start,
                paragraph_end=end,
                quote_digest="sha256:" + digest,
            )
        )
    assert error.value.status_code == 409


async def test_full_document_refuses_partial_scope_visibility(fixture):
    reader, conn, ref, other = fixture
    await conn.execute(
        text("UPDATE knowledge_chunks SET scope_ids=array_append(scope_ids,:other) WHERE id=:id"),
        {"other": other, "id": ref["chunk_id"]},
    )
    with pytest.raises(HTTPException) as error:
        await reader.read(ManualReadRequest(document_id=ref["document_id"], view="document"))
    assert error.value.status_code == 404


async def test_semantic_markdown_chunks_read_with_exact_quote_after_persistence(fixture):
    from atlasmind.ingestion.chunking import DeterministicChunker
    from atlasmind.ingestion.parsers import MarkdownParser

    reader, conn, ref, _ = fixture
    raw = (
        "# Returns\n\n## Conditions\n\n"
        + "Regular returns require proof. " * 100
        + "\n\n| Type | Days |\n| --- | --- |\n| Custom | 0 |\n"
    ).encode()

    class Objects:
        async def get_bytes(self, key):
            assert key == "synthetic/semantic.md"
            return raw

    reader.object_store = Objects()
    scope_ids = (
        await conn.execute(
            text("SELECT scope_ids FROM document_versions WHERE id=:v"), {"v": ref["version_id"]}
        )
    ).scalar_one()
    generated = DeterministicChunker().chunk(
        MarkdownParser().parse(raw),
        document_version_id=str(ref["version_id"]),
        scope_ids=frozenset(map(str, scope_ids)),
        generation=1,
    )
    await conn.execute(
        text("DELETE FROM knowledge_chunks WHERE document_version_id=:v"), {"v": ref["version_id"]}
    )
    for chunk in generated:
        await conn.execute(
            text(
                "INSERT INTO knowledge_chunks"
                "(id,document_version_id,ordinal,content,locator,scope_ids,generation) "
                "VALUES (:id,:v,:n,:content,:locator,:scopes,1)"
            ),
            {
                "id": chunk.id,
                "v": ref["version_id"],
                "n": chunk.ordinal,
                "content": chunk.content,
                "locator": chunk.locator,
                "scopes": scope_ids,
            },
        )
    await conn.execute(
        text(
            "UPDATE document_versions SET object_key='synthetic/semantic.md',"
            "media_type='text/markdown',"
            "size_bytes=:size,content_digest=:digest WHERE id=:v"
        ),
        {"size": len(raw), "digest": "sha256:" + sha256(raw).hexdigest(), "v": ref["version_id"]},
    )
    last = generated[-1]
    paragraph = sum(len(c.content.splitlines()) for c in generated)
    request = ManualReadRequest(
        document_id=ref["document_id"],
        version_id=ref["version_id"],
        chunk_id=last.id,
        digest=last.content_digest,
        view="document",
        paragraph_start=paragraph,
        paragraph_end=paragraph,
        quote_digest="sha256:" + sha256(last.content.splitlines()[-1].encode()).hexdigest(),
    )
    result = await reader.read(request)
    assert result["format"] == "markdown"
    assert result["highlight"] == {"start": paragraph, "end": paragraph, "mode": "precise"}
    assert "Custom" in str(result["nodes"])
    with pytest.raises(HTTPException) as error:
        await reader.read(request.model_copy(update={"quote_digest": "sha256:" + "0" * 64}))
    assert error.value.status_code == 409
