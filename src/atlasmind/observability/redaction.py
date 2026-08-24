"""Allowlist-first telemetry redaction and secret marker removal."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from hashlib import sha256
from typing import Any

SECRET_MARKERS = ("authorization", "password", "secret", "token", "api_key", "approval_grant")


def digest(value: str) -> str:
    return f"sha256:{sha256(value.encode()).hexdigest()}"


def redact_fields(values: Mapping[str, Any], *, allowlist: Iterable[str]) -> dict[str, Any]:
    allowed = set(allowlist)
    result: dict[str, Any] = {}
    for key, value in values.items():
        normalized = key.casefold()
        if any(marker in normalized for marker in SECRET_MARKERS):
            result[key] = "[REDACTED]"
        elif key in allowed:
            result[key] = value
    return result
