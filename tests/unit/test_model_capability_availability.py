"""Model-dependent operations degrade explicitly when model configuration is absent."""

from __future__ import annotations

from typing import Any, cast

import httpx
import pytest

from atlasmind.api.app import create_app
from atlasmind.application.real_mvp import PersistentKnowledgeService
from atlasmind.domain.common import ModelCapabilityUnavailable
from atlasmind.runtime import UnavailableAI
from atlasmind.settings import Settings


def unavailable_service() -> PersistentKnowledgeService:
    unavailable = UnavailableAI(("CHAT", "EMBEDDING"))
    dependency = cast(Any, object())
    return PersistentKnowledgeService(
        dependency,
        dependency,
        dependency,
        unavailable,
        unavailable,
        missing_ai_capabilities=("CHAT", "EMBEDDING"),
    )


@pytest.mark.asyncio
async def test_model_dependent_operations_fail_before_creating_side_effects() -> None:
    service = unavailable_service()

    with pytest.raises(ModelCapabilityUnavailable) as upload_error:
        await service.upload(
            title="Policy",
            source_key="policy/test",
            file_name="policy.md",
            media_type="text/markdown",
            content=b"content",
            scope_ids=frozenset({"00000000-0000-4000-8000-000000000010"}),
            metadata={},
            actor_id="00000000-0000-4000-8000-000000000001",
            idempotency_key="model-unavailable",
        )
    assert upload_error.value.details["missingCapabilities"] == ["CHAT", "EMBEDDING"]

    with pytest.raises(ModelCapabilityUnavailable):
        await service.ask(
            query="What is the policy?",
            mode="AUTO",
            principal_id="00000000-0000-4000-8000-000000000001",
            scope_ids=frozenset({"00000000-0000-4000-8000-000000000010"}),
            authz_revision=1,
            correlation_id="00000000-0000-4000-8000-000000000099",
        )

    with pytest.raises(ModelCapabilityUnavailable):
        await service.retry_job("00000000-0000-4000-8000-000000000020")


@pytest.mark.asyncio
async def test_ingestion_worker_stays_idle_when_models_are_unconfigured() -> None:
    assert await unavailable_service().process_next() is None


@pytest.mark.asyncio
async def test_api_starts_and_reports_unconfigured_model_capabilities() -> None:
    settings = Settings(
        environment="development",
        auth_mode="local",
        database_url="postgresql+asyncpg://user:password@localhost:5432/atlasmind",
        object_store_endpoint="http://localhost:9000",
        object_store_access_key="local-access",
        object_store_secret_key="local-secret",
        neo4j_password="neo4j-local",
    )
    class UnconfiguredRuntime:
        def __init__(self) -> None:
            self.knowledge = unavailable_service()

        async def verify(self) -> None:
            return None

        async def close(self) -> None:
            return None

    app = create_app(settings=settings, runtime=cast(Any, UnconfiguredRuntime()))

    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        health = await client.get("/health/live")
        response = await client.post(
            "/v1/agent-runs",
            json={"query": "What is the policy?", "mode": "AUTO"},
        )

    assert health.status_code == 200
    assert response.status_code == 503
    assert response.json()["code"] == "MODEL_CAPABILITY_NOT_CONFIGURED"
    assert response.json()["detail"] == (
        "当前功能不可用: 尚未配置生成模型、Embedding 模型。"
    )
