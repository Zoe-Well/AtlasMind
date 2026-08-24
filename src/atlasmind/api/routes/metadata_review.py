"""Authorized critical metadata confirmation and correction route."""

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.api.problem_details import problem_response
from atlasmind.api.routes.documents import _authorize_manage
from atlasmind.application.ingest_document import InMemoryIngestionService
from atlasmind.domain.common import DomainError


class MetadataReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool
    corrections: dict[str, Any] = Field(default_factory=dict)


def create_metadata_review_router(
    service: InMemoryIngestionService,
    auth_dependency: Callable[[], AuthContext],
) -> APIRouter:
    router = APIRouter(prefix="/v1/document-versions", tags=["Knowledge"])

    async def resolve_auth() -> AuthContext:
        return auth_dependency()

    @router.post("/{version_id}/metadata-review")
    async def decide_metadata(
        version_id: str,
        request: MetadataReviewRequest,
        context: Annotated[AuthContext, Depends(resolve_auth)],
    ) -> Any:
        try:
            version = service.get_version(version_id)
            _authorize_manage(context, version.scope_ids)
            records = service.review_metadata(
                version_id,
                corrections=request.corrections,
                reviewer_id=context.principal_id,
                approved=request.approved,
            )
            return {
                "documentVersionId": version_id,
                "approved": request.approved,
                "metadata": {
                    key: {"value": item.value, "status": item.review_status.value}
                    for key, item in sorted(records.items())
                },
            }
        except DomainError as exc:
            return problem_response(
                exc,
                context.correlation_id,
                conceal_authorization=False,
            )

    return router
