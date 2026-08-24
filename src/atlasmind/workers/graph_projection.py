"""Idempotent graph extraction and projection worker."""

from __future__ import annotations

from dataclasses import dataclass

from atlasmind.graph.entity_resolution import EntityResolver
from atlasmind.graph.extraction import GraphExtractor
from atlasmind.graph.models import (
    EntityMention,
    GraphEntity,
    GraphRelation,
    GraphRepository,
    RelationEvidence,
)
from atlasmind.infrastructure.neo4j_projection import InMemoryNeo4jProjection


@dataclass(frozen=True, slots=True)
class GraphSourceChunk:
    id: str
    document_version_id: str
    content: str
    locator: str
    scope_ids: frozenset[str]
    generation: int


@dataclass(frozen=True, slots=True)
class GraphProjectionResult:
    generation: int
    entity_count: int
    relation_count: int


class GraphProjectionWorker:
    def __init__(
        self,
        repository: GraphRepository,
        extractor: GraphExtractor,
        projection: InMemoryNeo4jProjection,
    ) -> None:
        self._repository = repository
        self._extractor = extractor
        self._projection = projection
        self._resolver = EntityResolver()

    def process(self, chunks: tuple[GraphSourceChunk, ...]) -> GraphProjectionResult:
        if not chunks:
            return GraphProjectionResult(0, 0, 0)
        generation = max(chunk.generation for chunk in chunks)
        for chunk in chunks:
            extracted = self._extractor.extract(chunk.content, locator=chunk.locator)
            resolved: dict[str, GraphEntity] = {}
            for entity_item in extracted.entities:
                entity = self._resolver.resolve(
                    entity_item.name,
                    tuple(self._repository.entities.values()),
                )
                if entity is None:
                    entity = GraphEntity(entity_item.name, entity_item.entity_type)
                    self._repository.add_entity(entity)
                resolved[entity_item.name] = entity
                self._repository.add_mention(
                    EntityMention(
                        entity_id=entity.id,
                        chunk_id=chunk.id,
                        document_version_id=chunk.document_version_id,
                        surface=entity_item.surface,
                        locator=chunk.locator,
                        confidence=entity_item.confidence,
                        scope_ids=chunk.scope_ids,
                        extraction_version=extracted.extraction_version,
                    )
                )
            for relation_item in extracted.relations:
                relation = GraphRelation(
                    source_entity_id=resolved[relation_item.source_name].id,
                    target_entity_id=resolved[relation_item.target_name].id,
                    relation_type=relation_item.relation_type,
                    confidence=relation_item.confidence,
                    extraction_version=extracted.extraction_version,
                )
                evidence = RelationEvidence(
                    relation_id=relation.id,
                    chunk_id=chunk.id,
                    document_version_id=chunk.document_version_id,
                    locator=chunk.locator,
                    scope_ids=chunk.scope_ids,
                    generation=chunk.generation,
                )
                self._repository.add_relation(relation, evidence)
        written = self._projection.rebuild(
            tuple(self._repository.entities.values()),
            tuple(self._repository.relations.values()),
            tuple(self._repository.evidence.values()),
            generation=generation,
        )
        return GraphProjectionResult(generation, len(self._repository.entities), written)
