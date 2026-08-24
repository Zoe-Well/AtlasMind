"""Graph retrieval backend port and deterministic path adapter."""

from __future__ import annotations

from typing import Protocol

from atlasmind.retrieval.graph_contracts import GraphPath, GraphRetrievalRequest


class GraphRetrievalBackend(Protocol):
    def retrieve(self, request: GraphRetrievalRequest) -> tuple[GraphPath, ...]: ...


class InMemoryGraphBackend:
    def __init__(self, paths: tuple[GraphPath, ...]) -> None:
        self._paths = paths

    def retrieve(self, request: GraphRetrievalRequest) -> tuple[GraphPath, ...]:
        return tuple(
            path
            for path in self._paths
            if len(path.edges) <= request.max_hops and len(path.nodes) <= request.max_nodes
        )
