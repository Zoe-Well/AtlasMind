"""Rebuildable Neo4j projection records with canonical provenance properties."""

from __future__ import annotations

from dataclasses import dataclass

from atlasmind.graph.models import GraphEntity, GraphRelation, RelationEvidence


@dataclass(frozen=True, slots=True)
class Neo4jNodeProjection:
    canonical_id: str
    name: str
    entity_type: str
    generation: int


@dataclass(frozen=True, slots=True)
class Neo4jEdgeProjection:
    canonical_id: str
    source_id: str
    target_id: str
    relation_type: str
    document_version_id: str
    locator: str
    scope_ids: frozenset[str]
    generation: int


class InMemoryNeo4jProjection:
    def __init__(self) -> None:
        self.nodes: dict[str, Neo4jNodeProjection] = {}
        self.edges: dict[str, Neo4jEdgeProjection] = {}

    def rebuild(
        self,
        entities: tuple[GraphEntity, ...],
        relations: tuple[GraphRelation, ...],
        evidence: tuple[RelationEvidence, ...],
        *,
        generation: int,
    ) -> int:
        evidence_by_relation = {item.relation_id: item for item in evidence}
        for entity in entities:
            self.nodes[entity.id] = Neo4jNodeProjection(
                entity.id,
                entity.canonical_name,
                entity.entity_type,
                generation,
            )
        written = 0
        for relation in relations:
            source = evidence_by_relation.get(relation.id)
            if source is None or not relation.can_support_fact:
                continue
            self.edges[relation.id] = Neo4jEdgeProjection(
                relation.id,
                relation.source_entity_id,
                relation.target_entity_id,
                relation.relation_type,
                source.document_version_id,
                source.locator,
                source.scope_ids,
                generation,
            )
            written += 1
        return written

    def retire_generation(self, generation: int) -> None:
        self.nodes = {
            key: value for key, value in self.nodes.items() if value.generation != generation
        }
        self.edges = {
            key: value for key, value in self.edges.items() if value.generation != generation
        }
