"""Treat retrieved and tool-provided instructions as inert data."""

from __future__ import annotations

import re
from dataclasses import dataclass

from atlasmind.domain.common import AuthorizationDenied

_INJECTION = re.compile(
    r"ignore previous|system prompt|without approval|override capability|"
    r"reveal scope|admin\.delete",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class InspectedContent:
    content: str
    source: str
    untrusted: bool
    injection_detected: bool
    authority_directives: tuple[str, ...] = ()


class UntrustedContentBoundary:
    def __init__(self, *, allowed_capabilities: set[str]) -> None:
        self._allowed = frozenset(allowed_capabilities)

    def inspect(self, content: str, *, source: str) -> InspectedContent:
        return InspectedContent(
            content=content,
            source=source,
            untrusted=True,
            injection_detected=bool(_INJECTION.search(content)),
        )

    def ensure_allowed(self, capability_name: str) -> None:
        if capability_name not in self._allowed:
            raise AuthorizationDenied(details={"reason": "CAPABILITY_NOT_ALLOWED"})
