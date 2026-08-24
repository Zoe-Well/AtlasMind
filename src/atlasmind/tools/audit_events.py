"""Minimal, redacted audit events for tool and approval transitions."""

from __future__ import annotations

from atlasmind.agent.models import ApprovalRequest, ToolInvocation
from atlasmind.observability.audit import AuditEvent


def invocation_audit_event(
    invocation: ToolInvocation,
    *,
    correlation_id: str,
    decision: str,
    reason_code: str,
) -> AuditEvent:
    return AuditEvent(
        event_type="tool.invocation.v1",
        actor_principal_id=invocation.principal_id,
        correlation_id=correlation_id,
        decision=decision,
        reason_code=reason_code,
        resource_type="TOOL_INVOCATION",
        resource_id=invocation.id,
        payload={
            "capability": invocation.capability_name,
            "version": invocation.capability_version,
            "inputDigest": invocation.normalized_input_digest,
            "state": invocation.state.value,
        },
    )


def approval_audit_event(
    request: ApprovalRequest,
    *,
    actor_id: str,
) -> AuditEvent:
    return AuditEvent(
        event_type="tool.approval.v1",
        actor_principal_id=actor_id,
        correlation_id=request.correlation_id,
        decision=request.state.value,
        reason_code=request.decision_reason or "APPROVAL_STATE_CHANGED",
        resource_type="APPROVAL_REQUEST",
        resource_id=request.id,
        payload={
            "capability": request.capability_name,
            "target": request.target_resource,
            "inputDigest": request.input_digest,
        },
    )
