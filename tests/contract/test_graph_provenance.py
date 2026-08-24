"""Graph entities and relations remain bound to immutable source evidence."""

from __future__ import annotations

import pytest

from atlasmind.graph.models import (
    EntityMention,
    GraphEntity,
    GraphRelation,
    RelationEvidence,
    RelationStatus,
)


@pytest.mark.contract
def test_relation_requires_canonical_endpoints_and_traceable_evidence() -> None:
    service = GraphEntity(canonical_name="Refund Service", entity_type="SERVICE")
    queue = GraphEntity(canonical_name="Refund Queue", entity_type="QUEUE")
    relation = GraphRelation(
        source_entity_id=service.id,
        target_entity_id=queue.id,
        relation_type="WRITES_TO",
        confidence=0.94,
        extraction_version="extractor-1",
    )
    mention = EntityMention(
        entity_id=service.id,
        chunk_id="chunk-1",
        document_version_id="version-1",
        surface="refund service",
        locator="page=2;paragraph=3",
        confidence=0.98,
        scope_ids=frozenset({"scope-public"}),
        extraction_version="extractor-1",
    )
    evidence = RelationEvidence(
        relation_id=relation.id,
        chunk_id="chunk-1",
        document_version_id="version-1",
        locator="page=2;paragraph=3",
        scope_ids=frozenset({"scope-public"}),
        generation=2,
    )

    assert relation.status is RelationStatus.ACTIVE
    assert mention.document_version_id == evidence.document_version_id
    assert evidence.locator == "page=2;paragraph=3"


@pytest.mark.contract
def test_invalid_self_relation_missing_scope_and_conflicted_fact_are_rejected() -> None:
    entity = GraphEntity(canonical_name="Refund Service", entity_type="SERVICE")
    with pytest.raises(ValueError, match="distinct endpoints"):
        GraphRelation(
            source_entity_id=entity.id,
            target_entity_id=entity.id,
            relation_type="DEPENDS_ON",
            confidence=0.8,
            extraction_version="extractor-1",
        )
    with pytest.raises(ValueError, match="source scope"):
        RelationEvidence(
            relation_id="relation-1",
            chunk_id="chunk-1",
            document_version_id="version-1",
            locator="paragraph=1",
            scope_ids=frozenset(),
            generation=1,
        )
    conflicted = GraphRelation(
        source_entity_id="entity-1",
        target_entity_id="entity-2",
        relation_type="OWNED_BY",
        confidence=0.5,
        extraction_version="extractor-1",
        status=RelationStatus.CONFLICTED,
    )
    assert conflicted.can_support_fact is False
