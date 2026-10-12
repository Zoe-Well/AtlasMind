"""Persistence boundary for LangGraph steps, tool invocations, and evidence."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from hashlib import sha256
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from atlasmind.agent.langgraph_rag import AgenticRAGResult
from atlasmind.agent.models import AgentRunState, RunStep
from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.domain.common import utc_now
from atlasmind.tools.contracts import CapabilityRequest

AuditAppender = Callable[..., Awaitable[None]]


class AgentRunPersistence:
    """Write-only adapter used by Agent nodes and the execution gateway."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        append_audit: AuditAppender,
    ) -> None:
        self._sessions = sessions
        self._append_audit = append_audit

    async def write_step(self, step: RunStep) -> None:
        async with self._sessions() as session, session.begin():
            await session.execute(
                text(
                    """
                    INSERT INTO run_steps
                        (id, run_id, ordinal, kind, state, capability_name,
                         capability_version, input_digest, result_ref, started_at, finished_at)
                    VALUES
                        (:id, :run_id, :ordinal, :kind, :state, :capability_name,
                         :capability_version, :input_digest, :result_ref, :started_at, :finished_at)
                    ON CONFLICT (id) DO UPDATE
                    SET state = EXCLUDED.state,
                        result_ref = EXCLUDED.result_ref,
                        started_at = COALESCE(run_steps.started_at, EXCLUDED.started_at),
                        finished_at = EXCLUDED.finished_at
                    """
                ),
                {
                    "id": UUID(step.id),
                    "run_id": UUID(step.run_id),
                    "ordinal": step.ordinal,
                    "kind": step.kind.value,
                    "state": step.state.value,
                    "capability_name": step.capability_name,
                    "capability_version": step.capability_version,
                    "input_digest": step.input_digest,
                    "result_ref": step.result_ref,
                    "started_at": step.started_at,
                    "finished_at": step.finished_at,
                },
            )

    async def audit_capability(self, status: str, request: CapabilityRequest) -> None:
        async with self._sessions() as session, session.begin():
            run = (
                await session.execute(
                    text(
                        """
                        SELECT principal_id, correlation_id
                        FROM agent_runs
                        WHERE id = :id
                        """
                    ),
                    {"id": UUID(request.run_id)},
                )
            ).mappings().one()
            normalized = json.dumps(
                request.input,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            digest = f"sha256:{sha256(normalized.encode()).hexdigest()}"
            invocation_state = "SUCCEEDED" if status in {"SUCCEEDED", "EMPTY"} else "FAILED"
            await session.execute(
                text(
                    """
                    INSERT INTO tool_invocations
                        (id, run_step_id, capability_name, capability_version, principal_id,
                         authz_revision, normalized_input_digest, state, result_ref, error_code,
                         idempotency_key)
                    VALUES
                        (:id, :step_id, :name, :version, :principal, :revision,
                         :digest, :state, :result_ref, :error_code, :idempotency_key)
                    ON CONFLICT (id) DO UPDATE
                    SET state = EXCLUDED.state,
                        result_ref = EXCLUDED.result_ref,
                        error_code = EXCLUDED.error_code
                    """
                ),
                {
                    "id": UUID(request.request_id),
                    "step_id": UUID(request.step_id),
                    "name": request.capability_name,
                    "version": request.capability_version,
                    "principal": run["principal_id"],
                    "revision": self._authz_revision(request.auth_context_ref),
                    "digest": digest,
                    "state": invocation_state,
                    "result_ref": f"capability:{status}",
                    "error_code": None if invocation_state == "SUCCEEDED" else status,
                    "idempotency_key": request.idempotency_key,
                },
            )
            await self._append_audit(
                session,
                event_type="AGENT_CAPABILITY_EXECUTED",
                actor_id=str(run["principal_id"]),
                correlation_id=str(run["correlation_id"]),
                resource_type="AGENT_RUN",
                resource_id=request.run_id,
                decision=invocation_state,
                reason_code=status,
                payload={"capability": request.capability_name, "inputDigest": digest},
            )

    async def complete(
        self,
        run_id: UUID,
        result: AgenticRAGResult,
        *,
        context: AuthContext,
        trace_id: str | None,
        created_at: Any,
    ) -> dict[str, object]:
        by_id = {item.evidence_id: item for item in result.evidence}
        graph_paths = self._graph_paths(result)
        citations: list[dict[str, object]] = []
        async with self._sessions() as session, session.begin():
            current_state = (
                await session.execute(
                    text("SELECT state FROM agent_runs WHERE id = :id FOR UPDATE"),
                    {"id": run_id},
                )
            ).scalar_one()
            if current_state != AgentRunState.RUNNING.value:
                # Cancellation or shutdown won the row lock. Rolling the
                # transaction back prevents late answer writes reviving the run.
                raise asyncio.CancelledError

            for referenced_id in result.answer.citation_ids:
                envelope = by_id[referenced_id]
                source_title = envelope.source.canonical_id
                if envelope.source.type == "DOCUMENT":
                    title = (
                        await session.execute(
                            text(
                                """
                                SELECT document.title
                                FROM knowledge_chunks chunk
                                JOIN document_versions version
                                  ON version.id = chunk.document_version_id
                                JOIN knowledge_documents document
                                  ON document.id = version.document_id
                                WHERE chunk.id = :id
                                """
                            ),
                            {"id": UUID(envelope.source.canonical_id)},
                        )
                    ).scalar_one_or_none()
                    if title is not None:
                        source_title = str(title)

                evidence_id = uuid4()
                citation_id = uuid4()
                excerpt = "\n".join(envelope.facts)[:500]
                source_metadata = {
                    "canonicalId": envelope.source.canonical_id,
                    "version": envelope.source.version,
                    **envelope.metadata,
                }
                await session.execute(
                    text(
                        """
                        INSERT INTO evidence_records
                            (id, run_id, source_type, source_id, source_version, locator,
                             scope_ids, content_digest, validity, authz_revision, verified_at,
                             source_title, source_excerpt, source_metadata)
                        VALUES
                            (:id, :run_id, :source_type, :source_id, :source_version, :locator,
                             :scopes, :digest, 'VALID', :revision, :verified_at,
                             :source_title, :source_excerpt, CAST(:source_metadata AS jsonb))
                        """
                    ),
                    {
                        "id": evidence_id,
                        "run_id": run_id,
                        "source_type": envelope.source.type,
                        "source_id": self._source_uuid(
                            envelope.source.type,
                            envelope.source.canonical_id,
                        ),
                        "source_version": self._source_uuid(
                            envelope.source.type,
                            envelope.source.version,
                        ),
                        "locator": envelope.source.locator,
                        "scopes": [UUID(value) for value in sorted(envelope.scope_ids)],
                        "digest": envelope.content_digest,
                        "revision": envelope.authz_revision,
                        "verified_at": envelope.verified_at,
                        "source_title": source_title,
                        "source_excerpt": excerpt,
                        "source_metadata": json.dumps(source_metadata),
                    },
                )
                await session.execute(
                    text(
                        """
                        INSERT INTO citations (id, run_id, evidence_id, claim, support)
                        VALUES (:id, :run_id, :evidence_id, :claim, 'SUPPORTED')
                        """
                    ),
                    {
                        "id": citation_id,
                        "run_id": run_id,
                        "evidence_id": evidence_id,
                        "claim": result.answer.answer,
                    },
                )
                citations.append(
                    {
                        "id": str(citation_id),
                        "claimLocator": result.answer.answer,
                        "supportStatus": "SUPPORTED",
                        "source": {
                            "type": envelope.source.type,
                            "id": envelope.source.canonical_id,
                            "version": envelope.source.version,
                            "locator": envelope.source.locator,
                            "title": source_title,
                            "excerpt": excerpt,
                        },
                    }
                )

            used_tools = tuple(dict.fromkeys(item.tool for item in result.observations))
            task_type = self._task_type(used_tools, has_graph_paths=bool(graph_paths))
            evidence_status = "SUFFICIENT" if citations else "INSUFFICIENT"
            now = utc_now()
            usage = {
                "agentFramework": "langgraph",
                "toolCalls": result.tool_calls,
                "tools": list(used_tools),
                "evidenceCount": len(result.evidence),
                "terminalReason": result.terminal_reason,
                "observations": [item.model_dump(mode="json") for item in result.observations],
                "graphPaths": graph_paths,
            }
            await session.execute(
                text(
                    """
                    UPDATE agent_runs
                    SET state = :state, task_type = :task_type, answer = :answer,
                        evidence_status = :evidence_status, usage = CAST(:usage AS jsonb),
                        degradation_reason = :reason, finished_at = :now
                    WHERE id = :id
                    """
                ),
                {
                    "id": run_id,
                    "state": result.state.value,
                    "task_type": task_type,
                    "answer": result.answer.answer,
                    "evidence_status": evidence_status,
                    "usage": json.dumps(usage, ensure_ascii=False),
                    "reason": result.terminal_reason,
                    "now": now,
                },
            )
            await self._append_audit(
                session,
                event_type="AGENT_RUN_COMPLETED",
                actor_id=context.principal_id,
                correlation_id=context.correlation_id,
                resource_type="AGENT_RUN",
                resource_id=str(run_id),
                decision=result.state.value,
                reason_code=evidence_status,
                payload={
                    "citationCount": len(citations),
                    "toolCalls": result.tool_calls,
                    "tools": list(used_tools),
                },
            )

        failure = None
        if result.state in {AgentRunState.FAILED, AgentRunState.TIMED_OUT}:
            budget_reasons = {
                "AGENT_TIMEOUT",
                "STEP_BUDGET_EXCEEDED",
                "TOOL_BUDGET_EXCEEDED",
            }
            failure = {
                "code": (
                    "TOOL_FAILED" if result.terminal_reason == "RETRIEVAL_FAILED"
                    else "BUDGET_EXCEEDED" if result.terminal_reason in budget_reasons
                    else "INTERNAL_ERROR"
                ),
                "message": (
                    "知识检索暂时失败, 请稍后重试。"
                    if result.terminal_reason == "RETRIEVAL_FAILED"
                    else "Agent 未能在受限预算内完成可靠回答。"
                ),
                "retryable": (
                    result.state == AgentRunState.TIMED_OUT
                    or result.terminal_reason == "RETRIEVAL_FAILED"
                ),
            }
        return {
            "id": str(run_id),
            "correlationId": context.correlation_id,
            "traceId": trace_id,
            "state": result.state.value,
            "taskType": self._task_type(
                tuple(dict.fromkeys(item.tool for item in result.observations)),
                has_graph_paths=bool(graph_paths),
            ),
            "createdAt": created_at.isoformat(),
            "finishedAt": utc_now().isoformat(),
            "answer": {
                "text": result.answer.answer,
                "confidence": "HIGH" if len(citations) > 1 else "MEDIUM",
                "evidenceStatus": "SUFFICIENT" if citations else "INSUFFICIENT",
                "limitations": (
                    [result.terminal_reason]
                    if result.terminal_reason
                    else ([] if citations else ["INSUFFICIENT_EVIDENCE"])
                ),
                "citations": citations,
                "graphPaths": graph_paths,
            },
            "pendingApproval": None,
            "failure": failure,
            "steps": [self.step_dict(step) for step in result.steps],
            "links": {"self": f"/v1/agent-runs/{run_id}", "approval": None},
        }

    @staticmethod
    def step_dict(step: RunStep) -> dict[str, object]:
        return {
            "id": step.id,
            "ordinal": step.ordinal,
            "kind": step.kind.value,
            "state": step.state.value,
            "capabilityName": step.capability_name,
            "resultRef": step.result_ref,
            "startedAt": step.started_at.isoformat() if step.started_at else None,
            "finishedAt": step.finished_at.isoformat() if step.finished_at else None,
        }

    @staticmethod
    def _source_uuid(source_type: str, value: str) -> UUID:
        try:
            return UUID(value)
        except ValueError:
            return uuid5(NAMESPACE_URL, f"atlasmind:{source_type}:{value}")

    @staticmethod
    def _task_type(tools: Sequence[str], *, has_graph_paths: bool = False) -> str:
        if "query_structured_data" in tools or len(set(tools)) > 1:
            return "MULTI_SOURCE"
        if has_graph_paths:
            return "GRAPH"
        return "SIMPLE"

    @staticmethod
    def _graph_paths(result: AgenticRAGResult) -> list[dict[str, object]]:
        paths: list[dict[str, object]] = []
        seen: set[str] = set()
        for envelope in result.evidence:
            for path in envelope.metadata.get("graphPaths", ()):
                if not isinstance(path, dict):
                    continue
                canonical = json.dumps(path, ensure_ascii=False, sort_keys=True, default=str)
                if canonical in seen:
                    continue
                seen.add(canonical)
                paths.append(path)
        return paths[:20]

    @staticmethod
    def _authz_revision(value: str) -> int:
        if not value.startswith("authz:"):
            raise ValueError("trusted authorization reference required")
        return int(value.removeprefix("authz:"))
