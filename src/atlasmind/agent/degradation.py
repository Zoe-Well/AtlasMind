"""Typed source outcomes and safe partial-result semantics."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceOutcome:
    source_name: str
    facts: tuple[str, ...]
    reason_code: str | None = None

    @classmethod
    def succeeded(cls, source_name: str, facts: tuple[str, ...]) -> SourceOutcome:
        return cls(source_name=source_name, facts=facts)

    @classmethod
    def failed(cls, source_name: str, reason_code: str) -> SourceOutcome:
        return cls(source_name=source_name, facts=(), reason_code=reason_code)

    @property
    def succeeded_safely(self) -> bool:
        return self.reason_code is None
