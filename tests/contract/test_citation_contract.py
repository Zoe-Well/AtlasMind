"""Every supported claim resolves to authorized source location."""

from datetime import UTC, datetime

import pytest

from atlasmind.domain.knowledge import Citation, Evidence, EvidenceValidity, SourceReference


def test_citation_binds_claim_evidence_version_and_locator() -> None:
    source = SourceReference("DOCUMENT", "document-1", "version-1", "page=2;paragraph=3")
    evidence = Evidence(
        id="evidence-1",
        source=source,
        scope_ids=frozenset({"public"}),
        content="Refunds are allowed within 30 days.",
        digest="sha256:abc",
        validity=EvidenceValidity.VALID,
        authz_revision=1,
        verified_at=datetime.now(UTC),
    )
    citation = Citation(
        id="citation-1",
        claim="Refunds are allowed within 30 days.",
        evidence_id=evidence.id,
        source=source,
        support="SUPPORTED",
    )
    citation.validate_against(evidence)


def test_citation_rejects_locator_or_evidence_mismatch() -> None:
    source = SourceReference("DOCUMENT", "document-1", "version-1", "page=2")
    evidence = Evidence(
        id="evidence-1",
        source=source,
        scope_ids=frozenset({"public"}),
        content="fact",
        digest="sha256:abc",
        validity=EvidenceValidity.VALID,
        authz_revision=1,
        verified_at=datetime.now(UTC),
    )
    bad = Citation(
        id="citation-1",
        claim="fact",
        evidence_id="different",
        source=source,
        support="SUPPORTED",
    )
    with pytest.raises(ValueError):
        bad.validate_against(evidence)
