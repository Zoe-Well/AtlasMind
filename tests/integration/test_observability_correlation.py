"""API through evaluation and audit retain a single safe correlation chain."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.identity.models import Action
from atlasmind.infrastructure.outbox import DataClassification, EventEnvelope
from atlasmind.observability.audit import AuditEvent
from atlasmind.observability.audit_repository import InMemoryAuditRepository
from atlasmind.observability.instrumentation import InMemoryInstrumentation


@pytest.mark.integration
def test_api_outbox_worker_agent_tool_evaluation_and_audit_are_correlated() -> None:
    correlation_id = "00000000-0000-0000-0000-000000000001"
    instrumentation = InMemoryInstrumentation()
    for name in ("api", "outbox", "worker", "agent", "tool", "evaluation"):
        instrumentation.record_span(
            name,
            {
                "atlasmind.correlation_id": correlation_id,
                "atlasmind.outcome": "SUCCEEDED",
                "query": "must not be exported",
            },
        )
    event = EventEnvelope.create(
        event_type="evaluation.requested.v1",
        producer="atlasmind-api",
        correlation_id=correlation_id,
        aggregate_type="EVALUATION_RUN",
        aggregate_id="evaluation-1",
        aggregate_version=1,
        classification=DataClassification.INTERNAL,
        payload={"datasetId": "golden-basic", "datasetVersion": "1"},
    )
    event.validate()
    audits = InMemoryAuditRepository()
    audits.append(
        AuditEvent(
            event_type="evaluation.completed",
            actor_principal_id="operator-1",
            correlation_id=correlation_id,
            decision="ALLOW",
            reason_code="PASSED",
            resource_type="EVALUATION_RUN",
            resource_id="evaluation-1",
            payload={"manifestDigest": "sha256:manifest"},
        )
    )
    now = datetime.now(UTC)
    operator = AuthContext(
        principal_id="operator-1",
        role_codes=frozenset({"operations"}),
        scope_ids=frozenset({"scope-public"}),
        allowed_actions=frozenset({Action.AUDIT}),
        authz_revision=1,
        policy_revision=1,
        correlation_id=correlation_id,
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
    )

    assert all(
        span.attributes["atlasmind.correlation_id"] == correlation_id
        for span in instrumentation.spans
    )
    assert all("query" not in span.attributes for span in instrumentation.spans)
    assert event.correlation_id == correlation_id
    assert audits.by_correlation(correlation_id, operator)[0].correlation_id == correlation_id
