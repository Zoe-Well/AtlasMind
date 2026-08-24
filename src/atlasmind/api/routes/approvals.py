"""Authorized approval challenge read and decision routes."""

from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, Field

from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.api.problem_details import problem_response
from atlasmind.domain.common import AuthorizationDenied, DomainError
from atlasmind.tools.approvals import ApprovalService


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["APPROVE", "DENY"]
    reason: str | None = Field(default=None, max_length=1_000)


def serialize_approval(request: Any) -> dict[str, Any]:
    return {
        "id": request.id,
        "state": request.state.value,
        "capability": f"{request.capability_name}@{request.capability_version}",
        "targetSummary": request.target_resource,
        "parameterSummary": {"digest": request.input_digest},
        "correlationId": request.correlation_id,
        "expiresAt": request.expires_at.isoformat(),
    }


def create_approval_router(
    service: ApprovalService,
    auth_dependency: Callable[[], AuthContext],
) -> APIRouter:
    router = APIRouter(prefix="/v1/approval-requests", tags=["Approvals"])

    async def resolve_auth() -> AuthContext:
        return auth_dependency()

    def authorize_approver(context: AuthContext) -> None:
        if "tool-approver" not in context.role_codes:
            raise AuthorizationDenied(details={"reason": "APPROVER_ROLE_REQUIRED"})

    @router.get("/{approval_id}")
    async def get_approval(
        approval_id: str,
        context: Annotated[AuthContext, Depends(resolve_auth)],
    ) -> Any:
        try:
            request = service.get(approval_id)
            if (
                request.principal_id != context.principal_id
                and "tool-approver" not in context.role_codes
            ):
                raise AuthorizationDenied()
            return serialize_approval(request)
        except DomainError as exc:
            return problem_response(exc, context.correlation_id)

    @router.post("/{approval_id}/decision")
    async def decide_approval(
        approval_id: str,
        decision: ApprovalDecision,
        context: Annotated[AuthContext, Depends(resolve_auth)],
        idempotency_key: Annotated[
            str,
            Header(alias="Idempotency-Key", min_length=16),
        ],
    ) -> Any:
        del idempotency_key
        try:
            authorize_approver(context)
            request = service.get(approval_id)
            if decision.decision == "APPROVE":
                decided, _grant = service.approve(request, approver_id=context.principal_id)
            else:
                decided = service.deny(
                    request,
                    approver_id=context.principal_id,
                    reason=decision.reason or "Denied by approver",
                )
            return serialize_approval(decided)
        except (DomainError, ValueError) as exc:
            return problem_response(
                exc,
                context.correlation_id,
                conceal_authorization=False,
            )

    return router
