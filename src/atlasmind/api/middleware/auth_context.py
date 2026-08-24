"""Trusted authentication context construction and request correlation."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from starlette.requests import Request
from starlette.responses import Response

from atlasmind.domain.common import AuthenticationRequired, new_id
from atlasmind.identity.models import Action


@dataclass(frozen=True, slots=True)
class AuthContext:
    principal_id: str
    role_codes: frozenset[str]
    scope_ids: frozenset[str]
    allowed_actions: frozenset[Action]
    authz_revision: int
    policy_revision: int
    correlation_id: str
    issued_at: datetime
    expires_at: datetime


def trusted_auth_context(claims: dict[str, Any], correlation_id: str) -> AuthContext:
    """Construct context only from already verified server-owned claims."""
    required = {
        "sub",
        "roles",
        "scopes",
        "actions",
        "authz_revision",
        "policy_revision",
        "iat",
        "exp",
    }
    if not required.issubset(claims):
        raise AuthenticationRequired(details={"reason": "AUTH_CONTEXT_INCOMPLETE"})
    try:
        UUID(correlation_id)
        return AuthContext(
            principal_id=str(claims["sub"]),
            role_codes=frozenset(map(str, claims["roles"])),
            scope_ids=frozenset(map(str, claims["scopes"])),
            allowed_actions=frozenset(Action(value) for value in claims["actions"]),
            authz_revision=int(claims["authz_revision"]),
            policy_revision=int(claims["policy_revision"]),
            correlation_id=correlation_id,
            issued_at=datetime.fromtimestamp(float(claims["iat"]), tz=UTC),
            expires_at=datetime.fromtimestamp(float(claims["exp"]), tz=UTC),
        )
    except (TypeError, ValueError) as exc:
        raise AuthenticationRequired(details={"reason": "AUTH_CONTEXT_INVALID"}) from exc


class CorrelationIdMiddleware:
    """Use valid caller correlation IDs or generate a server-owned UUID."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        candidate = request.headers.get("x-correlation-id", "")
        try:
            correlation_id = str(UUID(candidate))
        except ValueError:
            correlation_id = new_id()
        scope.setdefault("state", {})["correlation_id"] = correlation_id

        async def send_with_header(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                response = Response()
                response.raw_headers = list(message.get("headers", []))
                response.headers["x-correlation-id"] = correlation_id
                message["headers"] = response.raw_headers
            await send(message)

        await self.app(scope, receive, send_with_header)
