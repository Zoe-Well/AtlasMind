"""Bounded LangGraph Agentic RAG routing and safety behavior."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from atlasmind.agent.budgets import AgentBudgets
from atlasmind.agent.decisions import AgentDecision, AgentObservation, AgentToolSpec
from atlasmind.agent.events import AgentEventType
from atlasmind.agent.langgraph_rag import AgentGraphContext, AgenticRAGResult, LangGraphAgenticRAG
from atlasmind.agent.models import AgentRunState, RunStep, StepKind, StepState
from atlasmind.agent.state import AgentState
from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.identity.models import Action, AuthorizationSnapshot
from atlasmind.infrastructure.openai_compatible import GroundedAnswer
from atlasmind.tools.contracts import (
    CapabilityDescriptor,
    CapabilityKind,
    CapabilityRequest,
    CapabilityResult,
    EvidenceEnvelope,
    EvidenceSource,
    RiskLevel,
)
from atlasmind.tools.execution_gateway import (
    CapabilityExecutionContext,
    CapabilityRegistry,
    ExecutionGateway,
)

SCOPE_ID = "00000000-0000-4000-8000-000000000010"
PRINCIPAL_ID = "00000000-0000-4000-8000-000000000001"
Handler = Callable[
    [CapabilityRequest, CapabilityExecutionContext],
    Awaitable[CapabilityResult],
]


class ScriptedModel:
    def __init__(
        self,
        decisions: Sequence[AgentDecision],
        *,
        invalid_citation: bool = False,
    ) -> None:
        self.decisions = list(decisions)
        self.invalid_citation = invalid_citation

    async def decide_agent_action(
        self,
        query: str,
        tools: Sequence[AgentToolSpec],
        observations: Sequence[AgentObservation],
        *,
        remaining_steps: int,
        remaining_tools: int,
    ) -> AgentDecision:
        del query, tools, observations, remaining_steps, remaining_tools
        if self.decisions:
            return self.decisions.pop(0)
        return AgentDecision(action="ANSWER", reason_code="SCRIPT_COMPLETE")

    async def answer(
        self,
        query: str,
        evidence: dict[str, str],
        *,
        graph_facts: tuple[str, ...] = (),
    ) -> GroundedAnswer:
        del query, graph_facts
        citation = "outside-evidence" if self.invalid_citation else next(iter(evidence))
        return GroundedAnswer("基于授权证据的回答。", (citation,))


def auth_context() -> AuthContext:
    now = datetime.now(UTC)
    return AuthContext(
        principal_id=PRINCIPAL_ID,
        role_codes=frozenset({"local-super-admin"}),
        scope_ids=frozenset({SCOPE_ID}),
        allowed_actions=frozenset(Action),
        authz_revision=1,
        policy_revision=1,
        correlation_id=str(uuid4()),
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )


def tool_spec(name: str) -> AgentToolSpec:
    return AgentToolSpec.model_validate(
        {
            "name": name,
            "description": f"Test capability {name}",
            "input_schema": {"type": "object"},
        }
    )


def evidence(identifier: str) -> EvidenceEnvelope:
    return EvidenceEnvelope(
        evidence_id=identifier,
        source=EvidenceSource(
            type="DOCUMENT",
            canonical_id=identifier,
            version=str(uuid4()),
            locator="paragraph=1",
        ),
        scope_ids=frozenset({SCOPE_ID}),
        content_ref=f"knowledge-chunk:{identifier}",
        content_digest="sha256:test",
        facts=("授权知识证据",),
        authz_revision=1,
        verified_at=datetime.now(UTC),
    )


def successful(identifier: str) -> CapabilityResult:
    return CapabilityResult(status="SUCCEEDED", evidence=(evidence(identifier),))


async def run_agent(
    model: ScriptedModel,
    handlers: dict[str, Handler],
    *,
    budgets: AgentBudgets | None = None,
    query: str = "测试问题",
    events: list[tuple[AgentEventType, dict[str, object]]] | None = None,
) -> tuple[AgenticRAGResult, list[RunStep]]:
    registry = CapabilityRegistry()
    for name, handler in handlers.items():
        registry.register(
            CapabilityDescriptor(
                name=name,
                version="1",
                kind=(
                    CapabilityKind.STRUCTURED_QUERY
                    if name == "query_structured_data"
                    else CapabilityKind.RETRIEVAL
                ),
                required_actions=frozenset({Action.READ}),
                risk_level=RiskLevel.LOW,
                timeout_ms=8_000,
                max_result_bytes=500_000,
                max_items=40,
            ),
            handler,
        )

    async def audit(status: str, request: CapabilityRequest) -> None:
        del status, request

    written: list[RunStep] = []

    async def write_step(step: RunStep) -> None:
        written.append(step)

    async def write_event(
        event_type: AgentEventType,
        data: dict[str, object],
    ) -> None:
        if events is not None:
            events.append((event_type, data))

    context = auth_context()
    result = await LangGraphAgenticRAG().run(
        AgentState(
            run_id=str(uuid4()),
            query=query,
            budgets=budgets or AgentBudgets(max_steps=12, max_tools=4, timeout_ms=10_000),
        ),
        AgentGraphContext(
            gateway=ExecutionGateway(registry, audit),
            auth_context=context,
            authorization_snapshot=AuthorizationSnapshot(1, context.scope_ids),
            model=model,
            tools=tuple(tool_spec(name) for name in handlers),
            write_step=write_step,
            write_event=write_event,
        ),
    )
    return result, written


@pytest.mark.asyncio
async def test_public_events_do_not_expose_query_scope_or_evidence_text() -> None:
    captured: list[tuple[AgentEventType, dict[str, object]]] = []
    secret_query = "SECRET-QUESTION-7429"

    async def knowledge(
        _: CapabilityRequest,
        __: CapabilityExecutionContext,
    ) -> CapabilityResult:
        return successful(str(uuid4()))

    await run_agent(
        ScriptedModel(
            [
                AgentDecision(
                    action="CALL_TOOL",
                    tool="knowledge_search",
                    arguments={"query": secret_query},
                    reason_code="DOCUMENT_QUESTION",
                ),
                AgentDecision(action="ANSWER", reason_code="EVIDENCE_SUFFICIENT"),
            ]
        ),
        {"knowledge_search": knowledge},
        query=secret_query,
        events=captured,
    )

    serialized = json.dumps(captured, ensure_ascii=False)
    assert secret_query not in serialized
    assert SCOPE_ID not in serialized
    assert "授权知识证据" not in serialized
    assert "使用当前用户问题" in serialized


@pytest.mark.asyncio
async def test_capability_public_activity_is_nested_and_allowlisted() -> None:
    captured: list[tuple[AgentEventType, dict[str, object]]] = []

    async def knowledge(
        _: CapabilityRequest,
        context: CapabilityExecutionContext,
    ) -> CapabilityResult:
        await context.publish_public_activity(
            "retrieval-vector",
            "atlasmind.retrieval",
            {
                "stage": "RETRIEVAL",
                "strategyId": "vector",
                "status": "SUCCEEDED",
                "summary": "向量检索已完成。",
                "metrics": {"candidateCount": 8},
                "rawQuery": "SECRET-QUERY",
            },
        )
        return successful(str(uuid4()))

    await run_agent(
        ScriptedModel(
            [
                AgentDecision(
                    action="CALL_TOOL",
                    tool="knowledge_search",
                    arguments={"query": "测试问题"},
                    reason_code="DOCUMENT_QUESTION",
                ),
                AgentDecision(action="ANSWER", reason_code="EVIDENCE_SUFFICIENT"),
            ]
        ),
        {"knowledge_search": knowledge},
        events=captured,
    )

    retrieval_events = [
        data
        for event_type, data in captured
        if event_type is AgentEventType.ACTIVITY_SNAPSHOT
        and data.get("activityType") == "atlasmind.retrieval"
    ]
    assert len(retrieval_events) == 1
    assert retrieval_events[0]["messageId"] == "retrieval-vector"
    assert retrieval_events[0]["parentMessageId"]
    assert "rawQuery" not in retrieval_events[0]["content"]


@pytest.mark.asyncio
async def test_simple_question_uses_only_knowledge_search() -> None:
    calls: list[str] = []

    async def knowledge(_: CapabilityRequest, __: CapabilityExecutionContext) -> CapabilityResult:
        calls.append("knowledge_search")
        return successful(str(uuid4()))

    result, _ = await run_agent(
        ScriptedModel(
            [
                AgentDecision(
                    action="CALL_TOOL",
                    tool="knowledge_search",
                    arguments={"query": "测试问题"},
                    reason_code="DOCUMENT_QUESTION",
                ),
                AgentDecision(action="ANSWER", reason_code="EVIDENCE_SUFFICIENT"),
            ]
        ),
        {"knowledge_search": knowledge},
    )

    assert result.state is AgentRunState.COMPLETED
    assert calls == ["knowledge_search"]
    assert [step.kind for step in result.steps][-2:] == [StepKind.COMPOSE, StepKind.VERIFY]


@pytest.mark.asyncio
async def test_model_cannot_call_graph_as_separate_agent_tool() -> None:
    calls: list[str] = []

    async def empty_knowledge(
        _: CapabilityRequest,
        __: CapabilityExecutionContext,
    ) -> CapabilityResult:
        calls.append("knowledge_search")
        return CapabilityResult(status="EMPTY", reason_code="NO_AUTHORIZED_EVIDENCE")

    result, _ = await run_agent(
        ScriptedModel(
            [
                AgentDecision(
                    action="CALL_TOOL",
                    tool="knowledge_search",
                    arguments={"query": "测试问题"},
                    reason_code="TRY_DOCUMENTS",
                ),
                AgentDecision(
                    action="CALL_TOOL",
                    tool="search_graph",
                    arguments={"query": "测试问题"},
                    reason_code="NEED_RELATIONSHIP",
                ),
                AgentDecision(action="ANSWER", reason_code="GRAPH_EVIDENCE_SUFFICIENT"),
            ]
        ),
        {"knowledge_search": empty_knowledge},
    )

    assert calls == ["knowledge_search"]
    assert [item.tool for item in result.observations] == ["knowledge_search"]


@pytest.mark.asyncio
async def test_knowledge_search_returns_fused_graph_evidence() -> None:
    identifier = str(uuid4())
    document_evidence = evidence(identifier)
    graph_path = {
        "entities": ["AtlasMind", "PostgreSQL"],
        "relations": ["USES"],
        "directions": [True],
        "sources": [{"chunkId": identifier, "locator": "paragraph=1"}],
    }

    async def knowledge(_: CapabilityRequest, __: CapabilityExecutionContext) -> CapabilityResult:
        graph_evidence = document_evidence.model_copy(
            update={
                "facts": (*document_evidence.facts, "AtlasMind -[USES]-> PostgreSQL"),
                "metadata": {"graphPaths": [graph_path]},
            }
        )
        return CapabilityResult(status="SUCCEEDED", evidence=(graph_evidence,))

    result, _ = await run_agent(
        ScriptedModel(
            [
                AgentDecision(
                    action="CALL_TOOL",
                    tool="knowledge_search",
                    arguments={"query": "测试问题"},
                    reason_code="DOCUMENT_FIRST",
                ),
                AgentDecision(action="ANSWER", reason_code="ENOUGH"),
            ]
        ),
        {"knowledge_search": knowledge},
    )

    assert len(result.evidence) == 1
    assert result.evidence[0].facts == (
        "授权知识证据",
        "AtlasMind -[USES]-> PostgreSQL",
    )
    assert result.evidence[0].metadata["graphPaths"] == [graph_path]


@pytest.mark.asyncio
async def test_duplicate_empty_tool_call_terminates_without_reexecution() -> None:
    calls = 0

    async def empty(_: CapabilityRequest, __: CapabilityExecutionContext) -> CapabilityResult:
        nonlocal calls
        calls += 1
        return CapabilityResult(status="EMPTY")

    repeated = AgentDecision(
        action="CALL_TOOL",
        tool="knowledge_search",
        arguments={"query": "测试问题"},
        reason_code="RETRY_SAME_CALL",
    )
    result, _ = await run_agent(
        ScriptedModel([repeated, repeated]),
        {"knowledge_search": empty},
    )

    assert calls == 1
    assert result.tool_calls == 1
    assert not result.answer.citation_ids


@pytest.mark.asyncio
async def test_model_cannot_inject_authorization_fields_into_tool_input() -> None:
    handler_called = False

    async def structured(_: CapabilityRequest, __: CapabilityExecutionContext) -> CapabilityResult:
        nonlocal handler_called
        handler_called = True
        return successful(str(uuid4()))

    result, written = await run_agent(
        ScriptedModel(
            [
                AgentDecision(
                    action="CALL_TOOL",
                    tool="query_structured_data",
                    arguments={
                        "dataset": "orders",
                        "metric": "count",
                        "scope_ids": ["forged-scope"],
                    },
                    reason_code="MALICIOUS_ARGUMENT",
                ),
                AgentDecision(action="ANSWER", reason_code="STOP"),
            ]
        ),
        {"query_structured_data": structured},
    )

    assert handler_called is False
    assert result.observations[0].reason_code == "INVALID_TOOL_ARGUMENTS"
    assert any(step.state is StepState.FAILED for step in written)


@pytest.mark.asyncio
async def test_citation_outside_evidence_fails_closed() -> None:
    async def knowledge(_: CapabilityRequest, __: CapabilityExecutionContext) -> CapabilityResult:
        return successful(str(uuid4()))

    result, _ = await run_agent(
        ScriptedModel(
            [
                AgentDecision(
                    action="CALL_TOOL",
                    tool="knowledge_search",
                    arguments={"query": "测试问题"},
                    reason_code="SEARCH",
                ),
                AgentDecision(action="ANSWER", reason_code="ENOUGH"),
            ],
            invalid_citation=True,
        ),
        {"knowledge_search": knowledge},
    )

    assert result.state is AgentRunState.FAILED
    assert result.terminal_reason == "CITATION_VALIDATION_FAILED"
    assert not result.answer.citation_ids
    assert result.steps[-1].state is StepState.FAILED
