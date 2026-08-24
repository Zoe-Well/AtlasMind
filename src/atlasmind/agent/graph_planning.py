"""Policy-driven decision for when bounded graph retrieval is warranted."""

from dataclasses import dataclass

from atlasmind.retrieval.graph_contracts import GraphRetrievalRequest


@dataclass(frozen=True, slots=True)
class GraphPolicy:
    enabled: bool = True
    max_hops: int = 3
    max_nodes: int = 30


def plan_graph_retrieval(
    query: str,
    *,
    scope_ids: frozenset[str],
    policy: GraphPolicy,
) -> GraphRetrievalRequest | None:
    multi_hop_markers = ("related", "through", "ultimately", "关系", "最终", "多跳")
    if not policy.enabled or not any(marker in query.casefold() for marker in multi_hop_markers):
        return None
    return GraphRetrievalRequest(query, scope_ids, policy.max_hops, policy.max_nodes)
