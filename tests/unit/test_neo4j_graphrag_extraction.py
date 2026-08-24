"""Neo4j GraphRAG extraction adapter tests."""

from __future__ import annotations

import json

import pytest

from atlasmind.infrastructure.neo4j_graphrag_extraction import Neo4jGraphRAGExtractor


class StubChatCompletion:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def complete(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
        max_tokens: int = 1800,
    ) -> str:
        del system_instruction, max_tokens
        self.prompts.append(prompt)
        return json.dumps(
            {
                "nodes": [
                    {
                        "id": "0",
                        "label": "Product",
                        "properties": {"name": "AtlasMind"},
                    },
                    {
                        "id": "1",
                        "label": "Database",
                        "properties": {"name": "PostgreSQL", "aliases": ["Postgres"]},
                    },
                ],
                "relationships": [
                    {
                        "type": "USES",
                        "start_node_id": "0",
                        "end_node_id": "1",
                        "properties": {"confidence": 0.97},
                    }
                ],
            }
        )


@pytest.mark.asyncio
async def test_official_extractor_maps_to_atlasmind_graph_contract() -> None:
    chat = StubChatCompletion()
    extractor = Neo4jGraphRAGExtractor(chat, model_name="test-chat")

    result = await extractor.extract_graph(
        "AtlasMind uses PostgreSQL.",
        locator="paragraph:1",
    )

    assert [entity.name for entity in result.entities] == ["AtlasMind", "PostgreSQL"]
    assert result.entities[1].aliases == ("Postgres",)
    assert result.relations[0].source == "AtlasMind"
    assert result.relations[0].target == "PostgreSQL"
    assert result.relations[0].relation_type == "USES"
    assert result.relations[0].confidence == 0.97
    assert result.extraction_version.startswith("neo4j-graphrag-")
    assert "untrusted data" in chat.prompts[0]


@pytest.mark.asyncio
async def test_official_extractor_skips_model_call_for_empty_content() -> None:
    chat = StubChatCompletion()
    extractor = Neo4jGraphRAGExtractor(chat, model_name="test-chat")

    result = await extractor.extract_graph("  ", locator="paragraph:1")

    assert result.entities == ()
    assert result.relations == ()
    assert chat.prompts == []
