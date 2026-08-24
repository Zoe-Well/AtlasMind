"""Correlation-preserving spans and metrics for API, worker, Agent, and tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from atlasmind.observability.telemetry import safe_attributes


@dataclass(frozen=True, slots=True)
class RecordedSpan:
    name: str
    attributes: dict[str, Any]


class InMemoryInstrumentation:
    def __init__(self) -> None:
        self.spans: list[RecordedSpan] = []
        self.metrics: dict[str, list[float]] = {}

    def record_span(self, name: str, attributes: dict[str, Any]) -> None:
        safe = safe_attributes(attributes)
        if "atlasmind.correlation_id" not in safe:
            raise ValueError("correlation ID is required")
        self.spans.append(RecordedSpan(name, safe))

    def record_metric(self, name: str, value: float) -> None:
        self.metrics.setdefault(name, []).append(value)
