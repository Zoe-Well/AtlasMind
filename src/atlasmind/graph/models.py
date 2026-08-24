"""Canonical graph entities, mentions, relations, and immutable evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from atlasmind.domain.common import new_id


class EntityStatus(StrEnum):
    ACTIVE = "ACTIVE"
    MERGED = "MERGED"
    REVOKED = "REVOKED"


class MentionReviewStatus(StrEnum):
    AUTO = "AUTO"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class RelationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CONFLICTED = "CONFLICTED"
    REVOKED = "REVOKED"


@dataclass(frozen=True, slots=True)
class GraphEntity:
    canonical_name: str
    entity_type: str
    aliases: tuple[str, ...] = ()
    status: EntityStatus = EntityStatus.ACTIVE
    merged_into_id: str | None = None
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        if not self.canonical_name.strip() or not self.entity_type.strip():
            raise ValueError("entity name and type are required")
        if self.status is EntityStatus.MERGED and not self.merged_into_id:
            raise ValueError("merged entity requires canonical target")


@dataclass(frozen=True, slots=True)
class EntityMention:
    entity_id: str
    chunk_id: str
    document_version_id: str
    surface: str
    locator: str
    confidence: float
    scope_ids: frozenset[str]
    extraction_version: str
    review_status: MentionReviewStatus = MentionReviewStatus.AUTO
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("mention confidence must be between zero and one")
        if not self.scope_ids or not self.locator or not self.document_version_id:
            raise ValueError("mention requires source scope, version, and locator")


@dataclass(frozen=True, slots=True)
class GraphRelation:
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    confidence: float
    extraction_version: str
    status: RelationStatus = RelationStatus.ACTIVE
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        if self.source_entity_id == self.target_entity_id:
            raise ValueError("relation requires distinct endpoints")
        if not self.relation_type or not self.extraction_version:
            raise ValueError("relation type and extraction version are required")
        if not 0 <= self.confidence <= 1:
            raise ValueError("relation confidence must be between zero and one")
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("relation validity interval is invalid")

    @property
    def can_support_fact(self) -> bool:
        return self.status is RelationStatus.ACTIVE


@dataclass(frozen=True, slots=True)
class RelationEvidence:
    relation_id: str
    chunk_id: str
    document_version_id: str
    locator: str
    scope_ids: frozenset[str]
    generation: int
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        if not self.scope_ids:
            raise ValueError("relation evidence requires source scope")
        if not self.document_version_id or not self.chunk_id or not self.locator:
            raise ValueError("relation evidence requires source version and locator")
        if self.generation < 1:
            raise ValueError("relation evidence generation must be positive")


class GraphRepository:
    def __init__(self) -> None:
        self.entities: dict[str, GraphEntity] = {}
        self.mentions: dict[str, EntityMention] = {}
        self.relations: dict[str, GraphRelation] = {}
        self.evidence: dict[str, RelationEvidence] = {}

    def add_entity(self, entity: GraphEntity) -> None:
        self.entities[entity.id] = entity

    def add_mention(self, mention: EntityMention) -> None:
        if mention.entity_id not in self.entities:
            raise ValueError("mention entity is not canonical")
        self.mentions[mention.id] = mention

    def add_relation(self, relation: GraphRelation, evidence: RelationEvidence) -> None:
        if {relation.source_entity_id, relation.target_entity_id} - self.entities.keys():
            raise ValueError("relation endpoints are not canonical")
        if evidence.relation_id != relation.id:
            raise ValueError("relation evidence binding mismatch")
        self.relations[relation.id] = relation
        self.evidence[evidence.id] = evidence
