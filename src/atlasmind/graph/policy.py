"""Versioned policy for building and querying the auxiliary retrieval graph."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_ENTITY_TYPES = frozenset(
    {
        "SYSTEM",
        "PRODUCT",
        "SERVICE",
        "API",
        "ERROR_CODE",
        "ORGANIZATION",
        "ORG_UNIT",
        "DATABASE",
        "QUEUE",
        "TECH_COMPONENT",
    }
)

DEFAULT_RELATION_TYPES = frozenset(
    {
        "CALLS",
        "CONSUMES",
        "DEPENDS_ON",
        "DEPLOYED_ON",
        "EXPOSES",
        "INTEGRATES_WITH",
        "MANAGED_BY",
        "OWNED_BY",
        "PART_OF",
        "PRODUCES",
        "RETURNS_ERROR",
        "STORES_IN",
        "USES",
    }
)


class GraphPolicy(BaseModel):
    """Conservative, bounded policy shared by ingestion and retrieval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(default=1, ge=1)
    allowed_entity_types: frozenset[str] = DEFAULT_ENTITY_TYPES
    allowed_relation_types: frozenset[str] = DEFAULT_RELATION_TYPES
    minimum_entity_confidence: float = Field(default=0.60, ge=0, le=1)
    minimum_relation_confidence: float = Field(default=0.70, ge=0, le=1)
    seed_limit: int = Field(default=8, ge=1, le=30)
    max_hops: int = Field(default=2, ge=1, le=2)
    max_nodes: int = Field(default=40, ge=2, le=200)
    max_paths: int = Field(default=24, ge=1, le=100)
    max_graph_chunks: int = Field(default=24, ge=1, le=100)
    allowed_aliases: dict[str, str] = Field(default_factory=dict)

    @field_validator("allowed_entity_types", "allowed_relation_types", mode="before")
    @classmethod
    def normalize_types(cls, values: object) -> object:
        if isinstance(values, (list, tuple, set, frozenset)):
            return frozenset(str(value).strip().upper() for value in values if str(value).strip())
        return values

    @field_validator("allowed_aliases", mode="before")
    @classmethod
    def normalize_aliases(cls, values: object) -> object:
        if not isinstance(values, dict):
            return values
        return {
            str(alias).strip(): str(canonical).strip()
            for alias, canonical in values.items()
            if str(alias).strip() and str(canonical).strip()
        }

    @model_validator(mode="after")
    def non_empty_allowlists(self) -> GraphPolicy:
        if not self.allowed_entity_types or not self.allowed_relation_types:
            raise ValueError("graph entity and relation allowlists must not be empty")
        return self

    def as_configuration(self) -> dict[str, object]:
        values = self.model_dump(mode="json", exclude={"version"})
        values["allowed_entity_types"] = sorted(self.allowed_entity_types)
        values["allowed_relation_types"] = sorted(self.allowed_relation_types)
        return values

    def as_api_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "allowedEntityTypes": sorted(self.allowed_entity_types),
            "allowedRelationTypes": sorted(self.allowed_relation_types),
            "minimumEntityConfidence": self.minimum_entity_confidence,
            "minimumRelationConfidence": self.minimum_relation_confidence,
            "seedLimit": self.seed_limit,
            "maxHops": self.max_hops,
            "maxNodes": self.max_nodes,
            "maxPaths": self.max_paths,
            "maxGraphChunks": self.max_graph_chunks,
            "allowedAliases": dict(sorted(self.allowed_aliases.items())),
        }


def default_graph_policy() -> GraphPolicy:
    return GraphPolicy()
