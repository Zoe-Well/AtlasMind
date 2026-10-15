"""Explicit maintenance: rebuild projections, preserving canonical text and citations."""

from __future__ import annotations

import argparse
import asyncio
import json
from uuid import UUID

from sqlalchemy import text

from atlasmind.infrastructure.database import create_session_factory
from atlasmind.ingestion.embeddings import EmbeddingBuilder, model_profile, vector_literal
from atlasmind.retrieval.lexical_pg import LEXICAL_VERSION, BasicMultilingualTokenizer
from atlasmind.runtime import create_runtime
from atlasmind.settings import load_settings


async def rebuild(sessions, model, scopes: frozenset[str]) -> dict[str, int]:
    if not scopes or not model_profile(model):
        raise ValueError("REINDEX_REQUIRES_EXPLICIT_SCOPES_AND_MODEL_PROFILE")
    async with sessions() as session:
        versions = (
            (
                await session.execute(
                    text("""
            SELECT v.id, v.document_id FROM document_versions v
            JOIN knowledge_documents d ON d.active_version_id=v.id AND d.id=v.document_id
            WHERE d.active AND v.searchable
              AND cardinality(d.scope_ids)>0 AND d.scope_ids <@ :scopes
              AND cardinality(v.scope_ids)>0 AND v.scope_ids <@ :scopes
            ORDER BY v.id
        """),
                    {"scopes": [UUID(s) for s in scopes]},
                )
            )
            .mappings()
            .all()
        )
    totals = {"versions": 0, "chunks": 0, "embedding_calls": 0, "embedding_cache_hits": 0}
    tokenizer = BasicMultilingualTokenizer()
    for version in versions:
        async with sessions() as session:
            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT id,content,scope_ids FROM knowledge_chunks "
                            "WHERE document_version_id=:v AND active ORDER BY ordinal"
                        ),
                        {"v": version["id"]},
                    )
                )
                .mappings()
                .all()
            )
        if not rows:
            continue
        # Cache reuse uses the actual chunk scopes, never the operator's larger scope set.
        vectors = {}
        metrics = {"embedding_calls": 0, "embedding_cache_hits": 0}
        groups = {frozenset(map(str, row["scope_ids"])) for row in rows}
        if any(not group or not group.issubset(scopes) for group in groups):
            raise ValueError("REINDEX_CHUNK_SCOPE_MISMATCH")
        for group in groups:
            selected = [r for r in rows if frozenset(map(str, r["scope_ids"])) == group]
            values, counts = await EmbeddingBuilder(sessions, model).build(
                [r["content"] for r in selected], group
            )
            vectors.update({r["id"]: v for r, v in zip(selected, values, strict=True)})
            for key in metrics:
                metrics[key] += counts[key]
        async with sessions() as session, session.begin():
            # Same document-first lock order as activation/revocation.
            current = (
                (
                    await session.execute(
                        text(
                            "SELECT active_version_id,active,scope_ids FROM knowledge_documents "
                            "WHERE id=:d FOR UPDATE"
                        ),
                        {"d": version["document_id"]},
                    )
                )
                .mappings()
                .one()
            )
            version_row = (
                (
                    await session.execute(
                        text(
                            "SELECT searchable,scope_ids,build_profile FROM document_versions "
                            "WHERE id=:v FOR UPDATE"
                        ),
                        {"v": version["id"]},
                    )
                )
                .mappings()
                .one()
            )
            locked = (
                (
                    await session.execute(
                        text(
                            "SELECT id,content,scope_ids FROM knowledge_chunks "
                            "WHERE document_version_id=:v AND active ORDER BY ordinal FOR UPDATE"
                        ),
                        {"v": version["id"]},
                    )
                )
                .mappings()
                .all()
            )
            if (
                not current["active"]
                or current["active_version_id"] != version["id"]
                or not version_row["searchable"]
                or locked != rows
                or any(
                    not row["scope_ids"] or not set(map(str, row["scope_ids"])).issubset(scopes)
                    for row in (current, version_row)
                )
            ):
                raise ValueError("REINDEX_SOURCE_CHANGED_RETRY_WHEN_IDLE")
            for row in rows:
                await session.execute(
                    text("""
                    UPDATE knowledge_chunks SET embedding=CAST(:vector AS vector),
                        embedding_profile=:profile, lexical_version=:lexical,
                        search_vector=to_tsvector('simple',:tokens) WHERE id=:id
                """),
                    {
                        "id": row["id"],
                        "vector": vector_literal(vectors[row["id"]]),
                        "profile": model_profile(model),
                        "lexical": LEXICAL_VERSION,
                        "tokens": tokenizer.document(row["content"]),
                    },
                )
            profile = dict(
                version_row["build_profile"]
                or {"parser": "legacy-unknown", "chunker": "legacy-unknown"}
            )
            profile.update(
                {
                    "embedding_profile": model_profile(model),
                    "embedding": getattr(model, "embedding_descriptor", {}),
                    "dimension": len(next(iter(vectors.values()))),
                    "lexical": LEXICAL_VERSION,
                    "projection_rebuild_metrics": metrics,
                }
            )
            await session.execute(
                text(
                    "UPDATE document_versions SET build_profile=CAST(:profile AS jsonb) WHERE id=:v"
                ),
                {"v": version["id"], "profile": json.dumps(profile)},
            )
        totals["versions"] += 1
        totals["chunks"] += len(rows)
        for key in metrics:
            totals[key] += metrics[key]
    return totals


async def main(scopes: frozenset[str]) -> None:
    runtime = create_runtime(load_settings())
    try:
        print(json.dumps(await rebuild(create_session_factory(runtime.engine), runtime.ai, scopes)))
    finally:
        await runtime.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", action="append", required=True, type=UUID)
    args = parser.parse_args()
    asyncio.run(main(frozenset(map(str, args.scope))))
