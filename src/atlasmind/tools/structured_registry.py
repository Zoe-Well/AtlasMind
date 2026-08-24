"""Versioned capability registry with strict input and bounded output validation."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from atlasmind.agent.models import CapabilityDefinition, CapabilityStatus
from atlasmind.domain.common import AuthorizationDenied, BudgetExceeded


class StructuredCapabilityRegistry:
    def __init__(self) -> None:
        self._definitions: dict[tuple[str, str], CapabilityDefinition] = {}

    def register(self, definition: CapabilityDefinition) -> None:
        key = (definition.name, definition.version)
        if key in self._definitions:
            raise ValueError("capability version already registered")
        self._definitions[key] = definition

    def get(self, name: str, version: str) -> CapabilityDefinition:
        definition = self._definitions.get((name, version))
        if definition is None or definition.status is not CapabilityStatus.ACTIVE:
            raise AuthorizationDenied(details={"reason": "CAPABILITY_NOT_AVAILABLE"})
        return definition

    def set_status(self, name: str, version: str, status: CapabilityStatus) -> None:
        definition = self._definitions.get((name, version))
        if definition is None:
            raise AuthorizationDenied(details={"reason": "CAPABILITY_NOT_AVAILABLE"})
        self._definitions[(name, version)] = replace(definition, status=status)

    def validate_input(self, name: str, version: str, value: dict[str, Any]) -> None:
        definition = self.get(name, version)
        schema = definition.input_schema
        if schema.get("type") != "object":
            raise ValueError("capability input schema must describe an object")
        required = frozenset(map(str, schema.get("required", ())))
        missing = required - value.keys()
        if missing:
            raise ValueError(f"required property missing: {sorted(missing)[0]}")
        declared = frozenset(map(str, schema.get("properties", {})))
        extras = value.keys() - declared
        if extras and schema.get("additionalProperties") is False:
            raise ValueError(f"undeclared property: {sorted(extras)[0]}")
        for key, item in value.items():
            expected = schema.get("properties", {}).get(key, {}).get("type")
            if expected == "string" and not isinstance(item, str):
                raise ValueError(f"property {key} must be a string")

    def validate_output(self, name: str, version: str, value: Any) -> None:
        definition = self.get(name, version)
        if definition.output_schema.get("type") == "array" and not isinstance(value, list):
            raise ValueError("capability output must be an array")
        if isinstance(value, list) and len(value) > definition.max_items:
            raise BudgetExceeded(details={"reason": "ITEM_BUDGET_EXCEEDED"})
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        if len(encoded) > definition.max_result_bytes:
            raise BudgetExceeded(details={"reason": "RESULT_BUDGET_EXCEEDED"})
