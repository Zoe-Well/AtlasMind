"""Deterministic paragraph-aware chunking with stable source locators."""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256

from atlasmind.domain.common import new_id
from atlasmind.ingestion.parsers import DocumentBlock, ParsedDocument


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
    section_key: str | None = None


class DeterministicChunker:
    def __init__(self, *, max_chars: int = 1_500, max_bytes: int = 4_500) -> None:
        if max_chars < 100:
            raise ValueError("max chars must be at least 100")
        self.max_chars = max_chars
        if max_bytes < 400:
            raise ValueError("max bytes must be at least 400")
        self.max_bytes = max_bytes

    def _fits(self, text: str) -> bool:
        return len(text) <= self.max_chars and len(text.encode("utf-8")) <= self.max_bytes

    def _split(self, text: str, prefix: str) -> list[str]:
        """Split oversized units at sentence boundaries, then words, then characters."""
        parts = []
        while text:
            end = min(len(text), self.max_chars - len(prefix))
            while end and not self._fits(prefix + text[:end]):
                end -= 1
            if not end:
                raise ValueError("chunk context exceeds budget")
            if end < len(text):
                candidates = list(
                    re.finditer(r"[。\uff01\uff1f\uff1b.!?;](?:[”\u2019\"']|\s)*|\s+", text[:end])
                )
                # Prefer complete sentences; avoid tiny fragments from an early delimiter.
                sentence = [m.end() for m in candidates if m[0].strip() and m.end() >= end // 2]
                words = [m.end() for m in candidates if m.end() >= end // 2]
                end = (sentence or words or [end])[-1]
            parts.append(text[:end].strip())
            text = text[end:].strip()
        return parts

    def canonical_chunks(self, parsed: ParsedDocument) -> tuple[tuple[DocumentBlock, ...], ...]:
        """The persisted canonical paragraphs also drive safe manual rendering.

        Context is part of the canonical text and its digest, never hidden metadata
        that could drift from a citation. Old persisted paragraphs remain untouched.
        """
        blocks = parsed.blocks or tuple(DocumentBlock(p) for p in parsed.paragraphs)
        result: list[tuple[DocumentBlock, ...]] = []
        buffer: list[DocumentBlock] = []
        key: tuple[tuple[str, ...], str] | None = None
        context: list[DocumentBlock] = []
        used_context = False

        def flush() -> None:
            nonlocal used_context
            if buffer:
                result.append(tuple(context + buffer))
                buffer.clear()
                used_context = True

        def bounded_label(value: str) -> str:
            # A malicious/very long heading cannot consume the whole chunk budget.
            limit = min(self.max_chars // 3, self.max_bytes // 12)
            return value if len(value) <= limit else "…" + value[-limit + 1 :]

        for block in blocks:
            next_key = (block.heading_path, block.source)
            if next_key != key:
                flush()
                if (
                    context
                    and not used_context
                    and key is not None
                    and next_key[0][: len(key[0])] != key[0]
                ):
                    result.append(tuple(context))
                key = next_key
                used_context = False
                context = []
                if block.heading_path:
                    context.append(
                        DocumentBlock(
                            bounded_label(" > ".join(block.heading_path)),
                            "h2",
                            block.heading_path,
                            block.source,
                        )
                    )
                if block.source:
                    context.append(
                        DocumentBlock(
                            bounded_label(block.source),
                            source=block.source,
                            heading_path=block.heading_path,
                        )
                    )
            # The complete heading path is already present in context.
            if (
                block.kind.startswith("h")
                and block.heading_path
                and len(" > ".join(block.heading_path))
                <= min(self.max_chars // 3, self.max_bytes // 12)
            ):
                continue
            prefix = "\n".join(c.text for c in context)
            if prefix:
                prefix += "\n"
            for part in self._split(block.text, prefix):
                proposed = prefix + "\n".join([b.text for b in buffer] + [part])
                if buffer and not self._fits(proposed):
                    flush()
                buffer.append(DocumentBlock(part, block.kind, block.heading_path, block.source))
        flush()
        if context and not used_context:
            result.append(tuple(context))
        return tuple(result)

    def chunk(
        self,
        parsed: ParsedDocument,
        *,
        document_version_id: str,
        scope_ids: frozenset[str],
        generation: int,
    ) -> tuple[IngestedChunk, ...]:
        chunks: list[IngestedChunk] = []
        start = 1
        for blocks in self.canonical_chunks(parsed):
            end = start + len(blocks) - 1
            content = "\n".join(block.text for block in blocks)
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
                    section_key=sha256(
                        repr((blocks[-1].heading_path, blocks[-1].source)).encode()
                    ).hexdigest(),
                )
            )
            start = end + 1
        return tuple(chunks)
