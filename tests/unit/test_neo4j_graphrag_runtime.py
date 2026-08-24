"""Neo4j GraphRAG projection and pre-retrieval authorization tests."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from neo4j_graphrag.retrievers import VectorCypherRetriever

from atlasmind.infrastructure.neo4j_runtime import (
    AtlasMindVectorCypherRetriever,
    GraphProjectionRecord,
    Neo4jRuntime,
)


class FakeRecord:
    def __init__(self, values: dict[str, object]) -> None:
        self._values = values

    def data(self) -> dict[str, object]:
        return self._values


class RecordingRetriever:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def get_search_results(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            records=[
                FakeRecord(
                    {
                        "source": "AtlasMind",
                        "relation_type": "USES",
                        "target": "PostgreSQL",
                        "chunk_id": "chunk-1",
                        "locator": "paragraph:1",
                    }
                )
            ]
        )


def _runtime_without_drivers() -> Neo4jRuntime:
    return object.__new__(Neo4jRuntime)


@pytest.mark.asyncio
async def test_facts_passes_authorized_entity_allowlist_into_framework_retriever(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime_without_drivers()
    retriever = RecordingRetriever()

    async def authorized_ids(**kwargs: object) -> frozenset[str]:
        assert kwargs["scope_ids"] == frozenset({"scope-a"})
        assert kwargs["document_version_ids"] == frozenset({"version-a"})
        return frozenset({"entity-a", "entity-b"})

    async def get_retriever() -> RecordingRetriever:
        return retriever

    async def direct_call(function: Any, *args: object, **kwargs: object) -> object:
        return function(*args, **kwargs)

    monkeypatch.setattr(runtime, "_authorized_entity_ids", authorized_ids)
    monkeypatch.setattr(runtime, "_get_retriever", get_retriever)
    monkeypatch.setattr(
        "atlasmind.infrastructure.neo4j_runtime.asyncio.to_thread",
        direct_call,
    )

    facts = await runtime.facts(
        "AtlasMind uses what?",
        query_embedding=[0.1, 0.2],
        scope_ids=frozenset({"scope-a"}),
        document_version_ids=frozenset({"version-a"}),
    )

    assert facts == ("AtlasMind -[USES]-> PostgreSQL (source=chunk-1 locator=paragraph:1)",)
    assert retriever.calls[0]["filters"] == {"canonical_id": {"$in": ["entity-a", "entity-b"]}}
    assert retriever.calls[0]["query_params"]["scope_ids"] == ["scope-a"]
    assert retriever.calls[0]["query_params"]["version_ids"] == ["version-a"]


@pytest.mark.asyncio
async def test_facts_does_not_call_retriever_without_authorized_entities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime_without_drivers()

    async def no_authorized_ids(**kwargs: object) -> frozenset[str]:
        del kwargs
        return frozenset()

    async def unexpected_retriever() -> RecordingRetriever:
        raise AssertionError("retriever must not run without an authorized entity allow-list")

    monkeypatch.setattr(runtime, "_authorized_entity_ids", no_authorized_ids)
    monkeypatch.setattr(runtime, "_get_retriever", unexpected_retriever)

    facts = await runtime.facts(
        "restricted entity",
        query_embedding=[0.1, 0.2],
        scope_ids=frozenset({"scope-a"}),
        document_version_ids=frozenset({"version-a"}),
    )

    assert facts == ()


def test_projection_uses_framework_graph_with_canonical_ids_and_embeddings() -> None:
    record = GraphProjectionRecord(
        relation_id="relation-a",
        source_id="entity-a",
        source_name="AtlasMind",
        source_type="PRODUCT",
        source_embedding=(0.1, 0.2),
        target_id="entity-b",
        target_name="PostgreSQL",
        target_type="DATABASE",
        target_embedding=(0.3, 0.4),
        relation_type="USES",
        document_version_id="version-a",
        chunk_id="chunk-a",
        locator="paragraph:1",
        scope_ids=("scope-a",),
        generation=1,
        confidence=0.99,
    )

    graph = Neo4jRuntime._to_framework_graph((record,))

    assert {node.id for node in graph.nodes} == {"entity-a", "entity-b"}
    assert graph.nodes[0].embedding_properties["embedding"]
    assert graph.relationships[0].type == "RELATED"
    assert graph.relationships[0].properties["canonical_id"] == "relation-a"
    assert graph.relationships[0].properties["scope_ids"] == ["scope-a"]


def test_retriever_compatibility_maps_framework_index_property(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retriever = object.__new__(AtlasMindVectorCypherRetriever)

    def framework_index_loader(self: object, vector_index_name: str) -> None:
        assert vector_index_name == "atlasmind_entity_embedding"
        self._embedding_node_property = "embedding"

    monkeypatch.setattr(
        VectorCypherRetriever,
        "_fetch_index_infos",
        framework_index_loader,
    )
    retriever._node_embedding_property = None

    retriever._fetch_index_infos("atlasmind_entity_embedding")

    assert retriever._node_embedding_property == "embedding"
