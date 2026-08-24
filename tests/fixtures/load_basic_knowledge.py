"""Test-only deterministic knowledge fixtures."""

from atlasmind.domain.knowledge import KnowledgeChunk


def load_basic_knowledge() -> list[KnowledgeChunk]:
    return [
        KnowledgeChunk(
            id="chunk-public-refund",
            document_version_id="version-public-refund",
            ordinal=0,
            content="Refund requests are accepted within 30 days of purchase.",
            locator="page=1;paragraph=2",
            scope_ids=frozenset({"public"}),
            generation=1,
        ),
        KnowledgeChunk(
            id="chunk-secret",
            document_version_id="version-secret",
            ordinal=0,
            content="FORBIDDEN_MARKER internal refund override.",
            locator="page=9;paragraph=1",
            scope_ids=frozenset({"restricted"}),
            generation=1,
        ),
    ]
