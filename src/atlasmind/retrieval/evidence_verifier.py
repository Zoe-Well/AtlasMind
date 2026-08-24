"""Evidence sufficiency, conflicts, staleness, and locator verification."""

from __future__ import annotations

from dataclasses import dataclass

from atlasmind.domain.knowledge import Evidence, EvidenceValidity


@dataclass(frozen=True, slots=True)
class VerificationResult:
    status: str
    usable: tuple[Evidence, ...]
    limitations: tuple[str, ...] = ()


def verify_evidence(evidence: list[Evidence]) -> VerificationResult:
    located = [item for item in evidence if item.source.locator.strip()]
    usable = tuple(item for item in located if item.validity is EvidenceValidity.VALID)
    conflicted = any(item.validity is EvidenceValidity.CONFLICTED for item in located)
    if conflicted:
        return VerificationResult("CONFLICTED", tuple(located), ("Sources conflict.",))
    if not usable:
        return VerificationResult("INSUFFICIENT", (), ("No verifiable evidence was found.",))
    stale_count = sum(item.validity is EvidenceValidity.STALE for item in located)
    limitations = ("Some sources are stale.",) if stale_count else ()
    return VerificationResult("SUFFICIENT", usable, limitations)
