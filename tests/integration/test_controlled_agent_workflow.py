"""US3 end-to-end controlled capability, approval, and worker workflow."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import httpx
import pytest
from fastapi import FastAPI

from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.api.routes.approvals import create_approval_router
from atlasmind.domain.common import AuthorizationDenied
from atlasmind.identity.models import Action, AuthorizationSnapshot
from atlasmind.tools.approvals import ApprovalBinding, ApprovalService
from atlasmind.tools.contracts import (
    CapabilityBudget,
    CapabilityDescriptor,
    CapabilityKind,
    CapabilityRequest,
    CapabilityResult,
    RiskLevel,
)
from atlasmind.tools.execution_gateway import CapabilityRegistry, ExecutionGateway


def context() -> AuthContext:
    now = datetime.now(UTC)
    return AuthContext(
        principal_id="employee-1",
        role_codes=frozenset({"employee"}),
        scope_ids=frozenset({"scope-public"}),
        allowed_actions=frozenset({Action.MANAGE}),
        authz_revision=3,
        policy_revision=1,
        correlation_id="00000000-0000-0000-0000-000000000001",
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
    )


def approver_context() -> AuthContext:
    return replace(
        context(),
        principal_id="approver-1",
        role_codes=frozenset({"tool-approver"}),
    )


def request(*, grant: str | None) -> CapabilityRequest:
    return CapabilityRequest(
        request_id="request-1",
        run_id="run-1",
        step_id="step-1",
        capability_name="change.create",
        capability_version="1",
        auth_context_ref="trusted-context-1",
        input={"targetResource": "change:refund-service", "summary": "Tune retry policy"},
        budget=CapabilityBudget(timeout_ms=1_000, max_items=1, max_result_bytes=1_024),
        idempotency_key="change-create-1",
        approval_grant_ref=grant,
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_side_effect_executes_once_only_after_bound_approval() -> None:
    calls = 0
    audits: list[str] = []

    async def handler(
        capability_request: CapabilityRequest,
        scopes: frozenset[str],
    ) -> CapabilityResult:
        nonlocal calls
        assert capability_request.input["targetResource"] == "change:refund-service"
        assert scopes == frozenset({"scope-public"})
        calls += 1
        return CapabilityResult(status="SUCCEEDED")

    async def audit(status: str, _: CapabilityRequest) -> None:
        audits.append(status)

    registry = CapabilityRegistry()
    registry.register(
        CapabilityDescriptor(
            name="change.create",
            version="1",
            kind=CapabilityKind.EXTERNAL_TOOL,
            required_actions=frozenset({Action.MANAGE}),
            risk_level=RiskLevel.HIGH,
            side_effect=True,
            timeout_ms=2_000,
            max_result_bytes=2_048,
            max_items=2,
            idempotency_required=True,
        ),
        handler,
    )
    approvals = ApprovalService()
    gateway = ExecutionGateway(registry, audit, approvals)
    current = AuthorizationSnapshot(3, frozenset({"scope-public"}))

    with pytest.raises(AuthorizationDenied) as missing:
        await gateway.execute(request(grant=None), context(), current)
    assert missing.value.details["reason"] == "APPROVAL_REQUIRED"
    assert calls == 0

    pending_request = request(grant=None)
    canonical = json.dumps(
        pending_request.input,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    approval, grant = approvals.approve(
        approvals.create(
            ApprovalBinding(
                principal_id="employee-1",
                capability_name="change.create",
                capability_version="1",
                normalized_input_digest=f"sha256:{sha256(canonical).hexdigest()}",
                target_resource="change:refund-service",
                run_id="run-1",
                correlation_id=context().correlation_id,
            ),
            ttl=timedelta(minutes=5),
        ),
        approver_id="approver-1",
    )
    assert approval.state.value == "APPROVED"

    result = await gateway.execute(request(grant=grant), context(), current)

    assert result.status == "SUCCEEDED"
    assert calls == 1
    assert audits == ["SUCCEEDED"]
    with pytest.raises(AuthorizationDenied) as replay:
        await gateway.execute(request(grant=grant), context(), current)
    assert replay.value.details["reason"] == "APPROVAL_ALREADY_CONSUMED"
    assert calls == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_approval_rest_is_visible_and_decidable_only_by_bound_roles() -> None:
    approvals = ApprovalService()
    approval = approvals.create(
        ApprovalBinding(
            principal_id="employee-1",
            capability_name="change.create",
            capability_version="1",
            normalized_input_digest="sha256:parameters",
            target_resource="change:refund-service",
            run_id="run-1",
            correlation_id=context().correlation_id,
        ),
        ttl=timedelta(minutes=5),
    )
    active_context = {"value": context()}
    app = FastAPI()
    app.include_router(create_approval_router(approvals, lambda: active_context["value"]))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as api:
        visible = await api.get(f"/v1/approval-requests/{approval.id}")
        assert visible.status_code == 200
        assert visible.json()["state"] == "PENDING"

        denied = await api.post(
            f"/v1/approval-requests/{approval.id}/decision",
            headers={"Idempotency-Key": "employee-cannot-approve"},
            json={"decision": "APPROVE"},
        )
        assert denied.status_code == 403

        active_context["value"] = approver_context()
        decided = await api.post(
            f"/v1/approval-requests/{approval.id}/decision",
            headers={"Idempotency-Key": "approval-decision-0001"},
            json={"decision": "APPROVE"},
        )
        assert decided.status_code == 200
        assert decided.json()["state"] == "APPROVED"
