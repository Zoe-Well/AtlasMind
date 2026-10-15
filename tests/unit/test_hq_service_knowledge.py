"""HQ routing, grounding and post-generation source checks; no model/network calls."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from atlasmind.api.service import HqAnswerRequest, ServiceKnowledge
from atlasmind.infrastructure.openai_compatible import GroundedAnswer


def service(route="knowledge"):
    chunk = str(uuid4())
    row = dict(
        document_id=str(uuid4()),
        version_id=str(uuid4()),
        chunk_id=chunk,
        title="合成简历",
        locator="page 1",
        digest="sha256:" + "a" * 64,
        content="林青, 软件工程师, 具备企业知识检索项目经验。",
    )
    ai = Mock()
    ai.complete_json = AsyncMock(return_value={"route": route, "query": "介绍林青的简历"})
    ai.answer = AsyncMock(return_value=GroundedAnswer("林青具有软件工程及知识检索经验。", (chunk,)))
    knowledge = ServiceKnowledge(
        SimpleNamespace(ai=ai, engine=Mock(), graph=Mock(), model_capabilities_configured=True),
        str(uuid4()),
    )
    knowledge.search = AsyncMock(return_value={"data": [row], "warnings": []})
    knowledge.validate = AsyncMock(return_value={"valid": True})
    return knowledge, ai, row


async def test_hq_answer_uses_grounding_and_returns_only_selected_validated_citations():
    knowledge, ai, row = service()
    result = await knowledge.answer(HqAnswerRequest(query="介绍林青的简历"))
    assert result["route"] == "knowledge" and result["answer"].startswith("林青")
    assert result["citations"][0]["chunk_id"] == row["chunk_id"]
    assert "content" not in result["citations"][0]
    assert ai.answer.await_args.args[1] == {row["chunk_id"]: row["content"]}
    knowledge.validate.assert_awaited_once()


@pytest.mark.parametrize("enabled", [False, True])
async def test_standard_rerank_is_server_configured_and_disabled_by_default(monkeypatch, enabled):
    knowledge, _, _ = service()
    knowledge.standard = True
    knowledge.runtime.settings = SimpleNamespace(service_rerank_enabled=enabled)
    knowledge.rows = AsyncMock(return_value={})
    workflow = SimpleNamespace(run=AsyncMock(return_value=SimpleNamespace(
        reason_code=None, evidence=[], warnings=(), policy_version=1, metrics={}
    )))
    monkeypatch.setattr("atlasmind.api.service.AdvancedRetrievalWorkflow", lambda *args: workflow)
    await ServiceKnowledge.search(knowledge, "商品上架")
    plan = workflow.run.await_args.kwargs["fixed_plan"]
    assert bool(plan.post_retrieval) == enabled
    assert [item.id for item in plan.retrievers] == ["vector", "bm25"]


async def test_business_routing_never_consumes_ordinary_document_evidence():
    knowledge, ai, _ = service("business")
    result = await knowledge.answer(HqAnswerRequest(query="比较本周商户经营"))
    assert result == {"route": "business"}
    knowledge.search.assert_not_awaited()
    ai.answer.assert_not_awaited()


async def test_revocation_during_generation_discards_answer():
    knowledge, _, _ = service()
    knowledge.validate.return_value = {"valid": False}
    with pytest.raises(HTTPException) as error:
        await knowledge.answer(HqAnswerRequest(query="介绍简历"))
    assert error.value.status_code == 409


@pytest.mark.parametrize("warnings,status", [([], None), (["VECTOR_RETRIEVAL_FAILED"], 503)])
async def test_empty_evidence_differs_from_retrieval_failure(warnings, status):
    knowledge, ai, _ = service()
    knowledge.search.return_value = {"data": [], "warnings": warnings}
    if status:
        with pytest.raises(HTTPException) as error:
            await knowledge.answer(HqAnswerRequest(query="介绍简历"))
        assert error.value.status_code == status
    else:
        result = await knowledge.answer(HqAnswerRequest(query="介绍简历"))
        assert "没有足够证据" in result["answer"] and not result["citations"]
    ai.answer.assert_not_awaited()


async def test_unknown_model_citation_cannot_escape_authorized_candidates():
    knowledge, ai, _ = service()
    ai.answer.return_value = GroundedAnswer("不得展示的回答", (str(uuid4()),))
    with pytest.raises(HTTPException) as error:
        await knowledge.answer(HqAnswerRequest(query="介绍简历"))
    assert error.value.status_code == 503


@pytest.mark.parametrize("warnings", [(), ("VECTOR_RETRIEVAL_FAILED",)])
async def test_shared_customer_service_search_distinguishes_empty_knowledge_from_failure(monkeypatch, warnings):
    knowledge, _, _ = service()
    knowledge.rows = AsyncMock(return_value={})
    workflow = SimpleNamespace(run=AsyncMock(return_value=SimpleNamespace(
        reason_code="NO_AUTHORIZED_EVIDENCE", evidence=[], warnings=warnings, policy_version="test"
    )))
    monkeypatch.setattr("atlasmind.api.service.AdvancedRetrievalWorkflow", lambda *args: workflow)
    if warnings:
        with pytest.raises(HTTPException) as error:
            await ServiceKnowledge.search(knowledge, "公开客服知识")
        assert error.value.status_code == 503 and error.value.detail == "RETRIEVAL_FAILED"
    else:
        assert (await ServiceKnowledge.search(knowledge, "公开客服知识"))["data"] == []


async def test_standard_service_uses_fixed_hybrid_plan_with_existing_limits(monkeypatch):
    knowledge, _, _ = service()
    knowledge.standard = True
    knowledge.rows = AsyncMock(return_value={})
    workflow = SimpleNamespace(run=AsyncMock(return_value=SimpleNamespace(reason_code="NO_AUTHORIZED_EVIDENCE", evidence=[], warnings=(), policy_version="test")))
    monkeypatch.setattr("atlasmind.api.service.AdvancedRetrievalWorkflow", lambda *args: workflow)
    result = await ServiceKnowledge.search(knowledge, "商品首次上架")
    plan = workflow.run.await_args.kwargs['fixed_plan']
    assert [r.id for r in plan.retrievers] == ['vector','bm25']
    assert plan.query_processing == () and plan.reason_code == 'SERVICE_STANDARD_V2'
    assert plan.post_retrieval == ()
    assert result['strategy'] == 'service-standard-v2' and result['elapsed_ms'] >= 0
