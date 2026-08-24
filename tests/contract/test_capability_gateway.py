"""Strict schema and output limits for registered capabilities."""

from __future__ import annotations

import pytest

from atlasmind.agent.models import CapabilityDefinition, CapabilityStatus
from atlasmind.domain.common import AuthorizationDenied, BudgetExceeded
from atlasmind.identity.models import Action
from atlasmind.tools.contracts import CapabilityKind, RiskLevel
from atlasmind.tools.structured_registry import StructuredCapabilityRegistry


def definition() -> CapabilityDefinition:
    return CapabilityDefinition(
        name="metrics.query",
        version="1",
        kind=CapabilityKind.STRUCTURED_QUERY,
        input_schema={
            "type": "object",
            "required": ["dataset", "metric"],
            "additionalProperties": False,
            "properties": {
                "dataset": {"type": "string"},
                "metric": {"type": "string"},
            },
        },
        output_schema={"type": "array"},
        required_actions=frozenset({Action.READ}),
        supported_scope_types=frozenset({"KNOWLEDGE"}),
        risk_level=RiskLevel.LOW,
        timeout_ms=100,
        max_result_bytes=256,
        max_items=2,
    )


@pytest.mark.contract
def test_registry_rejects_unknown_disabled_and_invalid_capability_requests() -> None:
    registry = StructuredCapabilityRegistry()
    registry.register(definition())

    with pytest.raises(AuthorizationDenied) as unknown:
        registry.validate_input("unknown", "1", {})
    assert unknown.value.details["reason"] == "CAPABILITY_NOT_AVAILABLE"
    with pytest.raises(ValueError, match="required property"):
        registry.validate_input("metrics.query", "1", {"dataset": "refunds"})
    with pytest.raises(ValueError, match="undeclared property"):
        registry.validate_input(
            "metrics.query",
            "1",
            {"dataset": "refunds", "metric": "failure_rate", "scope": "secret"},
        )

    registry.set_status("metrics.query", "1", CapabilityStatus.DISABLED)
    with pytest.raises(AuthorizationDenied) as disabled:
        registry.validate_input(
            "metrics.query",
            "1",
            {"dataset": "refunds", "metric": "failure_rate"},
        )
    assert disabled.value.details["reason"] == "CAPABILITY_NOT_AVAILABLE"


@pytest.mark.contract
def test_registry_enforces_result_item_and_byte_limits() -> None:
    registry = StructuredCapabilityRegistry()
    registry.register(definition())

    with pytest.raises(BudgetExceeded) as too_many:
        registry.validate_output("metrics.query", "1", [{}, {}, {}])
    assert too_many.value.details["reason"] == "ITEM_BUDGET_EXCEEDED"
    with pytest.raises(BudgetExceeded) as too_large:
        registry.validate_output("metrics.query", "1", [{"value": "x" * 300}])
    assert too_large.value.details["reason"] == "RESULT_BUDGET_EXCEEDED"
