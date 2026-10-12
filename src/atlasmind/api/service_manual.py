"""Bounded, read-only manual over the same active chunks used by customer service."""

from __future__ import annotations

import json
import re
from hashlib import sha256
from typing import Any, Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text

from atlasmind.api.manual_structure import content_digest, structured_document


class ManualListRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(default="", max_length=100)
    page: int = Field(default=1, ge=1, le=10000, strict=True)


class ManualReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: UUID
    version_id: UUID | None = None
    chunk_id: UUID | None = None
    digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    page: int | None = Field(default=None, ge=1, le=100000, strict=True)
    view: Literal["chunk", "document"] = "chunk"
    paragraph_start: int | None = Field(default=None, ge=1, strict=True)
    paragraph_end: int | None = Field(default=None, ge=1, strict=True)
    quote_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def complete_reference(self) -> ManualReadRequest:
        if (self.chunk_id is None) != (self.digest is None):
            raise ValueError("chunk and digest must be supplied together")
        if self.chunk_id is not None and self.version_id is None:
            raise ValueError("a citation must pin its document version")
        precise = (self.paragraph_start, self.paragraph_end, self.quote_digest)
        if any(v is not None for v in precise) and (
            any(v is None for v in precise)
            or self.view != "document"
            or self.chunk_id is None
            or self.paragraph_end < self.paragraph_start
        ):
            raise ValueError("complete paragraph reference required")
        return self


# All three scope filters are deliberate: a mixed-scope document cannot be browsed.
VISIBLE = """
    FROM knowledge_documents d
    JOIN document_versions v ON v.id = d.active_version_id
    JOIN knowledge_chunks c ON c.document_version_id = v.id
    WHERE d.active AND v.searchable AND c.active
      AND cardinality(d.scope_ids) > 0 AND d.scope_ids <@ :scopes
      AND cardinality(v.scope_ids) > 0 AND v.scope_ids <@ :scopes
      AND cardinality(c.scope_ids) > 0 AND c.scope_ids <@ :scopes
"""


