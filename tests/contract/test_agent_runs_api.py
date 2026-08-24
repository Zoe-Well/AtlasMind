"""AgentRun REST contract for the SIMPLE MVP."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI

from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.api.routes.agent_runs import InMemoryAgentRunService, create_agent_run_router
from atlasmind.identity.models import Action


def auth() -> AuthContext:
    now = datetime.now(UTC)
    return AuthContext(
        principal_id="principal-1",
        role_codes=frozenset({"employee"}),
        scope_ids=frozenset({"public"}),
        allowed_actions=frozenset({Action.READ, Action.CITE}),
        authz_revision=1,
        policy_revision=1,
        correlation_id="00000000-0000-0000-0000-000000000001",
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
    )


def app() -> FastAPI:
    app = FastAPI()
    app.include_router(create_agent_run_router(InMemoryAgentRunService(), auth))
    return app


@pytest.mark.asyncio
async def test_create_read_and_cancel_agent_run_contract() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://test"
    ) as api:
        created = await api.post(
            "/v1/agent-runs", json={"query": "What is the refund policy?", "mode": "SIMPLE"}
        )
        assert created.status_code == 202
        body = created.json()
        assert body["state"] == "QUEUED"
        assert body["taskType"] == "SIMPLE"
        assert body["links"]["self"].endswith(body["id"])
        assert "scope_ids" not in body and "principal_id" not in body

        fetched = await api.get(body["links"]["self"])
        assert fetched.status_code == 200
        cancelled = await api.post(f"{body['links']['self']}/cancel")
        assert cancelled.status_code == 202
        assert cancelled.json()["state"] == "CANCELLED"


@pytest.mark.asyncio
async def test_public_request_rejects_authority_fields() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://test"
    ) as api:
        response = await api.post(
            "/v1/agent-runs",
            json={"query": "secret", "scope_ids": ["secret"], "principal_id": "forged"},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_multi_source_and_auto_modes_expose_async_task_type() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://test"
    ) as api:
        explicit = await api.post(
            "/v1/agent-runs",
            json={"query": "Analyze refund failures", "mode": "MULTI_SOURCE"},
        )
        automatic = await api.post(
            "/v1/agent-runs",
            json={"query": "Analyze refund failures", "mode": "AUTO"},
        )

    assert explicit.status_code == 202
    assert explicit.json()["taskType"] == "MULTI_SOURCE"
    assert automatic.status_code == 202
    assert automatic.json()["taskType"] == "MULTI_SOURCE"
