"""Deterministic bounded multi-source Agent application service."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from atlasmind.agent.budgets import AgentBudgets
from atlasmind.agent.degradation import SourceOutcome
from atlasmind.agent.models import AgentRunState, RunStep, StepKind
from atlasmind.domain.common import new_id

SourceHandler = Callable[[str], SourceOutcome | Awaitable[SourceOutcome]]


@dataclass(frozen=True, slots=True)
class MultiSourceRequest:
    query: str
    source_names: tuple[str, ...]
    budgets: AgentBudgets


@dataclass(frozen=True, slots=True)
class MultiSourceResult:
    run_id: str
    state: AgentRunState
    facts: tuple[str, ...]
    steps: tuple[RunStep, ...]
    degradation_reasons: tuple[str, ...] = ()
    failure_code: str | None = None


class MultiSourceAgent:
    def __init__(self, *, sources: dict[str, SourceHandler]) -> None:
        self._sources = dict(sources)

    async def run(self, request: MultiSourceRequest) -> MultiSourceResult:
        run_id = new_id()
        required_steps = len(request.source_names) + 2
        if not request.budgets.permits(steps=required_steps, tools=len(request.source_names)):
            return MultiSourceResult(
                run_id=run_id,
                state=AgentRunState.FAILED,
                facts=(),
                steps=(),
                failure_code="BUDGET_EXCEEDED",
            )

        steps = [RunStep(run_id=run_id, ordinal=1, kind=StepKind.PLAN).complete()]
        facts: list[str] = []
        reasons: list[str] = []
        per_source_timeout = request.budgets.timeout_ms / 1_000
        for ordinal, source_name in enumerate(request.source_names, start=2):
            handler = self._sources.get(source_name)
            if handler is None:
                outcome = SourceOutcome.failed(source_name, "SOURCE_UNAVAILABLE")
            else:
                try:
                    outcome = await asyncio.wait_for(
                        self._invoke(handler, request.query),
                        timeout=per_source_timeout,
                    )
                except TimeoutError:
                    outcome = SourceOutcome.failed(source_name, "TIMED_OUT")
            if outcome.succeeded_safely:
                facts.extend(outcome.facts)
                steps.append(
                    RunStep(
                        run_id=run_id,
                        ordinal=ordinal,
                        kind=StepKind.TOOL,
                        capability_name=source_name,
                        capability_version="1",
                    ).complete()
                )
            else:
                reasons.append(outcome.reason_code or "SOURCE_UNAVAILABLE")
                steps.append(
                    RunStep(
                        run_id=run_id,
                        ordinal=ordinal,
                        kind=StepKind.TOOL,
                        capability_name=source_name,
                        capability_version="1",
                    )
                )
        steps.append(
            RunStep(run_id=run_id, ordinal=required_steps, kind=StepKind.COMPOSE).complete()
        )
        state = AgentRunState.PARTIAL if reasons else AgentRunState.COMPLETED
        return MultiSourceResult(
            run_id=run_id,
            state=state,
            facts=tuple(facts),
            steps=tuple(steps),
            degradation_reasons=tuple(reasons),
        )

    async def _invoke(self, handler: SourceHandler, query: str) -> SourceOutcome:
        result = handler(query)
        if inspect.isawaitable(result):
            return await result
        return result
