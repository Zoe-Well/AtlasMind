"""Backend-neutral graph retrieval request and provenance path values."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GraphRetrievalRequest:
    query: str
    scope_ids: frozenset[str]
    max_hops: int
    max_nodes: int

    def __post_init__(self) -> None:
        if not self.query.strip() or not self.scope_ids:
            raise ValueError("graph query and scopes are required")
        if not 1 <= self.max_hops <= 5:
            raise ValueError("hop budget must be between one and five")
        if not 2 <= self.max_nodes <= 100:
            raise ValueError("node budget must be between two and one hundred")


@dataclass(frozen=True, slots=True)
class GraphPathNode:
    canonical_id: str
    display_name: str
    scope_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class GraphPathEdge:
    relation_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    document_version_id: str
    locator: str
    scope_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class GraphPath:
    nodes: tuple[GraphPathNode, ...]
    edges: tuple[GraphPathEdge, ...]

    def __post_init__(self) -> None:
        if not self.nodes or not self.edges or len(self.nodes) != len(self.edges) + 1:
            raise ValueError("graph path must be a connected edge chain")


@dataclass(frozen=True, slots=True)
class AuthorizedGraphPaths:
    paths: tuple[GraphPath, ...]
    visible_path_count: int
    public_reason: str | None = None
