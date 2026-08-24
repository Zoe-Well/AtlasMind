"""Approval grants are bound, expiring, and single use."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from atlasmind.domain.common import AuthorizationDenied, utc_now
from atlasmind.tools.approvals import ApprovalBinding, ApprovalService


def binding(**changes: str) -> ApprovalBinding:
    values = {
        "principal_id": "employee-1",
        "capability_name": "change.create",
        "capability_version": "1",
        "normalized_input_digest": "sha256:parameters",
        "target_resource": "change:refund-service",
        "run_id": "run-1",
        "correlation_id": "correlation-1",
    }
    values.update(changes)
    return ApprovalBinding(**values)


@pytest.mark.security
def test_approval_is_required_and_rejects_expired_or_changed_bindings() -> None:
    service = ApprovalService()
    with pytest.raises(AuthorizationDenied) as missing:
        service.consume(None, binding())
    assert missing.value.details["reason"] == "APPROVAL_REQUIRED"

    request, grant = service.approve(
        service.create(binding(), ttl=timedelta(minutes=5)),
        approver_id="approver-1",
    )
    service.requests[request.id] = replace(request, expires_at=utc_now() - timedelta(seconds=1))
    with pytest.raises(AuthorizationDenied) as expired:
        service.consume(grant, binding())
    assert expired.value.details["reason"] == "APPROVAL_EXPIRED"

    fresh_request, fresh_grant = service.approve(
        service.create(binding(), ttl=timedelta(minutes=5)),
        approver_id="approver-1",
    )
    assert fresh_request.id
    for changed in (
        binding(normalized_input_digest="sha256:changed"),
        binding(principal_id="employee-2"),
        binding(target_resource="change:other-service"),
    ):
        with pytest.raises(AuthorizationDenied) as mismatch:
            service.consume(fresh_grant, changed)
        assert mismatch.value.details["reason"] == "APPROVAL_BINDING_MISMATCH"


@pytest.mark.security
def test_approval_grant_can_be_consumed_only_once() -> None:
    service = ApprovalService()
    request, grant = service.approve(
        service.create(binding(), ttl=timedelta(minutes=5)),
        approver_id="approver-1",
    )

    consumed = service.consume(grant, binding())

    assert consumed.id == request.id
    with pytest.raises(AuthorizationDenied) as replay:
        service.consume(grant, binding())
    assert replay.value.details["reason"] == "APPROVAL_ALREADY_CONSUMED"
