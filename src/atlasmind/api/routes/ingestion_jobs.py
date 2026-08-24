"""Ingestion job status and corrected-failure retry routes."""

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, status

from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.api.problem_details import problem_response
from atlasmind.api.routes.documents import _authorize_manage, serialize_job
from atlasmind.application.ingest_document import InMemoryIngestionService
from atlasmind.domain.common import AuthorizationDenied, DomainError


def create_ingestion_job_router(
    service: InMemoryIngestionService,
    auth_dependency: Callable[[], AuthContext],
) -> APIRouter:
    router = APIRouter(prefix="/v1/ingestion-jobs", tags=["Knowledge"])

    async def resolve_auth() -> AuthContext:
        return auth_dependency()

    @router.get("/{job_id}")
    async def get_job(
        job_id: str,
        context: Annotated[AuthContext, Depends(resolve_auth)],
    ) -> Any:
        try:
            job = service.get_job(job_id)
            version = service.get_version(job.document_version_id)
            if not version.scope_ids.intersection(context.scope_ids):
                raise AuthorizationDenied()
            return serialize_job(job)
        except DomainError as exc:
            return problem_response(exc, context.correlation_id)

    @router.post("/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
    async def retry_job(
        job_id: str,
        context: Annotated[AuthContext, Depends(resolve_auth)],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    ) -> Any:
        try:
            job = service.get_job(job_id)
            version = service.get_version(job.document_version_id)
            _authorize_manage(context, version.scope_ids)
            return serialize_job(service.retry_job(job_id, idempotency_key=idempotency_key))
        except DomainError as exc:
            return problem_response(
                exc,
                context.correlation_id,
                conceal_authorization=False,
            )

    return router
