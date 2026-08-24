"""Executable FastAPI application backed only by persistent real-data services."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, Header, Request, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from atlasmind.api.middleware.auth_context import AuthContext, CorrelationIdMiddleware
from atlasmind.domain.common import AuthenticationRequired, DomainError, utc_now
from atlasmind.identity.models import Action
from atlasmind.runtime import (
    LOCAL_PRINCIPAL_ID,
    LOCAL_SCOPE_ID,
    Runtime,
    create_runtime,
)
from atlasmind.settings import AuthMode, Settings, load_settings


class CreateRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=16_000)
    mode: str = "AUTO"


async def runtime_auth_context(request: Request) -> AuthContext:
    configured: Settings = request.app.state.settings
    correlation_id = str(request.state.correlation_id)
    if configured.auth_mode is not AuthMode.LOCAL:
        raise AuthenticationRequired(details={"reason": "OIDC_RUNTIME_NOT_CONFIGURED"})
    now = utc_now()
    return AuthContext(
        principal_id=LOCAL_PRINCIPAL_ID,
        role_codes=frozenset({"knowledge-admin", "employee"}),
        scope_ids=frozenset({LOCAL_SCOPE_ID}),
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
            LOCAL_SCOPE_ID if value in {"scope-public", LOCAL_SCOPE_ID} else value
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
        return await dependencies.knowledge.upload(
            title=title,
            source_key=source_key,
            file_name=file.filename or "upload.bin",
            media_type=file.content_type or "application/octet-stream",
            content=await file.read(),
            scope_ids=requested_scopes(knowledge_scope_codes, context),
            metadata=values,
            actor_id=context.principal_id,
            idempotency_key=idempotency_key or str(uuid4()),
        )

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
        return await dependencies.knowledge.revoke_document(document_id, context.scope_ids)

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
        return await dependencies.knowledge.ask(
            query=body.query,
            mode=body.mode,
            principal_id=context.principal_id,
            scope_ids=context.scope_ids,
            authz_revision=context.authz_revision,
            correlation_id=context.correlation_id,
        )

    @api.get("/v1/agent-runs/{run_id}")
    async def read_run(
        run_id: str,
        context: AuthContextDependency,
    ) -> dict[str, object]:
        return await dependencies.knowledge.get_run(run_id, context.principal_id)

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

    return api
