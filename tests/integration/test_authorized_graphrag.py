"""Authorized multi-hop graph projection, retrieval, and cited answers."""

from __future__ import annotations

import pytest

from atlasmind.application.graph_answers import compose_graph_answer
from atlasmind.graph.extraction import DeterministicGraphExtractor
from atlasmind.graph.models import GraphRepository
from atlasmind.infrastructure.neo4j_projection import InMemoryNeo4jProjection
from atlasmind.retrieval.graph_contracts import (
    GraphPath,
    GraphPathEdge,
    GraphPathNode,
    GraphRetrievalRequest,
)
from atlasmind.retrieval.graph_neo4j import GraphPathAuthorizer
from atlasmind.workers.graph_projection import GraphProjectionWorker, GraphSourceChunk


@pytest.mark.integration
def test_multi_hop_graph_answer_preserves_generation_scope_and_source_citations() -> None:
    repository = GraphRepository()
    projection = InMemoryNeo4jProjection()
    worker = GraphProjectionWorker(
        repository,
        DeterministicGraphExtractor(),
        projection,
    )

    result = worker.process(
        (
            GraphSourceChunk(
                id="chunk-1",
                document_version_id="version-1",
                content=(
                    "Refund Service -[WRITES_TO]-> Refund Queue\n"
                    "Refund Queue -[OWNED_BY]-> Payments Team"
                ),
                locator="page=2;paragraph=3",
                scope_ids=frozenset({"scope-public"}),
                generation=4,
            ),
        )
    )

    assert result.generation == 4
    assert result.entity_count == 3
    assert result.relation_count == 2
    entities = {item.canonical_name: item for item in repository.entities.values()}
    relations = {item.relation_type: item for item in repository.relations.values()}
    evidence = {item.relation_id: item for item in repository.evidence.values()}
    path = GraphPath(
        nodes=(
            GraphPathNode(
                entities["Refund Service"].id,
                "Refund Service",
                frozenset({"scope-public"}),
            ),
            GraphPathNode(
                entities["Refund Queue"].id,
                "Refund Queue",
                frozenset({"scope-public"}),
            ),
            GraphPathNode(
                entities["Payments Team"].id,
                "Payments Team",
                frozenset({"scope-public"}),
            ),
        ),
        edges=tuple(
            GraphPathEdge(
                relation.id,
                relation.source_entity_id,
                relation.target_entity_id,
                relation.relation_type,
                evidence[relation.id].document_version_id,
                evidence[relation.id].locator,
                evidence[relation.id].scope_ids,
            )
            for relation in (relations["WRITES_TO"], relations["OWNED_BY"])
        ),
    )
    authorized = GraphPathAuthorizer().authorize(
        GraphRetrievalRequest(
            "Who ultimately owns the queue related to Refund Service?",
            frozenset({"scope-public"}),
            3,
            20,
        ),
        (path,),
        active_version_ids=frozenset({"version-1"}),
    )
    answer = compose_graph_answer(authorized)

    assert answer.evidence_status == "SUPPORTED"
    assert "Refund Service WRITES_TO Refund Queue" in answer.text
    assert "Refund Queue OWNED_BY Payments Team" in answer.text
    assert len(answer.citations) == 2
    assert {citation.locator for citation in answer.citations} == {"page=2;paragraph=3"}


@pytest.mark.integration
def test_revoked_generation_returns_insufficient_evidence_without_path_details() -> None:
    path = GraphPath(
        nodes=(
            GraphPathNode("entity-a", "A", frozenset({"scope-public"})),
            GraphPathNode("entity-b", "B", frozenset({"scope-public"})),
        ),
        edges=(
            GraphPathEdge(
                "relation-secret",
                "entity-a",
                "entity-b",
                "CONNECTED_TO",
                "version-revoked",
                "paragraph=1",
                frozenset({"scope-public"}),
            ),
        ),
    )
    result = GraphPathAuthorizer().authorize(
        GraphRetrievalRequest("How is A related to B?", frozenset({"scope-public"}), 2, 10),
        (path,),
        active_version_ids=frozenset(),
    )

    answer = compose_graph_answer(result)

    assert answer.evidence_status == "INSUFFICIENT_EVIDENCE"
    assert answer.citations == ()
    assert "relation-secret" not in answer.text
