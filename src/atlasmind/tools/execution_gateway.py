"""Deterministic validation, authorization, budget, execution, review, and audit gateway."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from hashlib import sha256

from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.domain.common import AuthorizationDenied, BudgetExceeded
from atlasmind.identity.authorization import AuthorizationService
from atlasmind.identity.models import AuthorizationSnapshot
from atlasmind.tools.approvals import ApprovalBinding, ApprovalService
from atlasmind.tools.contracts import CapabilityDescriptor, CapabilityRequest, CapabilityResult

CapabilityHandler = Callable[[CapabilityRequest, frozenset[str]], Awaitable[CapabilityResult]]
AuditWriter = Callable[[str, CapabilityRequest], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class RegisteredCapability:
    descriptor: CapabilityDescriptor
    handler: CapabilityHandler


class CapabilityRegistry:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], RegisteredCapability] = {}

    def register(self, descriptor: CapabilityDescriptor, handler: CapabilityHandler) -> None:
        key = (descriptor.name, descriptor.version)
        if key in self._items:
            raise ValueError("capability version already registered")
        self._items[key] = RegisteredCapability(descriptor, handler)

    def get(self, name: str, version: str) -> RegisteredCapability:
        try:
            return self._items[(name, version)]
        except KeyError as exc:
            raise AuthorizationDenied(details={"reason": "CAPABILITY_NOT_AVAILABLE"}) from exc


class ExecutionGateway:
    def __init__(
        self,
        registry: CapabilityRegistry,
        audit: AuditWriter,
        approval_service: ApprovalService | None = None,
    ) -> None:
        self._registry = registry
        self._audit = audit
        self._authorization = AuthorizationService()
        self._approvals = approval_service

    async def execute(
        self,
        request: CapabilityRequest,
        context: AuthContext,
        current: AuthorizationSnapshot,
    ) -> CapabilityResult:
        item = self._registry.get(request.capability_name, request.capability_version)
        descriptor = item.descriptor
        if request.budget.timeout_ms > descriptor.timeout_ms:
            raise BudgetExceeded(details={"reason": "TIME_BUDGET_EXCEEDED"})
        if request.budget.max_items > descriptor.max_items:
            raise BudgetExceeded(details={"reason": "ITEM_BUDGET_EXCEEDED"})
        if request.budget.max_result_bytes > descriptor.max_result_bytes:
            raise BudgetExceeded(details={"reason": "RESULT_BUDGET_EXCEEDED"})
        if descriptor.idempotency_required and not request.idempotency_key:
            raise ValueError("idempotency key required")

        scopes = context.scope_ids & current.active_scope_ids
        for action in descriptor.required_actions:
            scopes = self._authorization.authorize(
                context,
                action=action,
                requested_scope_ids=scopes,
                current=current,
            )
        if not descriptor.required_actions or not scopes:
            raise AuthorizationDenied(details={"reason": "AUTHORIZATION_REQUIREMENTS_MISSING"})
        if descriptor.side_effect:
            if self._approvals is None:
                raise AuthorizationDenied(details={"reason": "APPROVAL_REQUIRED"})
            canonical_input = json.dumps(
                request.input,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            self._approvals.consume(
                request.approval_grant_ref,
                ApprovalBinding(
                    principal_id=context.principal_id,
                    capability_name=request.capability_name,
                    capability_version=request.capability_version,
                    normalized_input_digest=f"sha256:{sha256(canonical_input).hexdigest()}",
                    target_resource=str(request.input.get("targetResource", "")),
                    run_id=request.run_id,
                    correlation_id=context.correlation_id,
                ),
            )
        try:
            result = await asyncio.wait_for(
                item.handler(request, scopes),
                timeout=request.budget.timeout_ms / 1_000,
            )
        except TimeoutError:
            await self._audit("TIMED_OUT", request)
            return CapabilityResult(status="FAILED", reason_code="TIMED_OUT", retryable=True)
        if any(not evidence.scope_ids.issubset(scopes) for evidence in result.evidence):
            raise AuthorizationDenied(details={"reason": "RESULT_SCOPE_INVALID"})
        if len(result.evidence) > request.budget.max_items:
            raise BudgetExceeded(details={"reason": "ITEM_BUDGET_EXCEEDED"})
        if len(result.model_dump_json().encode()) > request.budget.max_result_bytes:
            raise BudgetExceeded(details={"reason": "RESULT_BUDGET_EXCEEDED"})
        await self._audit(result.status, request)
        return result
