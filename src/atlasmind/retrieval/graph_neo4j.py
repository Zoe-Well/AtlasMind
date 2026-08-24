"""Whole-path authorization applied before graph results become observable."""

from atlasmind.retrieval.graph_contracts import (
    AuthorizedGraphPaths,
    GraphPath,
    GraphRetrievalRequest,
)


class GraphPathAuthorizer:
    def authorize(
        self,
        request: GraphRetrievalRequest,
        candidate_paths: tuple[GraphPath, ...],
        *,
        active_version_ids: frozenset[str],
    ) -> AuthorizedGraphPaths:
        allowed: list[GraphPath] = []
        for path in candidate_paths:
            if len(path.edges) > request.max_hops or len(path.nodes) > request.max_nodes:
                continue
            components_authorized = all(
                node.scope_ids.issubset(request.scope_ids) for node in path.nodes
            ) and all(
                edge.scope_ids.issubset(request.scope_ids)
                and edge.document_version_id in active_version_ids
                for edge in path.edges
            )
            if components_authorized:
                allowed.append(path)
        if not allowed:
            return AuthorizedGraphPaths((), 0, "NO_AUTHORIZED_PATH")
        return AuthorizedGraphPaths(tuple(allowed), len(allowed))
