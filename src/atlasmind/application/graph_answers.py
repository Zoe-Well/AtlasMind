"""Graph path answer composition with claim-to-edge source citations."""

from __future__ import annotations

from dataclasses import dataclass

from atlasmind.retrieval.graph_contracts import AuthorizedGraphPaths


@dataclass(frozen=True, slots=True)
class GraphCitation:
    claim: str
    relation_id: str
    document_version_id: str
    locator: str


@dataclass(frozen=True, slots=True)
class GraphAnswer:
    text: str
    citations: tuple[GraphCitation, ...]
    evidence_status: str


def compose_graph_answer(result: AuthorizedGraphPaths) -> GraphAnswer:
    if not result.paths:
        return GraphAnswer(
            "No authorized relationship path was found.",
            (),
            "INSUFFICIENT_EVIDENCE",
        )
    claims: list[str] = []
    citations: list[GraphCitation] = []
    for path in result.paths:
        names = {node.canonical_id: node.display_name for node in path.nodes}
        for edge in path.edges:
            claim = (
                f"{names[edge.source_entity_id]} {edge.relation_type} "
                f"{names[edge.target_entity_id]}"
            )
            claims.append(claim)
            citations.append(
                GraphCitation(
                    claim,
                    edge.relation_id,
                    edge.document_version_id,
                    edge.locator,
                )
            )
    return GraphAnswer("; ".join(claims), tuple(citations), "SUPPORTED")
