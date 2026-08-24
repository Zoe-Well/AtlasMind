"""Deterministic authorization boundary tests."""

from datetime import UTC, datetime, timedelta

import pytest

from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.domain.common import AuthorizationDenied
from atlasmind.identity.authorization import AuthorizationService
from atlasmind.identity.models import Action, AuthorizationSnapshot


def context(*, revision: int = 7, expires_delta: int = 60) -> AuthContext:
    now = datetime.now(UTC)
    return AuthContext(
        principal_id="principal-1",
        role_codes=frozenset({"employee"}),
        scope_ids=frozenset({"scope-public", "scope-refund"}),
        allowed_actions=frozenset({Action.READ, Action.CITE}),
        authz_revision=revision,
        policy_revision=3,
        correlation_id="00000000-0000-0000-0000-000000000001",
        issued_at=now,
        expires_at=now + timedelta(seconds=expires_delta),
    )


@pytest.mark.security
def test_authorization_returns_only_current_scope_intersection() -> None:
    service = AuthorizationService()
    result = service.authorize(
        context(),
        action=Action.READ,
        requested_scope_ids={"scope-public", "scope-secret"},
        current=AuthorizationSnapshot(revision=7, active_scope_ids=frozenset({"scope-public"})),
    )
    assert result == frozenset({"scope-public"})


@pytest.mark.security
@pytest.mark.parametrize(
    ("action", "scopes", "revision"),
    [
        (Action.MANAGE, {"scope-public"}, 7),
        (Action.READ, {"scope-secret"}, 7),
        (Action.READ, {"scope-public"}, 8),
    ],
)
def test_missing_action_scope_or_current_revision_fails_closed(
    action: Action, scopes: set[str], revision: int
) -> None:
    service = AuthorizationService()
    with pytest.raises(AuthorizationDenied):
        service.authorize(
            context(),
            action=action,
            requested_scope_ids=scopes,
            current=AuthorizationSnapshot(
                revision=revision, active_scope_ids=frozenset({"scope-public"})
            ),
        )


@pytest.mark.security
def test_expired_context_fails_closed() -> None:
    with pytest.raises(AuthorizationDenied):
        AuthorizationService().authorize(
            context(expires_delta=-1),
            action=Action.READ,
            requested_scope_ids={"scope-public"},
            current=AuthorizationSnapshot(revision=7, active_scope_ids=frozenset({"scope-public"})),
        )


@pytest.mark.security
def test_cache_key_includes_identity_scopes_and_revisions() -> None:
    service = AuthorizationService()
    first = service.cache_key(context(revision=7))
    second = service.cache_key(context(revision=8))
    assert first != second
    assert "principal-1" in first
