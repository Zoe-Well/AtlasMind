"""Bounded LangGraph orchestration for Agentic RAG capability execution."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Literal, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command
from pydantic import ValidationError

from atlasmind.agent.decisions import (
    AgentDecision,
    AgentMode,
    AgentObservation,
    AgentToolName,
    AgentToolSpec,
)
from atlasmind.agent.events import AgentEventType
from atlasmind.agent.models import AgentRunState, RunStep, StepKind, StepState
from atlasmind.agent.state import AgentState
from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.domain.common import DomainError, new_id, utc_now
from atlasmind.identity.models import AuthorizationSnapshot
from atlasmind.infrastructure.openai_compatible import GroundedAnswer
from atlasmind.tools.contracts import CapabilityBudget, CapabilityRequest, EvidenceEnvelope
from atlasmind.tools.execution_gateway import ExecutionGateway


class AgentDecisionModel(Protocol):
    async def decide_agent_action(
        self,
        query: str,
        tools: Sequence[AgentToolSpec],
        observations: Sequence[AgentObservation],
        *,
        remaining_steps: int,
        remaining_tools: int,
    ) -> AgentDecision: ...

    async def answer(
        self,
        query: str,
        evidence: dict[str, str],
        *,
        graph_facts: tuple[str, ...] = (),
    ) -> GroundedAnswer: ...


StepWriter = Callable[[RunStep], Awaitable[None]]
EventWriter = Callable[[AgentEventType, dict[str, object]], Awaitable[None]]


async def _discard_event(_event_type: AgentEventType, _data: dict[str, object]) -> None:
    """Backward-compatible sink for non-streaming graph consumers."""


@dataclass(frozen=True, slots=True)
class AgentGraphContext:
    """Trusted run-scoped dependencies never supplied by the model."""

    gateway: ExecutionGateway
    auth_context: AuthContext
    authorization_snapshot: AuthorizationSnapshot
    model: AgentDecisionModel
    tools: tuple[AgentToolSpec, ...]
    write_step: StepWriter
    write_event: EventWriter = _discard_event
    max_iterations: int = 6
    retrieval_mode: AgentMode = "AUTO"


class AgentGraphState(TypedDict, total=False):
    agent: AgentState
    decision: AgentDecision | None
    observations: tuple[AgentObservation, ...]
    used_signatures: tuple[str, ...]
    tool_calls: int
    iterations: int
    answer: GroundedAnswer | None
    terminal_reason: str | None


@dataclass(frozen=True, slots=True)
class AgenticRAGResult:
    state: AgentRunState
    answer: GroundedAnswer
    evidence: tuple[EvidenceEnvelope, ...]
    observations: tuple[AgentObservation, ...]
    steps: tuple[RunStep, ...]
    tool_calls: int
    terminal_reason: str | None = None


def _signature(tool: AgentToolName, arguments: dict[str, object]) -> str:
    canonical = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{tool}:sha256:{sha256(canonical.encode()).hexdigest()}"


def _evidence_text(item: EvidenceEnvelope) -> str:
    return "\n".join(item.facts).strip()


def _public_plan_summary(decision: AgentDecision, *, has_evidence: bool) -> str:
    """Expose the consequence of a decision, never the model's hidden reasoning."""
    if decision.action == "ANSWER":
        return "现有证据已经足够。正在组织回答。" if has_evidence else "没有找到足够证据。"
    labels = {
        "knowledge_search": "正在通过受控检索流程查询企业知识。",
        "query_structured_data": "这个问题涉及业务指标。正在查询结构化数据。",
    }
    return labels.get(decision.tool or "", "正在选择合适的企业知识能力。")


def _public_tool_arguments(arguments: dict[str, object]) -> dict[str, object]:
    """Keep public operational shape without persisting query/evidence text."""
    public: dict[str, object] = {}
    for key, value in arguments.items():
        if key == "query":
            public[key] = "使用当前用户问题"
        elif key in {"limit", "metric", "dataset", "dimensions"}:
            public[key] = value
        elif key == "filters" and isinstance(value, dict):
            public[key] = sorted(map(str, value))
    return public


