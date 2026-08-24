"""Explicitly enabled LangSmith export behind the common export policy."""

from __future__ import annotations

from typing import Any

from atlasmind.observability.export_policy import ExportPolicy


class LangSmithAdapter:
    def __init__(self, policy: ExportPolicy, *, enabled: bool = False) -> None:
        self._policy = policy
        self._enabled = enabled
        self._exported: list[dict[str, Any]] = []

    def export(self, artifact: dict[str, Any]) -> dict[str, Any] | None:
        if not self._enabled:
            return None
        sanitized = self._policy.sanitize(artifact)
        if not isinstance(sanitized, dict):
            raise ValueError("LangSmith artifact must be an object")
        self._exported.append(sanitized)
        return sanitized

    @property
    def exported(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._exported)
