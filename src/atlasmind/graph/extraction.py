"""Entity and relation extraction port with deterministic fixture adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ExtractedEntity:
    name: str
    entity_type: str
    surface: str
    confidence: float


@dataclass(frozen=True, slots=True)
class ExtractedRelation:
    source_name: str
    target_name: str
    relation_type: str
    confidence: float


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    entities: tuple[ExtractedEntity, ...]
    relations: tuple[ExtractedRelation, ...]
    extraction_version: str


class GraphExtractor(Protocol):
    def extract(self, content: str, *, locator: str) -> ExtractionResult: ...


class DeterministicGraphExtractor:
    """Explicit fact syntax: ``Source -[RELATION]-> Target`` per line."""

    version = "deterministic-1"

    def extract(self, content: str, *, locator: str) -> ExtractionResult:
        del locator
        entities: dict[str, ExtractedEntity] = {}
        relations: list[ExtractedRelation] = []
        for line in content.splitlines():
            if "-[" not in line or "]->" not in line:
                continue
            source, remainder = line.split("-[", 1)
            relation_type, target = remainder.split("]->", 1)
            source = source.strip()
            target = target.strip()
            entities.setdefault(source, ExtractedEntity(source, "ENTITY", source, 1.0))
            entities.setdefault(target, ExtractedEntity(target, "ENTITY", target, 1.0))
            relations.append(ExtractedRelation(source, target, relation_type.strip(), 1.0))
        return ExtractionResult(tuple(entities.values()), tuple(relations), self.version)
