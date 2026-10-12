"""Executable real-data API composition contract without external stores."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest

from atlasmind.agent.events import PersistedAgentEvent
from atlasmind.api.app import create_app
from atlasmind.retrieval.strategy_policy import default_advanced_retrieval_policy
from atlasmind.runtime import LOCAL_SCOPE_ID
from atlasmind.settings import Settings


class StubKnowledge:
    def __init__(self) -> None:
        self.uploaded: dict[str, Any] | None = None
        self.event_after: list[int] = []
        self.run_state = "COMPLETED"
        self.events: tuple[PersistedAgentEvent, ...] = ()

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

    async def list_documents(self, scope_ids: frozenset[str], *, limit: int) -> dict[str, object]:
        return {"items": [], "total": 0, "scopeIds": sorted(scope_ids), "limit": limit}

    async def list_runs(self, principal_id: str, *, limit: int) -> dict[str, object]:
        return {"items": [], "total": 0, "principalId": principal_id, "limit": limit}

    async def get_run(self, run_id: str, principal_id: str) -> dict[str, object]:
        return {"id": run_id, "principalId": principal_id, "state": self.run_state}

    async def list_run_events(
        self,
        run_id: str,
        principal_id: str,
        *,
        after: int,
        limit: int = 200,
    ) -> tuple[PersistedAgentEvent, ...]:
        del run_id, principal_id
        self.event_after.append(after)
        return tuple(item for item in self.events if item.sequence > after)[:limit]

    async def list_document_versions(
        self, document_id: str, scope_ids: frozenset[str]
    ) -> dict[str, object]:
        return {"items": [], "total": 0, "documentId": document_id, "scopeIds": sorted(scope_ids)}

    async def graph_snapshot(
        self,
        scope_ids: frozenset[str],
        *,
        limit: int,
        query: str | None = None,
        entity_types: frozenset[str] | None = None,
        relation_types: frozenset[str] | None = None,
        minimum_confidence: float | None = None,
    ) -> dict[str, object]:
        del query, entity_types, relation_types, minimum_confidence
        return {
            "nodes": [
                {
                    "id": str(uuid4()),
                    "name": "AtlasMind",
                    "type": "PRODUCT",
                    "aliases": [],
                    "mentionCount": 2,
                    "documentCount": 2,
                }
            ],
            "edges": [],
            "mode": "GLOBAL",
            "truncated": False,
            "scopeIds": sorted(scope_ids),
            "limit": limit,
        }

    async def search_graph_entities(
        self, scope_ids: frozenset[str], *, query: str,
        entity_types: frozenset[str] | None, limit: int,
    ) -> dict[str, object]:
        del scope_ids, entity_types, limit
        return {"items": [], "truncated": False, "query": query}

    async def get_graph_entity(
        self, entity_id: str, scope_ids: frozenset[str]
    ) -> dict[str, object]:
        del scope_ids
        return {
            "id": entity_id, "name": "AtlasMind", "type": "PRODUCT",
            "aliases": [], "mentionCount": 1, "documentCount": 1,
            "degree": 0, "properties": {}, "sourceDocuments": [],
        }

    async def graph_neighbors(
        self, entity_id: str, scope_ids: frozenset[str], *, depth: int,
        entity_types: frozenset[str] | None, relation_types: frozenset[str] | None,
        minimum_confidence: float | None, limit: int,
    ) -> dict[str, object]:
        del scope_ids, entity_types, relation_types, minimum_confidence, limit
        return {
            "nodes": [], "edges": [], "mode": "LOCAL", "truncated": False,
            "rootEntityId": entity_id, "depth": depth,
        }

    async def get_graph_relation(
        self, relation_id: str, scope_ids: frozenset[str]
    ) -> dict[str, object]:
        del scope_ids
        return {
            "id": relation_id, "source": str(uuid4()), "target": str(uuid4()),
            "type": "USES", "confidence": 0.9, "evidence": [],
        }

    async def get_graph_policy(self) -> object:
        class Policy:
            @staticmethod
            def as_api_dict() -> dict[str, object]:
                return {
                    "version": 1,
                    "allowedEntityTypes": ["API", "PRODUCT"],
                    "allowedRelationTypes": ["USES"],
                    "minimumEntityConfidence": 0.6,
                    "minimumRelationConfidence": 0.7,
                    "seedLimit": 8,
                    "maxHops": 2,
                    "maxNodes": 40,
                    "maxPaths": 24,
                    "maxGraphChunks": 24,
                    "allowedAliases": {},
                }

        return Policy()

    async def update_graph_policy(self, configuration: object, *, context: object) -> object:
        del configuration, context
        return await self.get_graph_policy()

    async def get_rag_policy(self) -> object:
        return default_advanced_retrieval_policy()

    async def get_rag_strategy_catalog(self) -> dict[str, object]:
        return {
            "policyVersion": 1,
            "strategies": [
                {
                    "id": "vector",
                    "stage": "RETRIEVAL",
                    "description": "Vector retrieval",
                    "enabled": True,
                    "settings": {},
                    "settingsSchema": {},
                    "planParametersSchema": {},
                    "conflictsWith": [],
                }
            ],
        }

    async def update_rag_policy(self, configuration: object, *, context: object) -> object:
        del configuration, context
        return default_advanced_retrieval_policy().model_copy(update={"version": 2})


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
        local_scope_id=LOCAL_SCOPE_ID,
        service_management_enabled=False,
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


async def test_service_audience_requires_explicit_public_upload_selection() -> None:
    runtime = StubRuntime()
    configured = settings().model_copy(update={"service_management_enabled": True})
    app = create_app(settings=configured, runtime=runtime)  # type: ignore[arg-type]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        for code, classification, expected in (
            ("scope-public", "INTERNAL", 202),
            ("scope-customer-service", "INTERNAL", 422),
            ("scope-customer-service", "PUBLIC", 202),
        ):
            response = await client.post("/v1/documents", data={
                "title": "audience test", "sourceKey": "test/audience",
                "knowledgeScopeCodes": code,
                "metadata": '{"classification":"' + classification + '"}',
            }, files={"file": ("test.txt", b"test", "text/plain")})
            assert response.status_code == expected
            if expected == 202:
                expected_scope = (configured.service_scope_id if code == "scope-customer-service"
                                  else configured.local_scope_id)
                assert runtime.knowledge.uploaded["scope_ids"] == frozenset({expected_scope})


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


@pytest.mark.asyncio
async def test_local_super_admin_can_list_real_documents_runs_and_versions() -> None:
    runtime = StubRuntime()
    app = create_app(settings=settings(), runtime=runtime)  # type: ignore[arg-type]
    document_id = str(uuid4())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client,
    ):
        documents = await client.get("/v1/documents?limit=12")
        runs = await client.get("/v1/agent-runs?limit=7")
        versions = await client.get(f"/v1/documents/{document_id}/versions")
        graph = await client.get("/v1/graph?limit=25")
        entity_search = await client.get("/v1/graph/entities?query=Atlas&limit=5")
        entity_detail = await client.get(f"/v1/graph/entities/{document_id}")
        local_graph = await client.get(
            f"/v1/graph/entities/{document_id}/neighbors?depth=2&minimumConfidence=0.8"
        )
        relation_detail = await client.get(f"/v1/graph/relations/{document_id}")
        capabilities = await client.get("/v1/capabilities")
        graph_policy = await client.get("/v1/graph/policy")
        updated_policy = await client.put(
            "/v1/graph/policy",
            json={
                "allowedEntityTypes": ["PRODUCT", "API"],
                "allowedRelationTypes": ["USES"],
            },
        )

    assert documents.status_code == 200
    assert documents.json()["scopeIds"] == [LOCAL_SCOPE_ID]
    assert documents.json()["limit"] == 12
    assert runs.status_code == 200
    assert runs.json()["principalId"] == "00000000-0000-4000-8000-000000000001"
    assert runs.json()["limit"] == 7
    assert versions.status_code == 200
    assert versions.json()["documentId"] == document_id
    assert graph.status_code == 200
    assert graph.json()["nodes"][0]["name"] == "AtlasMind"
    assert graph.json()["scopeIds"] == [LOCAL_SCOPE_ID]
    assert graph.json()["limit"] == 25
    assert entity_search.status_code == 200
    assert entity_search.json()["query"] == "Atlas"
    assert entity_detail.status_code == 200
    assert entity_detail.json()["id"] == document_id
    assert local_graph.status_code == 200
    assert local_graph.json()["mode"] == "LOCAL"
    assert local_graph.json()["depth"] == 2
    assert relation_detail.status_code == 200
    assert relation_detail.json()["id"] == document_id
    assert capabilities.status_code == 200
    assert capabilities.json()["localSuperAdmin"] is True
    assert capabilities.json()["features"]["approvals"] is False
    assert capabilities.json()["features"]["graphBrowse"] is True
    assert graph_policy.status_code == 200
    assert graph_policy.json()["maxHops"] == 2
    assert graph_policy.json()["canManage"] is True
    assert "ERROR_CODE" in graph_policy.json()["availableEntityTypes"]
    assert updated_policy.status_code == 200
    assert updated_policy.json()["canManage"] is True


@pytest.mark.asyncio
async def test_agent_event_stream_replays_after_last_event_id_and_closes_on_terminal() -> None:
    runtime = StubRuntime()
    run_id = str(uuid4())
    runtime.knowledge.events = (
        PersistedAgentEvent(
            sequence=2,
            event_type="RUN_FINISHED",
            payload={
                "type": "RUN_FINISHED",
                "threadId": run_id,
                "runId": run_id,
                "outcome": {"type": "success"},
            },
            created_at=datetime.now(UTC),
        ),
    )
    app = create_app(settings(), runtime=runtime)  # type: ignore[arg-type]

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client,
    ):
        response = await client.get(
            f"/v1/agent-runs/{run_id}/events?after=0",
            headers={"Last-Event-ID": "1"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert response.headers["x-accel-buffering"] == "no"
    assert runtime.knowledge.event_after[0] == 1
    assert response.text.startswith("id: 2\nevent: RUN_FINISHED\ndata: ")


@pytest.mark.asyncio
async def test_terminal_event_stream_closes_when_cursor_is_already_current() -> None:
    runtime = StubRuntime()
    runtime.knowledge.run_state = "COMPLETED"
    app = create_app(settings(), runtime=runtime)  # type: ignore[arg-type]

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client,
    ):
        response = await client.get(
            f"/v1/agent-runs/{uuid4()}/events",
            headers={"Last-Event-ID": "9"},
        )

    assert response.status_code == 200
    assert response.content == b""


@pytest.mark.asyncio
async def test_agent_event_stream_rejects_invalid_last_event_id() -> None:
    runtime = StubRuntime()
    app = create_app(settings(), runtime=runtime)  # type: ignore[arg-type]

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client,
    ):
        response = await client.get(
            f"/v1/agent-runs/{uuid4()}/events",
            headers={"Last-Event-ID": "-1"},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_rag_strategy_catalog_and_versioned_policy_contract() -> None:
    runtime = StubRuntime()
    app = create_app(settings(), runtime=runtime)  # type: ignore[arg-type]
    active = default_advanced_retrieval_policy()

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client,
    ):
        catalog = await client.get("/v1/rag/strategies")
        policy = await client.get("/v1/rag/policy")
        updated = await client.put("/v1/rag/policy", json=active.as_configuration())

    assert catalog.status_code == 200
    assert catalog.json()["strategies"][0]["id"] == "vector"
    assert policy.status_code == 200
    assert policy.json()["strategies"]["vector"]["enabled"] is True
    assert policy.json()["canManage"] is True
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
