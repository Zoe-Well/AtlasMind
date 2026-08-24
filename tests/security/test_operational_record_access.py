"""Operational records are owner-bound and separately operator-authorized."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.application.inspect_runs import OperationalRunRecord, RunInspector
from atlasmind.domain.common import ResourceNotAvailable
from atlasmind.identity.models import Action
from atlasmind.observability.audit import AuditEvent
from atlasmind.observability.audit_repository import InMemoryAuditRepository


def context(principal: str, *, operator: bool = False) -> AuthContext:
    now = datetime.now(UTC)
    return AuthContext(
        principal_id=principal,
        role_codes=frozenset({"operations"} if operator else {"employee"}),
        scope_ids=frozenset({"scope-public"}),
        allowed_actions=frozenset({Action.AUDIT} if operator else {Action.READ}),
        authz_revision=1,
        policy_revision=1,
        correlation_id="00000000-0000-0000-0000-000000000001",
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
    )


@pytest.mark.security
def test_employee_cannot_read_other_run_trace_or_evaluation_record() -> None:
    inspector = RunInspector()
    inspector.add(
        OperationalRunRecord(
            run_id="run-1",
            principal_id="employee-1",
            correlation_id="correlation-1",
            state="COMPLETED",
            trace_ref="trace:run-1",
            evaluation_run_ids=("evaluation-1",),
        )
    )

    assert inspector.get("run-1", context("employee-1")).trace_ref == "trace:run-1"
    with pytest.raises(ResourceNotAvailable):
        inspector.get("run-1", context("employee-2"))
    assert inspector.get("run-1", context("operator-1", operator=True)).run_id == "run-1"


@pytest.mark.security
def test_audit_events_require_separate_audit_permission() -> None:
    repository = InMemoryAuditRepository()
    repository.append(
        AuditEvent(
            event_type="agent.completed",
            actor_principal_id="employee-1",
            correlation_id="correlation-1",
            decision="ALLOW",
            reason_code="COMPLETED",
            resource_type="AGENT_RUN",
            resource_id="run-1",
            payload={},
        )
    )

    with pytest.raises(ResourceNotAvailable):
        repository.by_correlation("correlation-1", context("employee-1"))
    events = repository.by_correlation(
        "correlation-1",
        context("operator-1", operator=True),
    )
    assert len(events) == 1
