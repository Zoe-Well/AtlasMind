"""Recursive allowlist-first export policy for telemetry and evaluation artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import Any

_DROP_KEYS = frozenset(
    {
        "authorization",
        "password",
        "secret",
        "token",
        "api_key",
        "approval_grant",
    }
)
_CONTENT_KEYS = frozenset({"query", "content", "prompt", "result", "tool_result", "failure_sample"})


class ExportPolicy:
    def __init__(self, *, sensitive_values: set[str] | None = None) -> None:
        self._sensitive_values = frozenset(sensitive_values or ())

    def sanitize(self, value: Any, *, key: str | None = None) -> Any:
        normalized_key = (key or "").casefold()
        if any(marker in normalized_key for marker in _DROP_KEYS):
            return None
        if isinstance(value, Mapping):
            sanitized: dict[str, Any] = {}
            for child_key, child_value in value.items():
                normalized = str(child_key).casefold()
                if any(marker in normalized for marker in _DROP_KEYS):
                    continue
                sanitized[str(child_key)] = self.sanitize(child_value, key=str(child_key))
            return sanitized
        if isinstance(value, (tuple, list)):
            return [self.sanitize(item, key=key) for item in value]
        if isinstance(value, str) and (
            normalized_key in _CONTENT_KEYS
            or any(secret and secret in value for secret in self._sensitive_values)
        ):
            return f"sha256:{sha256(value.encode()).hexdigest()}"
        return value