class LangGraphAgenticRAG:
    """Small, explicit StateGraph with deterministic execution boundaries."""

    def __init__(self) -> None:
        builder = StateGraph(AgentGraphState, context_schema=AgentGraphContext)
        builder.add_node("plan", self._plan)
        builder.add_node("execute", self._execute)
        builder.add_node("compose", self._answer)
        builder.add_node("verify", self._verify)
        builder.add_edge(START, "plan")
        builder.add_edge("execute", "plan")
        builder.add_edge("compose", "verify")
        builder.add_edge("verify", END)
        self._graph = builder.compile(name="atlasmind-agentic-rag")

    async def run(self, state: AgentState, context: AgentGraphContext) -> AgenticRAGResult:
        initial: AgentGraphState = {
            "agent": replace(state, state=AgentRunState.RUNNING),
            "decision": None,
            "observations": (),
            "used_signatures": (),
            "tool_calls": 0,
            "iterations": 0,
            "answer": None,
            "terminal_reason": None,
        }
        try:
            async with asyncio.timeout(state.budgets.timeout_ms / 1_000):
                final = await self._graph.ainvoke(initial, context=context)
        except TimeoutError:
            answer = GroundedAnswer(
                "本次检索已达到时间上限, 当前没有足够证据形成可靠回答。",
                (),
            )
            return AgenticRAGResult(
                state=AgentRunState.TIMED_OUT,
                answer=answer,
                evidence=(),
                observations=(),
                steps=(),
                tool_calls=0,
                terminal_reason="AGENT_TIMEOUT",
            )

        final_agent = final["agent"]
        answer = final.get("answer") or GroundedAnswer(
            "当前授权知识中没有足够证据回答该问题。",
            (),
        )
        terminal_reason = final.get("terminal_reason")
        completed_state = AgentRunState.COMPLETED
        if terminal_reason in {
            "STEP_BUDGET_EXCEEDED",
            "TOOL_BUDGET_EXCEEDED",
            "ANSWER_GENERATION_FAILED",
        }:
            completed_state = (
                AgentRunState.PARTIAL if final_agent.evidence else AgentRunState.FAILED
            )
        elif terminal_reason == "CITATION_VALIDATION_FAILED":
            completed_state = AgentRunState.FAILED
        return AgenticRAGResult(
            state=completed_state,
            answer=answer,
            evidence=final_agent.evidence,
            observations=final.get("observations", ()),
            steps=final_agent.steps,
            tool_calls=final.get("tool_calls", 0),
            terminal_reason=terminal_reason,
        )

    async def _plan(
        self,
        state: AgentGraphState,
        runtime: Runtime[AgentGraphContext],
    ) -> Command[Literal["execute", "compose"]]:
        agent = state["agent"]
        iterations = state.get("iterations", 0)
        tool_calls = state.get("tool_calls", 0)
        if (
            iterations >= runtime.context.max_iterations
            or len(agent.steps) >= agent.budgets.max_steps
        ):
            return Command(
                update={
                    "decision": AgentDecision(
                        action="ANSWER",
                        reason_code="STEP_BUDGET_EXCEEDED",
                    ),
                    "terminal_reason": "STEP_BUDGET_EXCEEDED",
                },
                goto="compose",
            )
        if tool_calls >= agent.budgets.max_tools:
            return Command(
                update={
                    "decision": AgentDecision(
                        action="ANSWER",
                        reason_code="TOOL_BUDGET_EXCEEDED",
                    ),
                    "terminal_reason": "TOOL_BUDGET_EXCEEDED",
                },
                goto="compose",
            )

        available = {item.name for item in runtime.context.tools}
        step_id = new_id()
        await runtime.context.write_event(
            AgentEventType.STEP_STARTED,
            {
                "stepName": "plan",
                "stepId": step_id,
                "stepKind": StepKind.PLAN.value,
            },
        )
        try:
            decision = await runtime.context.model.decide_agent_action(
                agent.query,
                runtime.context.tools,
                state.get("observations", ()),
                remaining_steps=runtime.context.max_iterations - iterations,
                remaining_tools=agent.budgets.max_tools - tool_calls,
            )
        except ValueError, ValidationError:
            decision = self._safe_fallback_decision(
                state,
                available,
                "MODEL_DECISION_INVALID",
            )
        if decision.tool is not None and decision.tool not in available:
            decision = self._safe_fallback_decision(state, available, "CAPABILITY_NOT_ALLOWED")

        if decision.action == "ANSWER" and not agent.evidence:
            decision = self._safe_fallback_decision(state, available, "EVIDENCE_REQUIRED")

        if decision.tool is not None:
            signature = _signature(decision.tool, decision.arguments)
            if signature in state.get("used_signatures", ()):
                decision = self._safe_fallback_decision(state, available, "DUPLICATE_TOOL_REQUEST")

        step = RunStep(
            run_id=agent.run_id,
            ordinal=len(agent.steps) + 1,
            kind=StepKind.PLAN,
            input_digest=f"sha256:{sha256(agent.query.encode()).hexdigest()}",
            id=step_id,
        ).complete(result_ref=f"decision:{decision.action}:{decision.reason_code}")
        await runtime.context.write_step(step)
        await runtime.context.write_event(
            AgentEventType.ACTIVITY_SNAPSHOT,
            {
                "messageId": f"plan-{iterations + 1}",
                "activityType": "public_reasoning",
                "content": {
                    "summary": _public_plan_summary(decision, has_evidence=bool(agent.evidence)),
                },
                "replace": True,
            },
        )
        await runtime.context.write_event(
            AgentEventType.STEP_FINISHED,
            {
                "stepName": "plan",
                "stepId": step.id,
                "stepKind": StepKind.PLAN.value,
                "state": StepState.SUCCEEDED.value,
                "decision": decision.action,
            },
        )
        update: AgentGraphState = {
            "agent": agent.with_step(step),
            "decision": decision,
            "iterations": iterations + 1,
        }
        return Command(
            update=update,
            goto="execute" if decision.action == "CALL_TOOL" else "compose",
        )

    @staticmethod
    def _safe_fallback_decision(
        state: AgentGraphState,
        available: set[AgentToolName],
        reason_code: str,
    ) -> AgentDecision:
        agent = state["agent"]
        fallback = AgentDecision(
            action="CALL_TOOL",
            tool="knowledge_search",
            arguments={"query": agent.query},
            reason_code=reason_code,
        )
        if (
            "knowledge_search" in available
            and not agent.evidence
            and _signature("knowledge_search", fallback.arguments)
            not in state.get("used_signatures", ())
        ):
            return fallback
        return AgentDecision(action="ANSWER", reason_code=reason_code)

    async def _execute(
        self,
        state: AgentGraphState,
        runtime: Runtime[AgentGraphContext],
    ) -> AgentGraphState:
        agent = state["agent"]
        decision = state.get("decision")
        if decision is None or decision.tool is None:
            raise ValueError("tool execution requires a decision")
        signature = _signature(decision.tool, decision.arguments)
        step = RunStep(
            run_id=agent.run_id,
            ordinal=len(agent.steps) + 1,
            kind=(StepKind.RETRIEVAL if decision.tool == "knowledge_search" else StepKind.TOOL),
            capability_name=decision.tool,
            capability_version="1",
            input_digest=signature.split(":", 1)[1],
        )
        running_step = replace(step, state=StepState.RUNNING, started_at=utc_now())
        await runtime.context.write_step(running_step)
        await runtime.context.write_event(
            AgentEventType.STEP_STARTED,
            {
                "stepName": decision.tool,
                "stepId": step.id,
                "stepKind": step.kind.value,
            },
        )
        await runtime.context.write_event(
            AgentEventType.TOOL_CALL_START,
            {"toolCallId": step.id, "toolCallName": decision.tool},
        )
        await runtime.context.write_event(
            AgentEventType.TOOL_CALL_ARGS,
            {
                "toolCallId": step.id,
                "delta": json.dumps(_public_tool_arguments(decision.arguments), ensure_ascii=False),
            },
        )
        await runtime.context.write_event(
            AgentEventType.TOOL_CALL_END,
            {"toolCallId": step.id},
        )
        try:
            request = CapabilityRequest(
                request_id=new_id(),
                run_id=agent.run_id,
                step_id=step.id,
                capability_name=decision.tool,
                capability_version="1",
                auth_context_ref=f"authz:{runtime.context.auth_context.authz_revision}",
                input={
                    **decision.arguments,
                    **(
                        {"mode": runtime.context.retrieval_mode}
                        if decision.tool == "knowledge_search"
                        else {}
                    ),
                },
                budget=CapabilityBudget(
                    timeout_ms=min(8_000, agent.budgets.timeout_ms),
                    max_items=40,
                    max_result_bytes=min(500_000, agent.budgets.max_result_bytes),
                ),
            )
            async def publish_public_activity(
                activity_id: str,
                activity_type: str,
                content: dict[str, object],
            ) -> None:
                if activity_type != "atlasmind.retrieval":
                    return
                allowed = {
                    "stage",
                    "strategyId",
                    "status",
                    "summary",
                    "metrics",
                    "selectedStrategies",
                    "degradationCode",
                }
                await runtime.context.write_event(
                    AgentEventType.ACTIVITY_SNAPSHOT,
                    {
                        "messageId": activity_id,
                        "activityType": activity_type,
                        "parentMessageId": step.id,
                        "content": {
                            key: value for key, value in content.items() if key in allowed
                        },
                    },
                )

            result = await runtime.context.gateway.execute(
                request,
                runtime.context.auth_context,
                runtime.context.authorization_snapshot,
                public_activity_writer=publish_public_activity,
            )
        except (DomainError, ValidationError) as exc:
            reason_code = (
                str(exc.details.get("reason") or exc.code)
                if isinstance(exc, DomainError)
                else "INVALID_TOOL_ARGUMENTS"
            )
            completed = replace(
                running_step,
                state=StepState.FAILED,
                result_ref=f"capability:{reason_code}",
                finished_at=utc_now(),
            )
            await runtime.context.write_step(completed)
            await runtime.context.write_event(
                AgentEventType.TOOL_CALL_RESULT,
                {
                    "messageId": new_id(),
                    "toolCallId": step.id,
                    "content": json.dumps(
                        {
                            "status": "FAILED",
                            "evidenceCount": 0,
                            "reasonCode": reason_code,
                            "retryable": False,
                        },
                        ensure_ascii=False,
                    ),
                    "role": "tool",
                },
            )
            await runtime.context.write_event(
                AgentEventType.STEP_FINISHED,
                {
                    "stepName": decision.tool,
                    "stepId": step.id,
                    "stepKind": step.kind.value,
                    "state": StepState.FAILED.value,
                    "reasonCode": reason_code,
                },
            )
            observation = AgentObservation(
                tool=decision.tool,
                status="FAILED",
                evidence_count=0,
                reason_code=reason_code,
            )
            update: AgentGraphState = {
                "agent": agent.with_step(completed),
                "observations": (*state.get("observations", ()), observation),
                "used_signatures": (*state.get("used_signatures", ()), signature),
                "tool_calls": state.get("tool_calls", 0) + 1,
                "decision": None,
            }
            return update

        evidence_by_id = {item.evidence_id: item for item in agent.evidence}
        evidence_order = [item.evidence_id for item in agent.evidence]
        for item in result.evidence:
            prior = evidence_by_id.get(item.evidence_id)
            if prior is None:
                evidence_by_id[item.evidence_id] = item
                evidence_order.append(item.evidence_id)
                continue
            graph_paths = [
                *prior.metadata.get("graphPaths", ()),
                *item.metadata.get("graphPaths", ()),
            ]
            merged_metadata = {**prior.metadata, **item.metadata}
            if graph_paths:
                merged_metadata["graphPaths"] = list(
                    {
                        json.dumps(path, ensure_ascii=False, sort_keys=True, default=str): path
                        for path in graph_paths
                    }.values()
                )[:20]
            merged_facts = tuple(dict.fromkeys((*prior.facts, *item.facts)))
            evidence_by_id[item.evidence_id] = prior.model_copy(
                update={"facts": merged_facts, "metadata": merged_metadata}
            )
        evidence = tuple(evidence_by_id[evidence_id] for evidence_id in evidence_order)
        summaries = tuple(
            summary[:800]
            for item in result.evidence[:8]
            for summary in item.facts[:2]
            if summary.strip()
        )
        observation = AgentObservation(
            tool=decision.tool,
            status=result.status,
            evidence_count=len(result.evidence),
            evidence_summaries=summaries,
            reason_code=result.reason_code,
            warnings=result.warnings,
        )
        completed = running_step.complete(result_ref=f"evidence:{len(result.evidence)}")
        await runtime.context.write_step(completed)
        await runtime.context.write_event(
            AgentEventType.TOOL_CALL_RESULT,
            {
                "messageId": new_id(),
                "toolCallId": step.id,
                "content": json.dumps(
                        {
                            "status": result.status,
                            "evidenceCount": len(result.evidence),
                            "reasonCode": result.reason_code,
                            "warningCount": len(result.warnings),
                        },
                    ensure_ascii=False,
                ),
                "role": "tool",
            },
        )
        await runtime.context.write_event(
            AgentEventType.STEP_FINISHED,
            {
                "stepName": decision.tool,
                "stepId": step.id,
                "stepKind": step.kind.value,
                "state": completed.state.value,
                "evidenceCount": len(result.evidence),
            },
        )
        update = {
            "agent": replace(agent.with_step(completed), evidence=evidence),
            "observations": (*state.get("observations", ()), observation),
            "used_signatures": (*state.get("used_signatures", ()), signature),
            "tool_calls": state.get("tool_calls", 0) + 1,
            "decision": None,
        }
        return update

    async def _answer(
        self,
        state: AgentGraphState,
        runtime: Runtime[AgentGraphContext],
    ) -> AgentGraphState:
        agent = state["agent"]
        step_id = new_id()
        await runtime.context.write_event(
            AgentEventType.STEP_STARTED,
            {
                "stepName": "compose",
                "stepId": step_id,
                "stepKind": StepKind.COMPOSE.value,
            },
        )
        evidence = {
            item.evidence_id: _evidence_text(item)
            for item in agent.evidence
            if item.validity == "VALID" and _evidence_text(item)
        }
        if evidence:
            message_id = new_id()
            await runtime.context.write_event(
                AgentEventType.TEXT_MESSAGE_START,
                {"messageId": message_id, "role": "assistant"},
            )
            try:
                stream_answer = getattr(runtime.context.model, "stream_answer", None)
                if stream_answer is None:
                    answer = await runtime.context.model.answer(agent.query, evidence)
                    await runtime.context.write_event(
                        AgentEventType.TEXT_MESSAGE_CONTENT,
                        {"messageId": message_id, "delta": answer.answer},
                    )
                else:

                    async def emit_text(delta: str) -> None:
                        if delta:
                            await runtime.context.write_event(
                                AgentEventType.TEXT_MESSAGE_CONTENT,
                                {"messageId": message_id, "delta": delta},
                            )

                    answer = await stream_answer(agent.query, evidence, emit_text)
            except ValueError:
                answer = GroundedAnswer(
                    "回答生成结果未通过安全校验, 请稍后重试。",
                    (),
                )
                terminal_reason = "ANSWER_GENERATION_FAILED"
            await runtime.context.write_event(
                AgentEventType.TEXT_MESSAGE_END,
                {"messageId": message_id},
            )
        else:
            answer = GroundedAnswer("当前授权知识中没有足够证据回答该问题。", ())
        step = RunStep(
            run_id=agent.run_id,
            ordinal=len(agent.steps) + 1,
            kind=StepKind.COMPOSE,
            id=step_id,
        ).complete(result_ref="answer:composed")
        await runtime.context.write_step(step)
        await runtime.context.write_event(
            AgentEventType.STEP_FINISHED,
            {
                "stepName": "compose",
                "stepId": step.id,
                "stepKind": StepKind.COMPOSE.value,
                "state": step.state.value,
            },
        )
        update: AgentGraphState = {"agent": agent.with_step(step), "answer": answer}
        if evidence and "terminal_reason" in locals():
            update["terminal_reason"] = terminal_reason
        return update

    async def _verify(
        self,
        state: AgentGraphState,
        runtime: Runtime[AgentGraphContext],
    ) -> AgentGraphState:
        agent = state["agent"]
        step_id = new_id()
        await runtime.context.write_event(
            AgentEventType.STEP_STARTED,
            {
                "stepName": "verify",
                "stepId": step_id,
                "stepKind": StepKind.VERIFY.value,
            },
        )
        answer = state.get("answer")
        if answer is None:
            raise ValueError("answer verification requires an answer")
        allowed = {item.evidence_id for item in agent.evidence if item.validity == "VALID"}
        terminal_reason: str | None
        if not set(answer.citation_ids).issubset(allowed):
            answer = GroundedAnswer("回答引用未通过来源校验, 请稍后重试。", ())
            terminal_reason = "CITATION_VALIDATION_FAILED"
        else:
            terminal_reason = state.get("terminal_reason")
        step = RunStep(
            run_id=agent.run_id,
            ordinal=len(agent.steps) + 1,
            kind=StepKind.VERIFY,
            id=step_id,
        )
        if terminal_reason == "CITATION_VALIDATION_FAILED":
            step = replace(
                step,
                state=StepState.FAILED,
                result_ref="citations:invalid",
                started_at=utc_now(),
                finished_at=utc_now(),
            )
        else:
            step = step.complete(result_ref=f"citations:{len(answer.citation_ids)}")
        await runtime.context.write_step(step)
        await runtime.context.write_event(
            AgentEventType.STEP_FINISHED,
            {
                "stepName": "verify",
                "stepId": step.id,
                "stepKind": StepKind.VERIFY.value,
                "state": step.state.value,
                "citationCount": len(answer.citation_ids),
            },
        )
        update: AgentGraphState = {
            "agent": agent.with_step(step),
            "answer": answer,
            "terminal_reason": terminal_reason,
        }
        return update
