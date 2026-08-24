"""Multi-source Agent behavior under failures, timeouts, and budgets."""

from __future__ import annotations

import asyncio

import pytest

from atlasmind.agent.budgets import AgentBudgets
from atlasmind.agent.degradation import SourceOutcome
from atlasmind.application.run_agent import MultiSourceAgent, MultiSourceRequest


@pytest.mark.asyncio
@pytest.mark.integration
async def test_multi_source_agent_combines_verified_facts_and_tracks_steps() -> None:
    agent = MultiSourceAgent(
        sources={
            "knowledge": lambda _: SourceOutcome.succeeded(
                "knowledge", ("Runbook requires refund queue review.",)
            ),
            "metrics": lambda _: SourceOutcome.succeeded(
                "metrics", ("Refund failure rate is 7%.",)
            ),
        }
    )

    result = await agent.run(
        MultiSourceRequest(
            query="Analyze refund failures",
            source_names=("knowledge", "metrics"),
            budgets=AgentBudgets(max_steps=6, max_tools=2, timeout_ms=1_000),
        )
    )

    assert result.state.value == "COMPLETED"
    assert result.facts == (
        "Runbook requires refund queue review.",
        "Refund failure rate is 7%.",
    )
    assert [step.kind.value for step in result.steps] == ["PLAN", "TOOL", "TOOL", "COMPOSE"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_source_failure_and_timeout_degrade_without_inventing_facts() -> None:
    async def unavailable(_: str) -> SourceOutcome:
        return SourceOutcome.failed("metrics", "SOURCE_UNAVAILABLE")

    async def slow(_: str) -> SourceOutcome:
        await asyncio.sleep(0.05)
        return SourceOutcome.succeeded("changes", ("must not be returned",))

    agent = MultiSourceAgent(
        sources={
            "knowledge": lambda _: SourceOutcome.succeeded(
                "knowledge",
                ("Verified runbook fact.",),
            ),
            "metrics": unavailable,
            "changes": slow,
        }
    )
    result = await agent.run(
        MultiSourceRequest(
            query="Analyze refund failures",
            source_names=("knowledge", "metrics", "changes"),
            budgets=AgentBudgets(max_steps=8, max_tools=3, timeout_ms=10),
        )
    )

    assert result.state.value == "PARTIAL"
    assert result.facts == ("Verified runbook fact.",)
    assert set(result.degradation_reasons) == {"SOURCE_UNAVAILABLE", "TIMED_OUT"}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_step_or_tool_budget_exhaustion_stops_before_execution() -> None:
    calls = 0

    def source(_: str) -> SourceOutcome:
        nonlocal calls
        calls += 1
        return SourceOutcome.succeeded("knowledge", ("fact",))

    agent = MultiSourceAgent(sources={"knowledge": source, "metrics": source})
    result = await agent.run(
        MultiSourceRequest(
            query="Analyze refund failures",
            source_names=("knowledge", "metrics"),
            budgets=AgentBudgets(max_steps=2, max_tools=1, timeout_ms=1_000),
        )
    )

    assert result.state.value == "FAILED"
    assert result.failure_code == "BUDGET_EXCEEDED"
    assert calls == 0
