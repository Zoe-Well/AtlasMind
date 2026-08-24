"""Idempotent lexical and vector projection generation builders."""

from __future__ import annotations

from collections.abc import Iterable

from atlasmind.ingestion.chunking import IngestedChunk
from atlasmind.ingestion.models import Projection, ProjectionKind

REQUIRED_PROJECTIONS = (ProjectionKind.LEXICAL, ProjectionKind.VECTOR)


def build_required_projections(
    *,
    document_version_id: str,
    generation: int,
    chunks: Iterable[IngestedChunk],
    existing: Iterable[Projection],
) -> tuple[Projection, ...]:
    chunk_count = sum(1 for _ in chunks)
    by_key = {(item.kind, item.generation): item for item in existing}
    built: list[Projection] = []
    for kind in REQUIRED_PROJECTIONS:
        key = (kind, generation)
        projection = by_key.get(key) or Projection(
            document_version_id=document_version_id,
            kind=kind,
            generation=generation,
            adapter_version="atlasmind-v1",
        )
        built.append(projection.ready(chunk_count))
    return tuple(built)
