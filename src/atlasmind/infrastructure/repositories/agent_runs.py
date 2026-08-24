"""AgentRun and RunStep persistence ports with PostgreSQL and deterministic adapters."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from atlasmind.agent.models import AgentRunState, RunStep
from atlasmind.domain.common import ResourceNotAvailable, new_id, utc_now


@dataclass(frozen=True, slots=True)
class PersistedAgentRun:
    principal_id: str
    correlation_id: str
    query_digest: str
    scope_ids: frozenset[str]
    authz_revision: int
    task_type: str
    id: str = field(default_factory=new_id)
    state: AgentRunState = AgentRunState.QUEUED
    degradation_reason: str | None = None


class AgentRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_run(self, run: PersistedAgentRun) -> None:
        await self._session.execute(
            text(
                """INSERT INTO agent_runs
                (id, principal_id, correlation_id, query_digest, scope_ids, authz_revision,
                 state, task_type, budgets, usage, created_at)
                VALUES
                (:id, :principal, :correlation, :query, :scopes, :revision,
                 :state, :task_type, '{}', '{}', :created_at)"""
            ),
            {
                "id": run.id,
                "principal": run.principal_id,
                "correlation": run.correlation_id,
                "query": run.query_digest,
                "scopes": list(run.scope_ids),
                "revision": run.authz_revision,
                "state": run.state.value,
                "task_type": run.task_type,
                "created_at": utc_now(),
            },
        )

    async def add_step(self, step: RunStep) -> None:
        await self._session.execute(
            text(
                """INSERT INTO run_steps
                (id, run_id, ordinal, kind, state, capability_name, capability_version,
                 input_digest, result_ref, started_at, finished_at)
                VALUES
                (:id, :run, :ordinal, :kind, :state, :capability, :version,
                 :digest, :result, :started, :finished)"""
            ),
            {
                "id": step.id,
                "run": step.run_id,
                "ordinal": step.ordinal,
                "kind": step.kind.value,
                "state": step.state.value,
                "capability": step.capability_name,
                "version": step.capability_version,
                "digest": step.input_digest,
                "result": step.result_ref,
                "started": step.started_at,
                "finished": step.finished_at,
            },
        )


class InMemoryAgentRunRepository:
    def __init__(self) -> None:
        self.runs: dict[str, PersistedAgentRun] = {}
        self.steps: dict[str, list[RunStep]] = {}

    def add(self, run: PersistedAgentRun) -> None:
        self.runs[run.id] = run

    def get(self, run_id: str) -> PersistedAgentRun:
        try:
            return self.runs[run_id]
        except KeyError as exc:
            raise ResourceNotAvailable() from exc

    def update_state(
        self,
        run_id: str,
        state: AgentRunState,
        *,
        degradation_reason: str | None = None,
    ) -> PersistedAgentRun:
        updated = replace(
            self.get(run_id),
            state=state,
            degradation_reason=degradation_reason,
        )
        self.runs[run_id] = updated
        return updated

    def append_step(self, step: RunStep) -> None:
        self.steps.setdefault(step.run_id, []).append(step)
