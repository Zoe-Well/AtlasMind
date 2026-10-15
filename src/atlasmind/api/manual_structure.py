"""Safe structural document nodes aligned to the existing ingestion paragraph contract."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from markdown_it import MarkdownIt

from atlasmind.ingestion.chunking import DeterministicChunker
from atlasmind.ingestion.parsers import MarkdownParser, ParsingFailed

ALLOWED = {
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "ul",
    "ol",
    "li",
    "strong",
    "em",
    "code",
    "pre",
    "blockquote",
    "table",
    "thead",
    "tbody",
    "tr",
    "td",
    "th",
    "br",
    "hr",
}


def structured_document(
    raw: bytes | None, media_type: str, paragraphs: list[str]
) -> dict[str, Any]:
    """Return an allowlisted node tree, never provider HTML/URLs/event handlers."""
    fallback = {
        "format": "text",
        "nodes": [
            {"tag": "p", "children": [{"text": text, "paragraph": i + 1}]}
            for i, text in enumerate(paragraphs)
        ],
    }
    if raw is None or media_type not in {"text/markdown", "text/x-markdown"}:
        return fallback
    try:
        # New documents use semantic blocks; legacy documents keep the exact renderer below.
        blocks = [
            block
            for chunk in DeterministicChunker().canonical_chunks(MarkdownParser().parse(raw))
            for block in chunk
        ]
        if [block.text for block in blocks] == paragraphs:
            nodes = []
            for index, block in enumerate(blocks, 1):
                tag = (
                    block.kind
                    if block.kind in {"p", "pre", "li", "h1", "h2", "h3", "h4", "h5", "h6"}
                    else "p"
                )
                node = {"tag": tag, "children": [{"text": block.text, "paragraph": index}]}
                nodes.append({"tag": "ul", "children": [node]} if tag == "li" else node)
            return {"format": "markdown", "nodes": nodes}
        soup = BeautifulSoup(MarkdownIt().render(raw.decode("utf-8")), "html.parser")
        # Ingestion uses this exact normalization. Refuse inaccurate anchors if it differs.
        parsed = [
            " ".join(line.split()) for line in soup.get_text("\n").splitlines() if line.strip()
        ]
        if parsed != paragraphs:
            return fallback
        counter = 0
        budget = 0
        assigned = []

        def visit(node: Any, depth: int = 0) -> list[dict[str, Any]]:
            nonlocal counter, budget
            budget += 1
            if budget > 5000 or depth > 30:
                raise ValueError("document structure limit")
            if isinstance(node, Comment):
                return []
            if isinstance(node, NavigableString):
                result = []
                for part in str(node).splitlines(keepends=True):
                    normalized = " ".join(part.split())
                    if normalized:
                        counter += 1
                        assigned.append(normalized)
                    result.append({"text": part, "paragraph": counter if normalized else 0})
                return result
            if not isinstance(node, Tag) or node.name in {
                "script",
                "style",
                "noscript",
                "template",
            }:
                return []
            children = [out for child in node.children for out in visit(child, depth + 1)]
            # Links and arbitrary raw HTML become inert text containers. No attributes survive.
            return [{"tag": node.name if node.name in ALLOWED else "span", "children": children}]

        nodes = [out for node in soup.children for out in visit(node)]
        if assigned != paragraphs:
            return fallback
        return {"format": "markdown", "nodes": nodes}
    except (UnicodeError, ValueError, RecursionError, ParsingFailed):
        return fallback


def content_digest(text: str) -> str:
    return "sha256:" + sha256(text.encode()).hexdigest()
