"""EvaluationRun create/read contract and operator authorization."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI

from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.api.routes.evaluations import EvaluationService, create_evaluation_router
from atlasmind.evaluation.datasets import EvaluationDatasetRegistry
from atlasmind.evaluation.models import DatasetStatus, EvaluationDataset
from atlasmind.identity.models import Action


def auth(*, operator: bool = True) -> AuthContext:
    now = datetime.now(UTC)
    return AuthContext(
        principal_id="operator-1" if operator else "employee-1",
        role_codes=frozenset({"evaluation-operator"} if operator else {"employee"}),
        scope_ids=frozenset({"scope-public"}),
        allowed_actions=frozenset({Action.AUDIT} if operator else {Action.READ}),
        authz_revision=1,
        policy_revision=1,
        correlation_id="00000000-0000-0000-0000-000000000001",
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
    )


def app(*, operator: bool = True) -> FastAPI:
    datasets = EvaluationDatasetRegistry()
    datasets.register(
        EvaluationDataset(
            name="golden-basic",
            version="1",
            split="TUNING",
            knowledge_snapshot_digest="sha256:knowledge",
            status=DatasetStatus.APPROVED,
        )
    )
    api = FastAPI()
    api.include_router(
        create_evaluation_router(
            EvaluationService(datasets),
            lambda: auth(operator=operator),
        )
    )
    return api


@pytest.mark.asyncio
@pytest.mark.contract
async def test_create_and_read_evaluation_run_contract() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://test"
    ) as api:
        created = await api.post(
            "/v1/evaluation-runs",
            headers={"Idempotency-Key": "evaluation-golden-0001"},
            json={"datasetId": "golden-basic", "datasetVersion": "1"},
        )
        assert created.status_code == 202
        body = created.json()
        assert body["state"] == "QUEUED"
        assert body["dataset"] == {"id": "golden-basic", "version": "1"}
        assert "cases" not in body

        fetched = await api.get(f"/v1/evaluation-runs/{body['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["id"] == body["id"]


@pytest.mark.asyncio
@pytest.mark.contract
async def test_non_operator_and_unknown_dataset_are_not_available() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app(operator=False)), base_url="http://test"
    ) as api:
        denied = await api.post(
            "/v1/evaluation-runs",
            headers={"Idempotency-Key": "evaluation-denied-0001"},
            json={"datasetId": "golden-basic", "datasetVersion": "1"},
        )
    assert denied.status_code == 403

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://test"
    ) as api:
        unknown = await api.post(
            "/v1/evaluation-runs",
            headers={"Idempotency-Key": "evaluation-unknown-001"},
            json={"datasetId": "hidden", "datasetVersion": "99"},
        )
    assert unknown.status_code == 404
