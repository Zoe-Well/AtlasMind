"""Strict schemas at the Agent-to-capability execution boundary."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from atlasmind.identity.models import Action


class CapabilityKind(StrEnum):
    RETRIEVAL = "RETRIEVAL"
    STRUCTURED_QUERY = "STRUCTURED_QUERY"
    EXTERNAL_TOOL = "EXTERNAL_TOOL"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class CapabilityDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    version: str
    kind: CapabilityKind
    required_actions: frozenset[Action]
    risk_level: RiskLevel
    side_effect: bool = False
    timeout_ms: int = Field(gt=0, le=60_000)
    max_result_bytes: int = Field(gt=0, le=10_000_000)
    max_items: int = Field(gt=0, le=1_000)
    idempotency_required: bool = False

    @model_validator(mode="after")
    def side_effects_are_high_risk(self) -> CapabilityDescriptor:
        unsafe_side_effect = self.risk_level is not RiskLevel.HIGH or not self.idempotency_required
        if self.side_effect and unsafe_side_effect:
            raise ValueError("side-effect capabilities must be HIGH risk and idempotent")
        return self


class CapabilityBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    timeout_ms: int = Field(gt=0)
    max_items: int = Field(gt=0)
    max_result_bytes: int = Field(gt=0)


class CapabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request_id: str
    run_id: str
    step_id: str
    capability_name: str
    capability_version: str
    auth_context_ref: str
    input: dict[str, Any]
    budget: CapabilityBudget
    idempotency_key: str | None = None
    approval_grant_ref: str | None = None

    @model_validator(mode="after")
    def input_cannot_supply_authority(self) -> CapabilityRequest:
        forbidden = {
            "subject",
            "principal_id",
            "roles",
            "role_codes",
            "scopes",
            "scope_ids",
            "skip_auth",
        }
        if forbidden & {key.casefold() for key in self.input}:
            raise ValueError("capability input cannot supply authorization state")
        return self


class EvidenceSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    type: str
    canonical_id: str
    version: str
    locator: str


class EvidenceEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    evidence_id: str
    source: EvidenceSource
    scope_ids: frozenset[str]
    content_ref: str
    content_digest: str
    facts: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)
    validity: str = "VALID"
    authz_revision: int
    verified_at: datetime


class CapabilityResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: str
    evidence: tuple[EvidenceEnvelope, ...] = ()
    reason_code: str | None = None
    retryable: bool = False
    warnings: tuple[str, ...] = ()
