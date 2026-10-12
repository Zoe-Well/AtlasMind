"""Persisted failure and SSE snapshot agree when document retrieval cannot finish."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from atlasmind.agent.events import AgentEventType
from atlasmind.retrieval.advanced_workflow import AdvancedRetrievalResult
from atlasmind.runtime import LOCAL_PRINCIPAL_ID, create_runtime
from atlasmind.settings import Settings
from tests.integration.test_real_mvp_flow import RepeatableAI, auth_context

pytestmark = pytest.mark.skipif(
    os.getenv("ATLASMIND_RUN_REAL_MVP") != "1", reason="isolated real database not requested"
)


@pytest.mark.asyncio
@pytest.mark.parametrize("reason,warnings", [
    ("RETRIEVAL_TIMEOUT", ()),
    ("NO_AUTHORIZED_EVIDENCE", ("VECTOR_RETRIEVAL_FAILED",)),
])
async def test_retrieval_failure_persists_retryable_result_and_error_event(reason, warnings):
    runtime = create_runtime(Settings(), ai=RepeatableAI())
    runtime.knowledge._rag_capabilities.retrieval_workflow.run = AsyncMock(return_value=(
        AdvancedRetrievalResult(
            evidence=(), reason_code=reason, warnings=warnings,
            policy_version=1, plan_reason_code="TEST_FAILURE",
        )
    ))
    try:
        completed = await runtime.knowledge.ask(
            query="合成检索失败测试", mode="AUTO", context=auth_context(str(uuid4())),
        )
        assert completed["state"] == "FAILED"
        assert completed["failure"]["code"] == "TOOL_FAILED"
        assert completed["failure"]["retryable"] is True
        assert "稍后重试" in completed["answer"]["text"]
        assert "没有足够证据" not in completed["answer"]["text"]
        persisted = await runtime.knowledge.get_run(completed["id"], LOCAL_PRINCIPAL_ID)
        assert persisted["state"] == completed["state"]
        assert persisted["failure"]["code"] == completed["failure"]["code"]
        assert persisted["failure"]["retryable"] is True
        assert persisted["failure"] == completed["failure"]
        assert persisted["answer"]["text"] == completed["answer"]["text"]
        events = await runtime.knowledge.list_run_events(
            completed["id"], LOCAL_PRINCIPAL_ID, after=0,
        )
        assert events[-1].event_type == AgentEventType.RUN_ERROR
        assert events[-1].payload["code"] == "RETRIEVAL_FAILED"
    finally:
        await runtime.close()
