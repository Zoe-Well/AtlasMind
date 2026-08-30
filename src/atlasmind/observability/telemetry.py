"""OpenTelemetry initialization and safe AtlasMind span attributes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

ALLOWED_ATTRIBUTES = frozenset(
    {
        "atlasmind.correlation_id",
        "atlasmind.run_id",
        "atlasmind.step_id",
        "atlasmind.capability.name",
        "atlasmind.capability.version",
        "atlasmind.policy.version",
        "atlasmind.outcome",
        "atlasmind.error.code",
    }
)
_provider: TracerProvider | None = None


def safe_attributes(values: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if key in ALLOWED_ATTRIBUTES}


def configure_telemetry(service_name: str, endpoint: str | None = None) -> TracerProvider:
    global _provider
    if _provider is not None:
        return _provider
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    if endpoint:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    _provider = provider
    return provider
