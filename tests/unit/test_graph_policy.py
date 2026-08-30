"""Graph ingestion/retrieval policy validation."""

import pytest
from pydantic import ValidationError

from atlasmind.graph.policy import GraphPolicy, default_graph_policy


def test_default_graph_policy_is_business_focused_and_bounded() -> None:
    policy = default_graph_policy()

    assert "PRODUCT" in policy.allowed_entity_types
    assert "ERROR_CODE" in policy.allowed_entity_types
    assert "CONCEPT" not in policy.allowed_entity_types
    assert policy.max_hops == 2
    assert policy.max_nodes == 40
    assert policy.minimum_relation_confidence > policy.minimum_entity_confidence


def test_policy_normalizes_configured_types_and_rejects_unbounded_hops() -> None:
    policy = GraphPolicy(
        allowed_entity_types={"product", "api"},
        allowed_relation_types={"uses"},
    )

    assert policy.allowed_entity_types == {"PRODUCT", "API"}
    assert policy.allowed_relation_types == {"USES"}
    with pytest.raises(ValidationError):
        GraphPolicy(max_hops=3)
