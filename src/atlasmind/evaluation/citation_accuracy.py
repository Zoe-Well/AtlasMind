"""Claim-bound citation locator and support accuracy metric."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CitationCheck:
    claim: str
    locator: str
    source_content: str


def citation_accuracy(checks: tuple[CitationCheck, ...]) -> float:
    if not checks:
        return 0.0
    supported = sum(
        bool(check.claim.strip())
        and bool(check.locator.strip())
        and check.claim.casefold() in check.source_content.casefold()
        for check in checks
    )
    return supported / len(checks)
