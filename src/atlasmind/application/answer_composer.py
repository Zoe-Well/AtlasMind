"""Evidence-only answer composition with explicit uncertainty semantics."""

from __future__ import annotations

from dataclasses import dataclass

from atlasmind.domain.common import new_id
from atlasmind.domain.knowledge import Citation, Evidence
from atlasmind.retrieval.evidence_verifier import verify_evidence


@dataclass(frozen=True, slots=True)
class ComposedAnswer:
    text: str
    confidence: str
    evidence_status: str
    citations: tuple[Citation, ...]
    limitations: tuple[str, ...] = ()


class AnswerComposer:
    def compose(self, evidence: list[Evidence]) -> ComposedAnswer:
        verification = verify_evidence(evidence)
        if verification.status == "INSUFFICIENT":
            return ComposedAnswer(
                "I don't have sufficient authorized evidence to answer.",
                "LOW",
                "INSUFFICIENT",
                (),
                verification.limitations,
            )
        if verification.status == "CONFLICTED":
            return ComposedAnswer(
                "Authorized sources conflict; no single conclusion is established.",
                "LOW",
                "CONFLICTED",
                (),
                verification.limitations,
            )
        citations = tuple(
            Citation(new_id(), item.content, item.id, item.source, "SUPPORTED")
            for item in verification.usable
        )
        facts = " ".join(item.content for item in verification.usable)
        return ComposedAnswer(
            facts, "HIGH" if len(citations) > 1 else "MEDIUM", "SUFFICIENT", citations
        )
