"""Deterministic intent classification and allowlisted capability planning."""

from __future__ import annotations

from dataclasses import dataclass

from atlasmind.domain.common import AuthorizationDenied


@dataclass(frozen=True, slots=True)
class Plan:
    task_type: str
    capability_names: tuple[str, ...]


class PolicyPlanner:
    def __init__(self, *, allowed_capabilities: frozenset[str]) -> None:
        self._allowed = allowed_capabilities

    def plan(self, query: str, requested: tuple[str, ...]) -> Plan:
        if not query.strip():
            raise ValueError("query is required")
        denied = set(requested) - self._allowed
        if denied:
            raise AuthorizationDenied(details={"reason": "CAPABILITY_NOT_ALLOWED"})
        task_type = "MULTI_SOURCE" if len(requested) > 1 else "SIMPLE"
        return Plan(task_type=task_type, capability_names=requested)
