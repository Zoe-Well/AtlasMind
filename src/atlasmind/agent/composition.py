"""Compose only verified evidence and label fact, inference, conflict, and unknown."""

from __future__ import annotations

from dataclasses import dataclass

from atlasmind.tools.contracts import EvidenceEnvelope


@dataclass(frozen=True, slots=True)
class ComposedAnalysis:
    facts: tuple[str, ...]
    inferences: tuple[str, ...]
    unknowns: tuple[str, ...]
    evidence_ids: tuple[str, ...]


def compose_analysis(
    evidence: tuple[EvidenceEnvelope, ...],
    *,
    unavailable_sources: tuple[str, ...] = (),
) -> ComposedAnalysis:
    verified = tuple(item for item in evidence if item.validity == "VALID")
    facts = tuple(fact for item in verified for fact in item.facts)
    return ComposedAnalysis(
        facts=facts,
        inferences=(),
        unknowns=tuple(f"Source unavailable: {name}" for name in unavailable_sources),
        evidence_ids=tuple(item.evidence_id for item in verified),
    )
