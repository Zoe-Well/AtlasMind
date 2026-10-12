"""Executable FastAPI application backed only by persistent real-data services."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, Header, Query, Request, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse
from opentelemetry import trace
from pydantic import BaseModel, ConfigDict, Field

from atlasmind.agent.decisions import AgentMode
from atlasmind.api.middleware.auth_context import AuthContext, CorrelationIdMiddleware
from atlasmind.domain.common import AuthenticationRequired, DomainError, utc_now
from atlasmind.graph.policy import DEFAULT_ENTITY_TYPES
from atlasmind.identity.models import Action
from atlasmind.observability.telemetry import configure_telemetry
from atlasmind.retrieval.strategy_policy import (
    RetrievalRuntimeBudget,
    StrategyConfiguration,
)
from atlasmind.runtime import (
    LOCAL_PRINCIPAL_ID,
    Runtime,
    create_runtime,
)
from atlasmind.settings import AuthMode, Settings, load_settings


class CreateRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=16_000)
    mode: AgentMode = "AUTO"


class UpdateGraphPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    allowed_entity_types: set[str] = Field(alias="allowedEntityTypes", min_length=1)
    allowed_relation_types: set[str] = Field(alias="allowedRelationTypes", min_length=1)
    minimum_entity_confidence: float = Field(
        default=0.60, alias="minimumEntityConfidence", ge=0, le=1
    )
    minimum_relation_confidence: float = Field(
        default=0.70, alias="minimumRelationConfidence", ge=0, le=1
    )
    seed_limit: int = Field(default=8, alias="seedLimit", ge=1, le=30)
    max_hops: int = Field(default=2, alias="maxHops", ge=1, le=2)
    max_nodes: int = Field(default=40, alias="maxNodes", ge=2, le=200)
    max_paths: int = Field(default=24, alias="maxPaths", ge=1, le=100)
    max_graph_chunks: int = Field(default=24, alias="maxGraphChunks", ge=1, le=100)
    allowed_aliases: dict[str, str] = Field(default_factory=dict, alias="allowedAliases")


class UpdateRagPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    strategies: dict[str, StrategyConfiguration]
    budget: RetrievalRuntimeBudget = RetrievalRuntimeBudget()


async def runtime_auth_context(request: Request) -> AuthContext:
    configured: Settings = request.app.state.settings
    correlation_id = str(request.state.correlation_id)
    if configured.auth_mode is not AuthMode.LOCAL:
        raise AuthenticationRequired(details={"reason": "OIDC_RUNTIME_NOT_CONFIGURED"})
    now = utc_now()
    return AuthContext(
        principal_id=LOCAL_PRINCIPAL_ID,
        role_codes=frozenset(
            {"local-super-admin", "knowledge-admin", "tool-approver", "auditor", "employee"}
        ),
        scope_ids=frozenset(
            {configured.local_scope_id, configured.service_scope_id}
            if configured.service_management_enabled else {configured.local_scope_id}
        ),
        allowed_actions=frozenset(
            {Action.DISCOVER, Action.READ, Action.CITE, Action.MANAGE, Action.AUDIT}
        ),
        authz_revision=1,
        policy_revision=1,
        correlation_id=correlation_id,
        issued_at=now,
        expires_at=now + timedelta(hours=8),
    )


AuthContextDependency = Annotated[AuthContext, Depends(runtime_auth_context)]


def _problem(exc: Exception, correlation_id: str) -> JSONResponse:
    detail: str | None = None
    if isinstance(exc, DomainError):
        status_code = exc.status_code
        code = exc.code
        title = exc.public_message
        if code == "MODEL_CAPABILITY_NOT_CONFIGURED":
            missing = [str(value) for value in exc.details.get("missingCapabilities", ())]
            labels = {"CHAT": "生成模型", "EMBEDDING": "Embedding 模型"}
            names = "、".join(labels.get(value, value) for value in missing)
            detail = f"当前功能不可用: 尚未配置{names or '所需的 AI 模型'}。"
    elif isinstance(exc, (ValueError, json.JSONDecodeError)):
        status_code = 422
        code = "INVALID_REQUEST"
        title = str(exc) or "Invalid request"
    else:
        status_code = 500
        code = "INTERNAL_ERROR"
        title = "The request could not be completed."
    content: dict[str, object] = {
        "type": f"urn:atlasmind:error:{code.lower()}",
        "title": title,
        "status": status_code,
        "code": code,
        "correlationId": correlation_id,
    }
    if detail:
        content["detail"] = detail
    return JSONResponse(
        status_code=status_code,
        media_type="application/problem+json",
        content=content,
    )


def create_app(
    settings: Settings | None = None,
    runtime: Runtime | None = None,
) -> FastAPI:
    configured = settings or load_settings()
    dependencies = runtime or create_runtime(configured)
    configure_telemetry(
        "atlasmind-api",
        str(configured.otel_exporter_otlp_endpoint)
        if configured.otel_exporter_otlp_endpoint
        else None,
    )
    tracer = trace.get_tracer("atlasmind.api")

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await dependencies.verify()
        yield
        await dependencies.close()

    api = FastAPI(title="AtlasMind real-data MVP", version="0.1.0", lifespan=lifespan)
    api.state.runtime = dependencies
    api.state.settings = configured
    api.add_middleware(CorrelationIdMiddleware)

    def requested_scopes(values: list[str], context: AuthContext) -> frozenset[str]:
        resolved = {
            configured.local_scope_id if value == "scope-public" else
            configured.service_scope_id if value == "scope-customer-service"
            and configured.service_management_enabled else value
            for value in values
        }
        if not resolved or not resolved.issubset(context.scope_ids):
            raise ValueError("knowledge scope is not granted to the current identity")
        return frozenset(resolved)

    @api.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return _problem(exc, str(request.state.correlation_id))

    @api.exception_handler(Exception)
    async def exception_handler(request: Request, exc: Exception) -> JSONResponse:
        return _problem(exc, str(request.state.correlation_id))

    @api.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok", "dataMode": "persistent"}

    @api.get("/v1/capabilities")
    async def capabilities(_context: AuthContextDependency) -> dict[str, object]:
        return {
            "dataMode": "persistent",
            "localSuperAdmin": configured.auth_mode is AuthMode.LOCAL,
            "features": {
                "knowledge": True,
                "agentRuns": True,
                "graphConflicts": True,
                "graphBrowse": True,
                "approvals": False,
                "evaluations": False,
                "serviceKnowledge": configured.service_management_enabled,
            },
        }

    @api.post("/v1/documents", status_code=status.HTTP_202_ACCEPTED)
    async def upload_document(
        context: AuthContextDependency,
        file: Annotated[UploadFile, File()],
        title: Annotated[str, Form(min_length=1, max_length=500)],
        source_key: Annotated[str, Form(alias="sourceKey", min_length=1, max_length=300)],
        knowledge_scope_codes: Annotated[list[str], Form(alias="knowledgeScopeCodes")],
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        metadata: Annotated[str | None, Form()] = None,
    ) -> dict[str, object]:
        values = json.loads(metadata or "{}")
        if not isinstance(values, dict):
            raise ValueError("metadata must be a JSON object")
        scopes = requested_scopes(knowledge_scope_codes, context)
        if configured.service_scope_id in scopes and values.get("classification") != "PUBLIC":
            raise ValueError("商户客服知识必须为已审阅的公开通用资料")
        return await dependencies.knowledge.upload(
            title=title,
            source_key=source_key,
            file_name=file.filename or "upload.bin",
            media_type=file.content_type or "application/octet-stream",
            content=await file.read(),
            scope_ids=scopes,
            metadata=values,
            actor_id=context.principal_id,
            idempotency_key=idempotency_key or str(uuid4()),
            correlation_id=context.correlation_id,
        )

    @api.get("/v1/documents")
    async def list_documents(
        context: AuthContextDependency,
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
    ) -> dict[str, object]:
        return await dependencies.knowledge.list_documents(context.scope_ids, limit=limit)

    @api.get("/v1/documents/{document_id}")
    async def read_document(
        document_id: str,
        context: AuthContextDependency,
    ) -> dict[str, object]:
        return await dependencies.knowledge.get_document(document_id, context.scope_ids)

    @api.delete("/v1/documents/{document_id}", status_code=status.HTTP_202_ACCEPTED)
    async def revoke_document(
        document_id: str,
        context: AuthContextDependency,
    ) -> dict[str, object]:
        return await dependencies.knowledge.revoke_document(
            document_id,
            context.scope_ids,
            actor_id=context.principal_id,
            correlation_id=context.correlation_id,
        )

    @api.get("/v1/documents/{document_id}/versions")
    async def list_document_versions(
        document_id: str,
        context: AuthContextDependency,
    ) -> dict[str, object]:
        return await dependencies.knowledge.list_document_versions(document_id, context.scope_ids)

    @api.post("/v1/documents/{document_id}/versions", status_code=status.HTTP_202_ACCEPTED)
    async def upload_document_version(
        document_id: str,
        context: AuthContextDependency,
        file: Annotated[UploadFile, File()],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
        version_label: Annotated[str | None, Form(alias="versionLabel", max_length=100)] = None,
        metadata: Annotated[str | None, Form()] = None,
    ) -> dict[str, object]:
        values = json.loads(metadata or "{}")
        if not isinstance(values, dict):
            raise ValueError("metadata must be a JSON object")
        return await dependencies.knowledge.add_version(
            document_id=document_id,
            file_name=file.filename or "upload.bin",
            media_type=file.content_type or "application/octet-stream",
            content=await file.read(),
            scope_ids=context.scope_ids,
            metadata=values,
            actor_id=context.principal_id,
            idempotency_key=idempotency_key,
            correlation_id=context.correlation_id,
            version_label=version_label,
        )

    @api.get("/v1/ingestion-jobs/{job_id}")
    async def read_job(
        job_id: str,
        _context: AuthContextDependency,
    ) -> dict[str, object]:
        return await dependencies.knowledge.get_job(job_id)

    @api.post("/v1/ingestion-jobs/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
    async def retry_job(
        job_id: str,
        _context: AuthContextDependency,
    ) -> dict[str, object]:
        return await dependencies.knowledge.retry_job(job_id)

    @api.post("/v1/agent-runs", status_code=status.HTTP_202_ACCEPTED)
    async def create_run(
        body: CreateRun,
        context: AuthContextDependency,
    ) -> dict[str, object]:
        with tracer.start_as_current_span("atlasmind.agent_run") as span:
            span.set_attribute("atlasmind.correlation_id", context.correlation_id)
            trace_id = format(span.get_span_context().trace_id, "032x")
            result = await dependencies.knowledge.start_ask(
                query=body.query,
                mode=body.mode,
                context=context,
                trace_id=trace_id,
            )
            span.set_attribute("atlasmind.run_id", str(result["id"]))
            span.set_attribute("atlasmind.outcome", str(result["state"]))
            return result

    @api.get("/v1/agent-runs")
    async def list_runs(
        context: AuthContextDependency,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> dict[str, object]:
        return await dependencies.knowledge.list_runs(context.principal_id, limit=limit)

    @api.get("/v1/agent-runs/{run_id}")
    async def read_run(
        run_id: str,
        context: AuthContextDependency,
    ) -> dict[str, object]:
        return await dependencies.knowledge.get_run(run_id, context.principal_id)

    @api.get("/v1/agent-runs/{run_id}/events")
    async def stream_run_events(
        run_id: str,
        request: Request,
        context: AuthContextDependency,
        after: Annotated[int, Query(ge=0)] = 0,
        last_event_id: Annotated[
            int | None,
            Header(alias="Last-Event-ID", ge=0),
        ] = None,
    ) -> StreamingResponse:
        cursor = after
        if last_event_id is not None:
            cursor = max(cursor, last_event_id)

        initial = await dependencies.knowledge.list_run_events(
            run_id, context.principal_id, after=cursor, limit=1
        )
        initial_run = await dependencies.knowledge.get_run(run_id, context.principal_id)
        terminal_states = {"COMPLETED", "PARTIAL", "FAILED", "TIMED_OUT", "CANCELLED"}

        async def events() -> AsyncIterator[bytes]:
            current = cursor
            pending = initial
            heartbeat_ticks = 0
            terminal_without_pending = not pending and initial_run.get("state") in terminal_states
            while True:
                batch = pending or await dependencies.knowledge.list_run_events(
                    run_id, context.principal_id, after=current, limit=200
                )
                pending = ()
                if batch:
                    heartbeat_ticks = 0
                    for item in batch:
                        current = item.sequence
                        yield item.as_sse()
                        if item.is_terminal:
                            return
                    continue
                if terminal_without_pending:
                    return
                if await request.is_disconnected():
                    return
                await asyncio.sleep(0.35)
                heartbeat_ticks += 1
                if heartbeat_ticks % 10 == 0:
                    current_run = await dependencies.knowledge.get_run(run_id, context.principal_id)
                    if current_run.get("state") in terminal_states:
                        return
                if heartbeat_ticks >= 40:
                    heartbeat_ticks = 0
                    yield b": heartbeat\n\n"

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @api.post("/v1/agent-runs/{run_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
    async def cancel_run(
        run_id: str,
        context: AuthContextDependency,
    ) -> dict[str, object]:
        return await dependencies.knowledge.cancel_run(run_id, context.principal_id)

    @api.get("/v1/graph/conflicts")
    async def graph_conflicts(
        context: AuthContextDependency,
    ) -> dict[str, object]:
        return await dependencies.knowledge.graph_conflicts(context.scope_ids)

    @api.get("/v1/graph")
    async def graph_snapshot(
        context: AuthContextDependency,
        limit: Annotated[int, Query(ge=1, le=500)] = 200,
        query: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
        entity_types: Annotated[list[str] | None, Query(alias="entityType")] = None,
        relation_types: Annotated[list[str] | None, Query(alias="relationType")] = None,
        minimum_confidence: Annotated[
            float | None, Query(alias="minimumConfidence", ge=0, le=1)
        ] = None,
    ) -> dict[str, object]:
        return await dependencies.knowledge.graph_snapshot(
            context.scope_ids,
            limit=limit,
            query=query,
            entity_types=frozenset(entity_types) if entity_types else None,
            relation_types=frozenset(relation_types) if relation_types else None,
            minimum_confidence=minimum_confidence,
        )

    @api.get("/v1/graph/entities")
    async def search_graph_entities(
        context: AuthContextDependency,
        query: Annotated[str, Query(min_length=1, max_length=200)],
        entity_types: Annotated[list[str] | None, Query(alias="entityType")] = None,
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
    ) -> dict[str, object]:
        return await dependencies.knowledge.search_graph_entities(
            context.scope_ids,
            query=query,
            entity_types=frozenset(entity_types) if entity_types else None,
            limit=limit,
        )

    @api.get("/v1/graph/entities/{entity_id}")
    async def get_graph_entity(
        entity_id: str,
        context: AuthContextDependency,
    ) -> dict[str, object]:
        return await dependencies.knowledge.get_graph_entity(entity_id, context.scope_ids)

    @api.get("/v1/graph/entities/{entity_id}/neighbors")
    async def get_graph_neighbors(
        entity_id: str,
        context: AuthContextDependency,
        depth: Annotated[int, Query(ge=1, le=3)] = 1,
        entity_types: Annotated[list[str] | None, Query(alias="entityType")] = None,
        relation_types: Annotated[list[str] | None, Query(alias="relationType")] = None,
        minimum_confidence: Annotated[
            float | None, Query(alias="minimumConfidence", ge=0, le=1)
        ] = None,
        limit: Annotated[int, Query(ge=2, le=200)] = 80,
    ) -> dict[str, object]:
        return await dependencies.knowledge.graph_neighbors(
            entity_id,
            context.scope_ids,
            depth=depth,
            entity_types=frozenset(entity_types) if entity_types else None,
            relation_types=frozenset(relation_types) if relation_types else None,
            minimum_confidence=minimum_confidence,
            limit=limit,
        )

    @api.get("/v1/graph/relations/{relation_id}")
    async def get_graph_relation(
        relation_id: str,
        context: AuthContextDependency,
    ) -> dict[str, object]:
        return await dependencies.knowledge.get_graph_relation(relation_id, context.scope_ids)

    @api.get("/v1/graph/policy")
    async def get_graph_policy(context: AuthContextDependency) -> dict[str, object]:
        policy = await dependencies.knowledge.get_graph_policy()
        return {
            **policy.as_api_dict(),
            "availableEntityTypes": sorted(DEFAULT_ENTITY_TYPES),
            "canManage": Action.MANAGE in context.allowed_actions,
        }

    @api.get("/v1/rag/strategies")
    async def get_rag_strategies(
        _context: AuthContextDependency,
    ) -> dict[str, object]:
        return await dependencies.knowledge.get_rag_strategy_catalog()

    @api.get("/v1/rag/policy")
    async def get_rag_policy(context: AuthContextDependency) -> dict[str, object]:
        policy = await dependencies.knowledge.get_rag_policy()
        return {
            **policy.as_api_dict(),
            "canManage": Action.MANAGE in context.allowed_actions,
        }

    @api.put("/v1/rag/policy")
    async def update_rag_policy(
        body: UpdateRagPolicy,
        context: AuthContextDependency,
    ) -> dict[str, object]:
        policy = await dependencies.knowledge.update_rag_policy(
            body.model_dump(mode="json", by_alias=True),
            context=context,
        )
        return {
            **policy.as_api_dict(),
            "canManage": Action.MANAGE in context.allowed_actions,
        }

    @api.put("/v1/graph/policy")
    async def update_graph_policy(
        body: UpdateGraphPolicy,
        context: AuthContextDependency,
    ) -> dict[str, object]:
        policy = await dependencies.knowledge.update_graph_policy(
            body.model_dump(by_alias=False),
            context=context,
        )
        return {
            **policy.as_api_dict(),
            "availableEntityTypes": sorted(DEFAULT_ENTITY_TYPES),
            "canManage": Action.MANAGE in context.allowed_actions,
        }

    return api