class ManualReader:
    def __init__(self, sessions: Any, scopes: frozenset[str], object_store: Any = None) -> None:
        self.sessions = sessions
        self.params = {"scopes": [UUID(scope) for scope in scopes]}
        self.object_store = object_store

    async def documents(self, body: ManualListRequest) -> dict[str, Any]:
        params = {**self.params, "query": body.query, "offset": (body.page - 1) * 20}
        async with self.sessions() as session:
            # Window count and page are one statement/snapshot.
            result = await session.execute(
                text(
                    """
                WITH docs AS (
                    SELECT DISTINCT d.id AS document_id, d.title, v.id AS version_id
            """
                    + VISIBLE
                    + """
                      AND strpos(lower(d.title), lower(:query)) > 0
                )
                SELECT *, count(*) OVER () AS total FROM docs
                ORDER BY title, document_id LIMIT 20 OFFSET :offset
            """
                ),
                params,
            )
            rows = list(result.mappings())
        return {
            "data": [
                {
                    "document_id": str(r["document_id"]),
                    "title": r["title"],
                    "version_id": str(r["version_id"]),
                }
                for r in rows
            ],
            "page": body.page,
            "page_size": 20,
            "has_more": bool(rows) and body.page * 20 < rows[0]["total"],
        }

    async def read(self, body: ManualReadRequest) -> dict[str, Any]:
        params = {**self.params, "document": body.document_id}
        async with self.sessions() as session:
            # Lock the active document/version against replacement/revocation while reading.
            meta = (
                (
                    await session.execute(
                        text("""
                SELECT d.id AS document_id, d.title, v.id AS version_id,
                       v.object_key, v.media_type, v.content_digest, v.size_bytes
                FROM knowledge_documents d JOIN document_versions v ON v.id=d.active_version_id
                WHERE d.id=:document AND d.active AND v.searchable
                  AND cardinality(d.scope_ids)>0 AND d.scope_ids <@ :scopes
                  AND cardinality(v.scope_ids)>0 AND v.scope_ids <@ :scopes
                FOR SHARE OF d, v
            """),
                        params,
                    )
                )
                .mappings()
                .first()
            )
            if meta is None:
                raise HTTPException(404, "MANUAL_NOT_AVAILABLE")
            if body.version_id is not None and str(meta["version_id"]) != str(body.version_id):
                raise HTTPException(409, "KNOWLEDGE_SOURCE_CHANGED")
            if body.view == "document":
                return await self.full_document(session, body, meta, params)
            base = VISIBLE + " AND d.id=:document"
            index = list(
                (
                    await session.execute(
                        text("SELECT c.id AS chunk_id, c.ordinal " + base + " ORDER BY c.ordinal"),
                        params,
                    )
                ).mappings()
            )
            if not index:
                raise HTTPException(404, "MANUAL_NOT_AVAILABLE")
            target = next((i for i, r in enumerate(index) if r["chunk_id"] == body.chunk_id), None)
            if body.chunk_id is not None and target is None:
                raise HTTPException(409, "KNOWLEDGE_SOURCE_CHANGED")
            # One chunk per page bounds reads even for large documents, without truncation.
            page = body.page or ((target + 1) if target is not None else 1)
            if page > len(index):
                raise HTTPException(404, "MANUAL_PAGE_NOT_FOUND")
            ids = [index[page - 1]["chunk_id"]]
            if body.chunk_id is not None and body.chunk_id not in ids:
                ids.append(body.chunk_id)
            rows = list(
                (
                    await session.execute(
                        text(
                            "SELECT c.id AS chunk_id, c.content, c.locator "
                            + base
                            + " AND c.id=ANY(:ids) FOR SHARE OF c"
                        ),
                        {**params, "ids": ids},
                    )
                ).mappings()
            )
            lookup = {r["chunk_id"]: r for r in rows}
            if len(lookup) != len(ids):
                raise HTTPException(409, "KNOWLEDGE_SOURCE_CHANGED")
            if body.chunk_id is not None:
                digest = "sha256:" + sha256(lookup[body.chunk_id]["content"].encode()).hexdigest()
                if digest != body.digest:
                    raise HTTPException(409, "KNOWLEDGE_SOURCE_CHANGED")
            row = lookup[ids[0]]
            result = {
                "document_id": str(meta["document_id"]),
                "title": meta["title"],
                "version_id": str(meta["version_id"]),
                "page": page,
                "total_pages": len(index),
                "highlight_chunk_id": str(body.chunk_id or ""),
                "chunks": [
                    {
                        "chunk_id": str(row["chunk_id"]),
                        "content": row["content"],
                        "locator": row["locator"],
                    }
                ],
            }
            if len(json.dumps(result, ensure_ascii=False).encode()) > 250000:
                raise HTTPException(413, "MANUAL_CONTENT_TOO_LARGE")
            return result

    async def full_document(
        self, session: Any, body: ManualReadRequest, meta: Any, params: dict[str, Any]
    ) -> dict[str, Any]:
        rows = list(
            (
                await session.execute(
                    text(
                        "SELECT c.id AS chunk_id, c.content, c.locator, c.ordinal "
                        + VISIBLE
                        + " AND d.id=:document ORDER BY c.ordinal LIMIT 501 FOR SHARE OF c"
                    ),
                    params,
                )
            ).mappings()
        )
        total = (
            await session.execute(
                text("SELECT count(*) FROM knowledge_chunks WHERE document_version_id=:version"),
                {"version": meta["version_id"]},
            )
        ).scalar_one()
        if not rows or len(rows) != total:
            raise HTTPException(404, "MANUAL_NOT_AVAILABLE")
        if len(rows) > 500 or sum(len(r["content"].encode()) for r in rows) > 120000:
            raise HTTPException(413, "MANUAL_CONTENT_TOO_LARGE")
        paragraphs: list[str] = []
        ranges = {}
        for row in rows:
            match = re.fullmatch(r"paragraph=(\d+)(?:-(\d+))?", row["locator"])
            lines = row["content"].splitlines()
            if (
                not match
                or int(match[1]) != len(paragraphs) + 1
                or int(match[2] or match[1]) != len(paragraphs) + len(lines)
            ):
                raise HTTPException(409, "KNOWLEDGE_SOURCE_CHANGED")
            ranges[str(row["chunk_id"])] = (len(paragraphs) + 1, len(paragraphs) + len(lines), row)
            paragraphs.extend(lines)
        highlight = None
        if body.chunk_id is not None:
            found = ranges.get(str(body.chunk_id))
            if not found or content_digest(found[2]["content"]) != body.digest:
                raise HTTPException(409, "KNOWLEDGE_SOURCE_CHANGED")
            start, end, _ = found
            mode = "reference"
            if body.paragraph_start is not None:
                if not (start <= body.paragraph_start <= body.paragraph_end <= end):
                    raise HTTPException(409, "KNOWLEDGE_SOURCE_CHANGED")
                start, end = body.paragraph_start, body.paragraph_end
                if content_digest("\n".join(paragraphs[start - 1 : end])) != body.quote_digest:
                    raise HTTPException(409, "KNOWLEDGE_SOURCE_CHANGED")
                mode = "precise"
            highlight = {"start": start, "end": end, "mode": mode}
        raw = None
        if (
            self.object_store is not None
            and meta["object_key"]
            and meta["media_type"] in {"text/markdown", "text/x-markdown"}
            and meta["size_bytes"] <= 120000
        ):
            raw = await self.object_store.get_bytes(meta["object_key"])
            if len(raw) > 120000 or "sha256:" + sha256(raw).hexdigest() != meta["content_digest"]:
                raise HTTPException(409, "KNOWLEDGE_SOURCE_CHANGED")
        structure = structured_document(raw, meta["media_type"], paragraphs)
        result = {
            "document_id": str(meta["document_id"]),
            "title": meta["title"],
            "version_id": str(meta["version_id"]),
            "highlight": highlight,
            **structure,
        }
        if len(json.dumps(result, ensure_ascii=False).encode()) > 250000:
            raise HTTPException(413, "MANUAL_CONTENT_TOO_LARGE")
        return result
