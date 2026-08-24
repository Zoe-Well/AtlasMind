"""Permission matrix ensures unauthorized candidates never reach output surfaces."""

from datetime import UTC, datetime, timedelta

import pytest

from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.domain.common import AuthorizationDenied
from atlasmind.domain.knowledge import KnowledgeChunk
from atlasmind.identity.models import Action, AuthorizationSnapshot
from atlasmind.retrieval.authorization import RetrievalAuthorization


def context() -> AuthContext:
    now = datetime.now(UTC)
    return AuthContext(
        principal_id="employee",
        role_codes=frozenset({"employee"}),
        scope_ids=frozenset({"public"}),
        allowed_actions=frozenset({Action.READ, Action.CITE}),
        authz_revision=4,
        policy_revision=2,
        correlation_id="00000000-0000-0000-0000-000000000001",
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
    )


def chunk(identifier: str, scope: str, text: str) -> KnowledgeChunk:
    return KnowledgeChunk(
        id=identifier,
        document_version_id=f"version-{identifier}",
        ordinal=0,
        content=text,
        locator="page=1;paragraph=1",
        scope_ids=frozenset({scope}),
        generation=1,
    )


@pytest.mark.security
def test_candidate_filter_prevents_forbidden_marker_leaking() -> None:
    authorization = RetrievalAuthorization()
    result = authorization.filter_candidates(
        context(),
        [chunk("public", "public", "allowed"), chunk("secret", "secret", "FORBIDDEN_MARKER")],
        current=AuthorizationSnapshot(4, frozenset({"public"})),
        active_generation=1,
    )
    serialized = repr(result)
    assert [item.id for item in result] == ["public"]
    assert "FORBIDDEN_MARKER" not in serialized


@pytest.mark.security
def test_return_review_fails_closed_after_revision_change() -> None:
    with pytest.raises(AuthorizationDenied):
        RetrievalAuthorization().review_evidence(
            context(),
            evidence_scope_ids=frozenset({"public"}),
            current=AuthorizationSnapshot(5, frozenset({"public"})),
        )
