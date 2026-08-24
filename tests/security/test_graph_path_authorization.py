"""Every disclosed graph path component must remain currently authorized."""

from __future__ import annotations

import pytest

from atlasmind.retrieval.graph_contracts import (
    GraphPath,
    GraphPathEdge,
    GraphPathNode,
    GraphRetrievalRequest,
)
from atlasmind.retrieval.graph_neo4j import GraphPathAuthorizer


def path(*, edge_scope: str = "scope-public", version: str = "version-1") -> GraphPath:
    return GraphPath(
        nodes=(
            GraphPathNode("entity-service", "Refund Service", frozenset({"scope-public"})),
            GraphPathNode("entity-queue", "Refund Queue", frozenset({"scope-public"})),
        ),
        edges=(
            GraphPathEdge(
                relation_id="relation-writes",
                source_entity_id="entity-service",
                target_entity_id="entity-queue",
                relation_type="WRITES_TO",
                document_version_id=version,
                locator="page=2;paragraph=3",
                scope_ids=frozenset({edge_scope}),
            ),
        ),
    )


@pytest.mark.security
def test_whole_path_authorization_filters_scope_and_revoked_versions_before_return() -> None:
    authorizer = GraphPathAuthorizer()
    request = GraphRetrievalRequest(
        query="What does the refund service write to?",
        scope_ids=frozenset({"scope-public"}),
        max_hops=3,
        max_nodes=20,
    )

    authorized = authorizer.authorize(
        request,
        (path(), path(edge_scope="scope-secret"), path(version="version-revoked")),
        active_version_ids=frozenset({"version-1"}),
    )

    assert authorized.paths == (path(),)
    assert authorized.visible_path_count == 1


@pytest.mark.security
def test_unauthorized_and_absent_paths_have_identical_public_result() -> None:
    authorizer = GraphPathAuthorizer()
    request = GraphRetrievalRequest(
        query="restricted relation",
        scope_ids=frozenset({"scope-public"}),
        max_hops=2,
        max_nodes=10,
    )

    unauthorized = authorizer.authorize(
        request,
        (path(edge_scope="scope-secret"),),
        active_version_ids=frozenset({"version-1"}),
    )
    absent = authorizer.authorize(
        request,
        (),
        active_version_ids=frozenset({"version-1"}),
    )

    assert unauthorized == absent
    assert unauthorized.public_reason == "NO_AUTHORIZED_PATH"


@pytest.mark.security
def test_path_budget_is_checked_before_traversal() -> None:
    with pytest.raises(ValueError, match="hop budget"):
        GraphRetrievalRequest(
            query="too broad",
            scope_ids=frozenset({"scope-public"}),
            max_hops=0,
            max_nodes=10,
        )
