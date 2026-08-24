"""Authorized EvaluationRun creation and status routes."""

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, ConfigDict

from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.api.problem_details import problem_response
from atlasmind.domain.common import AuthorizationDenied, DomainError
from atlasmind.evaluation.datasets import EvaluationDatasetRegistry
from atlasmind.evaluation.models import EvaluationRun
from atlasmind.identity.models import Action


class CreateEvaluationRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    datasetId: str
    datasetVersion: str
    retrievalPolicyVersion: str | None = None


class EvaluationService:
    def __init__(self, datasets: EvaluationDatasetRegistry) -> None:
        self.datasets = datasets
        self.runs: dict[str, EvaluationRun] = {}
        self._idempotency: dict[str, EvaluationRun] = {}

    def create(
        self,
        request: CreateEvaluationRunRequest,
        context: AuthContext,
        *,
        idempotency_key: str,
    ) -> EvaluationRun:
        if Action.AUDIT not in context.allowed_actions:
            raise AuthorizationDenied(details={"reason": "EVALUATION_NOT_ALLOWED"})
        cached = self._idempotency.get(idempotency_key)
        if cached is not None:
            return cached
        dataset = self.datasets.get_for_run(request.datasetId, request.datasetVersion)
        run = EvaluationRun(
            dataset_id=str(dataset.id),
            dataset_version=dataset.version,
            requested_by=context.principal_id,
            correlation_id=context.correlation_id,
        )
        self.runs[run.id] = run
        self._idempotency[idempotency_key] = run
        return run

    def get(self, run_id: str, context: AuthContext) -> EvaluationRun:
        run = self.runs.get(run_id)
        if run is None or Action.AUDIT not in context.allowed_actions:
            raise AuthorizationDenied(details={"reason": "EVALUATION_NOT_AVAILABLE"})
        return run


def serialize_run(run: EvaluationRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "dataset": {"id": run.dataset_id, "version": run.dataset_version},
        "state": run.state.value,
        "createdAt": run.created_at.isoformat(),
        "finishedAt": run.finished_at.isoformat() if run.finished_at else None,
        "reportRef": run.report_ref,
    }


def create_evaluation_router(
    service: EvaluationService,
    auth_dependency: Callable[[], AuthContext],
) -> APIRouter:
    router = APIRouter(prefix="/v1/evaluation-runs", tags=["Evaluation"])

    async def resolve_auth() -> AuthContext:
        return auth_dependency()

    @router.post("", status_code=status.HTTP_202_ACCEPTED)
    async def create(
        request: CreateEvaluationRunRequest,
        context: Annotated[AuthContext, Depends(resolve_auth)],
        idempotency_key: Annotated[
            str,
            Header(alias="Idempotency-Key", min_length=16),
        ],
    ) -> Any:
        try:
            return serialize_run(service.create(request, context, idempotency_key=idempotency_key))
        except DomainError as exc:
            return problem_response(
                exc,
                context.correlation_id,
                conceal_authorization=False,
            )

    @router.get("/{evaluation_run_id}")
    async def get(
        evaluation_run_id: str,
        context: Annotated[AuthContext, Depends(resolve_auth)],
    ) -> Any:
        try:
            return serialize_run(service.get(evaluation_run_id, context))
        except DomainError as exc:
            return problem_response(exc, context.correlation_id)

    return router
