"""Fail-closed authorization over trusted, short-lived context snapshots."""

from __future__ import annotations

from hashlib import sha256

from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.domain.common import AuthorizationDenied, utc_now
from atlasmind.identity.models import Action, AuthorizationSnapshot


class AuthorizationService:
    """Authorize actions without treating cached request context as current truth."""

    def authorize(
        self,
        context: AuthContext,
        *,
        action: Action,
        requested_scope_ids: set[str] | frozenset[str],
        current: AuthorizationSnapshot,
    ) -> frozenset[str]:
        now = utc_now()
        if context.expires_at <= now or context.issued_at > now:
            raise AuthorizationDenied(details={"reason": "AUTH_CONTEXT_EXPIRED"})
        if context.authz_revision != current.revision:
            raise AuthorizationDenied(details={"reason": "AUTHZ_REVISION_CHANGED"})
        if action not in context.allowed_actions:
            raise AuthorizationDenied(details={"reason": "ACTION_NOT_GRANTED"})

        authorized = frozenset(requested_scope_ids) & context.scope_ids & current.active_scope_ids
        if not authorized:
            raise AuthorizationDenied(details={"reason": "SCOPE_NOT_GRANTED"})
        return authorized

    def cache_key(self, context: AuthContext) -> str:
        """Bind cached decisions to all authority-bearing revisions and values."""
        material = "|".join(
            (
                context.principal_id,
                ",".join(sorted(context.role_codes)),
                ",".join(sorted(context.scope_ids)),
                ",".join(sorted(action.value for action in context.allowed_actions)),
                str(context.authz_revision),
                str(context.policy_revision),
            )
        )
        return f"{context.principal_id}:{sha256(material.encode()).hexdigest()}"
