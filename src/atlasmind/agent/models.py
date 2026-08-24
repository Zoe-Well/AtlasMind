"""Agent runs, steps, capabilities, invocations, and approval state."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Any

from atlasmind.domain.common import InvalidState, new_id, utc_now
from atlasmind.identity.models import Action
from atlasmind.tools.contracts import CapabilityKind, RiskLevel


class CapabilityStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    RETIRED = "RETIRED"


class AgentRunState(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


class StepKind(StrEnum):
    PLAN = "PLAN"
    RETRIEVAL = "RETRIEVAL"
    TOOL = "TOOL"
    COMPOSE = "COMPOSE"
    VERIFY = "VERIFY"


class StepState(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class InvocationState(StrEnum):
    PLANNED = "PLANNED"
    AUTHORIZED = "AUTHORIZED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ApprovalState(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"
    CONSUMED = "CONSUMED"


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    name: str
    version: str
    kind: CapabilityKind
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    required_actions: frozenset[Action]
    supported_scope_types: frozenset[str]
    risk_level: RiskLevel
    timeout_ms: int
    max_result_bytes: int
    max_items: int
    side_effect: bool = False
    idempotency_required: bool = False
    status: CapabilityStatus = CapabilityStatus.ACTIVE

    def __post_init__(self) -> None:
        if not self.name or not self.version or not self.supported_scope_types:
            raise ValueError("capability identity and supported scopes are required")
        if min(self.timeout_ms, self.max_result_bytes, self.max_items) <= 0:
            raise ValueError("capability limits must be positive")
        if self.side_effect and (
            self.risk_level is not RiskLevel.HIGH or not self.idempotency_required
        ):
            raise ValueError("side-effect capability must be HIGH risk and idempotent")


@dataclass(frozen=True, slots=True)
class RunStep:
    run_id: str
    ordinal: int
    kind: StepKind
    state: StepState = StepState.PENDING
    capability_name: str | None = None
    capability_version: str | None = None
    input_digest: str | None = None
    result_ref: str | None = None
    id: str = field(default_factory=new_id)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def complete(self, *, result_ref: str | None = None) -> RunStep:
        return replace(
            self,
            state=StepState.SUCCEEDED,
            result_ref=result_ref,
            started_at=self.started_at or utc_now(),
            finished_at=utc_now(),
        )


@dataclass(frozen=True, slots=True)
class ToolInvocation:
    run_step_id: str
    capability_name: str
    capability_version: str
    principal_id: str
    authz_revision: int
    normalized_input_digest: str
    idempotency_key: str | None
    state: InvocationState = InvocationState.PLANNED
    approval_request_id: str | None = None
    result_ref: str | None = None
    error_code: str | None = None
    id: str = field(default_factory=new_id)


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    invocation_id: str
    principal_id: str
    capability_name: str
    capability_version: str
    target_resource: str
    input_digest: str
    run_id: str
    correlation_id: str
    expires_at: datetime
    nonce_hash: str
    state: ApprovalState = ApprovalState.PENDING
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_reason: str | None = None
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utc_now)

    def approve(self, approver_id: str) -> ApprovalRequest:
        if self.state is not ApprovalState.PENDING:
            raise InvalidState(details={"reason": "APPROVAL_NOT_PENDING"})
        return replace(
            self,
            state=ApprovalState.APPROVED,
            decided_by=approver_id,
            decided_at=utc_now(),
        )
