"""Executable real-data API composition contract without external stores."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx
import pytest

from atlasmind.api.app import create_app
from atlasmind.runtime import LOCAL_SCOPE_ID
from atlasmind.settings import Settings


class StubKnowledge:
    def __init__(self) -> None:
        self.uploaded: dict[str, Any] | None = None

    async def upload(self, **values: Any) -> dict[str, object]:
        self.uploaded = values
        now = "2026-08-23T00:00:00+00:00"
        return {
            "document": {
                "id": str(uuid4()),
                "title": values["title"],
                "sourceKey": values["source_key"],
                "status": "ACTIVE",
                "activeVersionId": None,
                "knowledgeScopes": sorted(values["scope_ids"]),
                "createdAt": now,
            },
            "versionId": str(uuid4()),
            "ingestionJob": {
                "id": str(uuid4()),
                "documentVersionId": str(uuid4()),
                "state": "QUEUED",
                "currentStage": "VALIDATING",
                "attempt": 0,
                "failure": None,
                "createdAt": now,
                "finishedAt": None,
            },
        }


class StubRuntime:
    def __init__(self) -> None:
        self.knowledge = StubKnowledge()
        self.verified = False
        self.closed = False

    async def verify(self) -> None:
        self.verified = True

    async def close(self) -> None:
        self.closed = True


def settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="development",
        auth_mode="local",
        database_url="postgresql+asyncpg://user:password@localhost:5432/atlasmind",
        object_store_endpoint="http://localhost:9000",
        object_store_access_key="local-access",
        object_store_secret_key="local-secret",
        model_base_url="http://localhost:11434/v1",
        model_api_key="local-model",
        chat_model="chat-model",
        embedding_model="embedding-model",
        neo4j_password="neo4j-local",
    )


@pytest.mark.asyncio
async def test_local_api_upload_maps_scope_to_server_owned_uuid_without_demo_fallback(
    isolated_atlasmind_environment: None,
) -> None:
    runtime = StubRuntime()
    app = create_app(settings(), runtime=runtime)  # type: ignore[arg-type]

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client,
    ):
        health = await client.get("/health/live")
        response = await client.post(
            "/v1/documents",
            data={
                "title": "Architecture",
                "sourceKey": "architecture/runtime",
                "knowledgeScopeCodes": ["scope-public"],
                "metadata": '{"classification":"INTERNAL"}',
            },
            files={
                "file": (
                    "architecture.md",
                    b"AtlasMind uses PostgreSQL",
                    "text/markdown",
                )
            },
        )

    assert health.json() == {"status": "ok", "dataMode": "persistent"}
    assert response.status_code == 202, response.text
    assert runtime.knowledge.uploaded is not None
    assert runtime.knowledge.uploaded["scope_ids"] == frozenset({LOCAL_SCOPE_ID})
    assert runtime.verified is True
    assert runtime.closed is True
