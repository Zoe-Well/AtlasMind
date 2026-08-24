"""Serializable Agent state without hidden reasoning traces."""

from __future__ import annotations

from dataclasses import dataclass, replace

from atlasmind.agent.budgets import AgentBudgets
from atlasmind.agent.models import AgentRunState, RunStep
from atlasmind.tools.contracts import CapabilityRequest, EvidenceEnvelope


@dataclass(frozen=True, slots=True)
class AgentState:
    run_id: str
    query: str
    budgets: AgentBudgets
    state: AgentRunState = AgentRunState.QUEUED
    steps: tuple[RunStep, ...] = ()
    requests: tuple[CapabilityRequest, ...] = ()
    evidence: tuple[EvidenceEnvelope, ...] = ()
    degradation_reasons: tuple[str, ...] = ()

    def with_step(self, step: RunStep) -> AgentState:
        if len(self.steps) >= self.budgets.max_steps:
            return replace(self, state=AgentRunState.FAILED)
        return replace(self, steps=(*self.steps, step))
