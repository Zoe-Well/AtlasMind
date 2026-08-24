"""Document upload, version, read, and immediate revocation routes."""

import json
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile, status

from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.api.problem_details import problem_response
from atlasmind.application.ingest_document import (
    IngestionAccepted,
    InMemoryIngestionService,
    UploadDocument,
)
from atlasmind.domain.common import AuthorizationDenied, DomainError, new_id
from atlasmind.identity.models import Action
from atlasmind.ingestion.file_validation import UploadRejected
from atlasmind.ingestion.models import IngestionJob, ManagedDocument


def serialize_document(document: ManagedDocument, context: AuthContext) -> dict[str, Any]:
    return {
        "id": document.id,
        "title": document.title,
        "sourceKey": document.source_key,
        "status": document.status.value,
        "activeVersionId": document.active_version_id,
        "knowledgeScopes": sorted(document.scope_ids & context.scope_ids),
        "createdAt": document.created_at.isoformat(),
    }


def serialize_job(job: IngestionJob) -> dict[str, Any]:
    failure = None
    if job.failure_code:
        failure = {
            "code": "SOURCE_UNAVAILABLE",
            "message": "The ingestion stage could not be completed.",
            "retryable": job.attempt < job.max_attempts,
        }
    return {
        "id": job.id,
        "documentVersionId": job.document_version_id,
        "state": job.state.value,
        "currentStage": job.current_stage.value,
        "attempt": job.attempt,
        "failure": failure,
        "createdAt": job.created_at.isoformat(),
        "finishedAt": job.finished_at.isoformat() if job.finished_at else None,
    }


def serialize_upload(result: IngestionAccepted, context: AuthContext) -> dict[str, Any]:
    return {
        "document": serialize_document(result.document, context),
        "versionId": result.version.id,
        "ingestionJob": serialize_job(result.job),
    }


def _authorize_manage(context: AuthContext, scopes: frozenset[str]) -> None:
    if Action.MANAGE not in context.allowed_actions or not scopes.issubset(context.scope_ids):
        raise AuthorizationDenied(details={"reason": "KNOWLEDGE_MANAGEMENT_NOT_ALLOWED"})


def _metadata(value: str | None) -> dict[str, Any]:
    if value is None or not value.strip():
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("metadata must be a JSON object")
    return parsed


def create_document_router(
    service: InMemoryIngestionService,
    auth_dependency: Callable[[], AuthContext],
) -> APIRouter:
    router = APIRouter(prefix="/v1/documents", tags=["Knowledge"])

    async def resolve_auth() -> AuthContext:
        return auth_dependency()

    @router.post("", status_code=status.HTTP_202_ACCEPTED)
    async def upload_document(
        context: Annotated[AuthContext, Depends(resolve_auth)],
        file: Annotated[UploadFile, File()],
        title: Annotated[str, Form(min_length=1, max_length=500)],
        source_key: Annotated[str, Form(alias="sourceKey", min_length=1, max_length=300)],
        knowledge_scope_codes: Annotated[
            list[str], Form(alias="knowledgeScopeCodes", min_length=1)
        ],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
        metadata: Annotated[str | None, Form()] = None,
    ) -> Any:
        try:
            scopes = frozenset(knowledge_scope_codes)
            _authorize_manage(context, scopes)
            content = await file.read()
            accepted = await service.upload(
                UploadDocument(
                    title=title,
                    source_key=source_key,
                    file_name=file.filename or "upload.bin",
                    media_type=file.content_type or "application/octet-stream",
                    content=content,
                    scope_ids=scopes,
                    metadata=_metadata(metadata),
                    created_by=context.principal_id,
                    idempotency_key=idempotency_key,
                )
            )
            return serialize_upload(accepted, context)
        except UploadRejected as exc:
            return problem_response(
                DomainError(details={"reason": exc.reason}), context.correlation_id
            )
        except (DomainError, ValueError, json.JSONDecodeError) as exc:
            return problem_response(
                exc,
                context.correlation_id,
                conceal_authorization=False,
            )

    @router.get("/{document_id}")
    async def get_document(
        document_id: str,
        context: Annotated[AuthContext, Depends(resolve_auth)],
    ) -> Any:
        try:
            document = service.get_document(document_id)
            if not document.scope_ids.intersection(context.scope_ids):
                raise AuthorizationDenied()
            return serialize_document(document, context)
        except DomainError as exc:
            return problem_response(exc, context.correlation_id)

    @router.delete("/{document_id}", status_code=status.HTTP_202_ACCEPTED)
    async def revoke_document(
        document_id: str,
        context: Annotated[AuthContext, Depends(resolve_auth)],
    ) -> Any:
        try:
            document = service.get_document(document_id)
            _authorize_manage(context, document.scope_ids)
            return serialize_document(
                service.revoke_document(document_id, actor_id=context.principal_id), context
            )
        except DomainError as exc:
            return problem_response(
                exc,
                context.correlation_id,
                conceal_authorization=False,
            )

    @router.post("/{document_id}/versions", status_code=status.HTTP_202_ACCEPTED)
    async def upload_version(
        document_id: str,
        context: Annotated[AuthContext, Depends(resolve_auth)],
        file: Annotated[UploadFile, File()],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
        version_label: Annotated[str | None, Form(alias="versionLabel", max_length=100)] = None,
        metadata: Annotated[str | None, Form()] = None,
    ) -> Any:
        try:
            document = service.get_document(document_id)
            _authorize_manage(context, document.scope_ids)
            result = await service.add_version(
                document_id,
                file_name=file.filename or f"version-{new_id()}.bin",
                media_type=file.content_type or "application/octet-stream",
                content=await file.read(),
                metadata=_metadata(metadata),
                created_by=context.principal_id,
                idempotency_key=idempotency_key,
                version_label=version_label,
            )
            return serialize_upload(result, context)
        except UploadRejected as exc:
            return problem_response(
                DomainError(details={"reason": exc.reason}), context.correlation_id
            )
        except (DomainError, ValueError, json.JSONDecodeError) as exc:
            return problem_response(
                exc,
                context.correlation_id,
                conceal_authorization=False,
            )

    return router
