"""AgentRun create, read, and cancel REST routes."""

from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.domain.knowledge import AgentRun


class CreateAgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=16_000)
    mode: Literal["AUTO", "SIMPLE", "MULTI_SOURCE", "GRAPH"] = "AUTO"
    conversationId: str | None = None
    responseLanguage: str | None = Field(default=None, max_length=20)


class InMemoryAgentRunService:
    def __init__(self) -> None:
        self._runs: dict[str, AgentRun] = {}
        self._task_types: dict[str, str] = {}
        self._pending_approvals: dict[str, dict[str, Any]] = {}

    def create(self, request: CreateAgentRunRequest, context: AuthContext) -> AgentRun:
        run = AgentRun(
            principal_id=context.principal_id,
            query=request.query,
            correlation_id=context.correlation_id,
            scope_ids=context.scope_ids,
            authz_revision=context.authz_revision,
        )
        self._runs[run.id] = run
        task_type = request.mode
        if task_type == "AUTO":
            task_type = (
                "MULTI_SOURCE"
                if any(word in request.query.casefold() for word in ("analyze", "compare", "分析"))
                else "SIMPLE"
            )
        self._task_types[run.id] = task_type
        return run

    def get(self, run_id: str, context: AuthContext) -> AgentRun:
        run = self._runs.get(run_id)
        if run is None or run.principal_id != context.principal_id:
            raise KeyError(run_id)
        return run

    def cancel(self, run_id: str, context: AuthContext) -> AgentRun:
        run = self.get(run_id, context).cancel()
        self._runs[run.id] = run
        return run

    def serialize(self, run: AgentRun) -> dict[str, Any]:
        return serialize_run(
            run,
            task_type=self._task_types.get(run.id, "SIMPLE"),
            pending_approval=self._pending_approvals.get(run.id),
        )

    def set_pending_approval(self, run_id: str, summary: dict[str, Any]) -> None:
        self._pending_approvals[run_id] = dict(summary)


def serialize_run(
    run: AgentRun,
    *,
    task_type: str = "SIMPLE",
    pending_approval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    citations = [
        {
            "id": citation.id,
            "claim": citation.claim,
            "support": citation.support,
            "source": {
                "type": citation.source.type,
                "canonicalId": citation.source.canonical_id,
                "version": citation.source.version,
                "locator": citation.source.locator,
            },
        }
        for citation in run.citations
    ]
    answer = None
    if run.answer is not None:
        answer = {
            "text": run.answer,
            "confidence": "MEDIUM",
            "evidenceStatus": run.evidence_status,
            "limitations": [],
            "citations": citations,
        }
    return {
        "id": run.id,
        "correlationId": run.correlation_id,
        "state": run.state.value,
        "taskType": task_type,
        "createdAt": run.created_at.isoformat(),
        "finishedAt": None,
        "answer": answer,
        "pendingApproval": pending_approval,
        "failure": None,
        "links": {"self": f"/v1/agent-runs/{run.id}", "approval": None},
    }


def create_agent_run_router(
    service: InMemoryAgentRunService,
    auth_provider: Callable[[], AuthContext],
) -> APIRouter:
    router = APIRouter(prefix="/v1/agent-runs", tags=["Agent Runs"])

    async def resolve_auth() -> AuthContext:
        return auth_provider()

    @router.post("", status_code=status.HTTP_202_ACCEPTED)
    async def create(
        request: CreateAgentRunRequest,
        context: Annotated[AuthContext, Depends(resolve_auth)],
    ) -> dict[str, Any]:
        return service.serialize(service.create(request, context))

    @router.get("/{run_id}")
    async def get(
        run_id: str,
        context: Annotated[AuthContext, Depends(resolve_auth)],
    ) -> dict[str, Any]:
        try:
            return service.serialize(service.get(run_id, context))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Resource not available") from exc

    @router.post("/{run_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
    async def cancel(
        run_id: str,
        context: Annotated[AuthContext, Depends(resolve_auth)],
    ) -> dict[str, Any]:
        try:
            return service.serialize(service.cancel(run_id, context))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Resource not available") from exc

    return router
