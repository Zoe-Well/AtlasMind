"""Graph entity merge and conflicted relation governance routes."""

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.api.problem_details import problem_response
from atlasmind.domain.common import AuthorizationDenied, DomainError, ResourceNotAvailable
from atlasmind.graph.entity_resolution import EntityResolver
from atlasmind.graph.models import GraphRepository, RelationStatus
from atlasmind.identity.models import Action


class EntityMergeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    targetEntityId: str
    approved: bool


def create_graph_governance_router(
    repository: GraphRepository,
    auth_dependency: Callable[[], AuthContext],
) -> APIRouter:
    router = APIRouter(prefix="/v1/graph", tags=["Graph Governance"])
    resolver = EntityResolver()

    async def resolve_auth() -> AuthContext:
        return auth_dependency()

    def authorize(context: AuthContext) -> None:
        if Action.MANAGE not in context.allowed_actions:
            raise AuthorizationDenied(details={"reason": "GRAPH_MANAGEMENT_NOT_ALLOWED"})

    @router.get("/conflicts")
    async def conflicts(
        context: Annotated[AuthContext, Depends(resolve_auth)],
    ) -> Any:
        try:
            authorize(context)
            return {
                "relations": [
                    relation.id
                    for relation in repository.relations.values()
                    if relation.status is RelationStatus.CONFLICTED
                ]
            }
        except DomainError as exc:
            return problem_response(exc, context.correlation_id, conceal_authorization=False)

    @router.post("/entities/{entity_id}/merge")
    async def merge_entity(
        entity_id: str,
        request: EntityMergeRequest,
        context: Annotated[AuthContext, Depends(resolve_auth)],
    ) -> Any:
        try:
            authorize(context)
            source = repository.entities.get(entity_id)
            target = repository.entities.get(request.targetEntityId)
            if source is None or target is None:
                raise ResourceNotAvailable()
            merged = resolver.merge(source, target, approved=request.approved)
            repository.entities[merged.id] = merged
            return {
                "id": merged.id,
                "status": merged.status.value,
                "mergedIntoId": merged.merged_into_id,
            }
        except (DomainError, ValueError) as exc:
            return problem_response(
                exc,
                context.correlation_id,
                conceal_authorization=False,
            )

    return router
