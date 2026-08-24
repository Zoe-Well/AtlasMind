"""Bound, expiring, one-time approval challenges and grants."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta
from hashlib import sha256

from atlasmind.agent.models import ApprovalRequest, ApprovalState
from atlasmind.domain.common import AuthorizationDenied, new_id, utc_now


@dataclass(frozen=True, slots=True)
class ApprovalBinding:
    principal_id: str
    capability_name: str
    capability_version: str
    normalized_input_digest: str
    target_resource: str
    run_id: str
    correlation_id: str


class ApprovalService:
    def __init__(self) -> None:
        self.requests: dict[str, ApprovalRequest] = {}
        self._bindings: dict[str, ApprovalBinding] = {}
        self._grants: dict[str, str] = {}

    def create(self, binding: ApprovalBinding, *, ttl: timedelta) -> ApprovalRequest:
        if ttl <= timedelta(0):
            raise ValueError("approval ttl must be positive")
        nonce = new_id()
        request = ApprovalRequest(
            invocation_id=new_id(),
            principal_id=binding.principal_id,
            capability_name=binding.capability_name,
            capability_version=binding.capability_version,
            target_resource=binding.target_resource,
            input_digest=binding.normalized_input_digest,
            run_id=binding.run_id,
            correlation_id=binding.correlation_id,
            expires_at=utc_now() + ttl,
            nonce_hash=f"sha256:{sha256(nonce.encode()).hexdigest()}",
        )
        self.requests[request.id] = request
        self._bindings[request.id] = binding
        return request

    def approve(self, request: ApprovalRequest, *, approver_id: str) -> tuple[ApprovalRequest, str]:
        current = self.requests.get(request.id)
        if current is None:
            raise AuthorizationDenied(details={"reason": "APPROVAL_INVALID"})
        if current.expires_at <= utc_now():
            raise AuthorizationDenied(details={"reason": "APPROVAL_EXPIRED"})
        approved = current.approve(approver_id)
        grant = new_id()
        self.requests[approved.id] = approved
        self._grants[grant] = approved.id
        return approved, grant

    def get(self, request_id: str) -> ApprovalRequest:
        request = self.requests.get(request_id)
        if request is None:
            raise AuthorizationDenied(details={"reason": "APPROVAL_NOT_AVAILABLE"})
        return request

    def deny(
        self,
        request: ApprovalRequest,
        *,
        approver_id: str,
        reason: str,
    ) -> ApprovalRequest:
        current = self.get(request.id)
        if current.state is not ApprovalState.PENDING:
            raise AuthorizationDenied(details={"reason": "APPROVAL_NOT_PENDING"})
        if not reason.strip():
            raise ValueError("denial reason is required")
        denied = replace(
            current,
            state=ApprovalState.DENIED,
            decided_by=approver_id,
            decided_at=utc_now(),
            decision_reason=reason,
        )
        self.requests[denied.id] = denied
        return denied

    def consume(self, grant: str | None, binding: ApprovalBinding) -> ApprovalRequest:
        if grant is None:
            raise AuthorizationDenied(details={"reason": "APPROVAL_REQUIRED"})
        request_id = self._grants.get(grant)
        request = self.requests.get(request_id or "")
        if request is None:
            raise AuthorizationDenied(details={"reason": "APPROVAL_INVALID"})
        if request.state is ApprovalState.CONSUMED:
            raise AuthorizationDenied(details={"reason": "APPROVAL_ALREADY_CONSUMED"})
        if request.expires_at <= utc_now():
            self.requests[request.id] = replace(request, state=ApprovalState.EXPIRED)
            raise AuthorizationDenied(details={"reason": "APPROVAL_EXPIRED"})
        if request.state is not ApprovalState.APPROVED:
            raise AuthorizationDenied(details={"reason": "APPROVAL_INVALID"})
        if self._bindings[request.id] != binding:
            raise AuthorizationDenied(details={"reason": "APPROVAL_BINDING_MISMATCH"})
        consumed = replace(request, state=ApprovalState.CONSUMED)
        self.requests[request.id] = consumed
        return consumed
