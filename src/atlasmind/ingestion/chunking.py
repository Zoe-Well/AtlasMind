"""Deterministic paragraph-aware chunking with stable source locators."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from atlasmind.domain.common import new_id
from atlasmind.ingestion.parsers import ParsedDocument


@dataclass(frozen=True, slots=True)
class IngestedChunk:
    id: str
    document_version_id: str
    ordinal: int
    content: str
    locator: str
    language: str
    scope_ids: frozenset[str]
    generation: int
    content_digest: str


class DeterministicChunker:
    def __init__(self, *, max_chars: int = 1_500) -> None:
        if max_chars < 100:
            raise ValueError("max chars must be at least 100")
        self.max_chars = max_chars

    def chunk(
        self,
        parsed: ParsedDocument,
        *,
        document_version_id: str,
        scope_ids: frozenset[str],
        generation: int,
    ) -> tuple[IngestedChunk, ...]:
        chunks: list[IngestedChunk] = []
        buffer: list[str] = []
        start = 1

        def flush(end: int) -> None:
            if not buffer:
                return
            content = "\n".join(buffer)
            locator = f"paragraph={start}" if start == end else f"paragraph={start}-{end}"
            chunks.append(
                IngestedChunk(
                    id=new_id(),
                    document_version_id=document_version_id,
                    ordinal=len(chunks),
                    content=content,
                    locator=locator,
                    language=parsed.language,
                    scope_ids=scope_ids,
                    generation=generation,
                    content_digest=f"sha256:{sha256(content.encode()).hexdigest()}",
                )
            )
            buffer.clear()

        for index, paragraph in enumerate(parsed.paragraphs, start=1):
            proposed = len("\n".join([*buffer, paragraph]))
            if buffer and proposed > self.max_chars:
                flush(index - 1)
                start = index
            buffer.append(paragraph)
        flush(len(parsed.paragraphs))
        return tuple(chunks)
