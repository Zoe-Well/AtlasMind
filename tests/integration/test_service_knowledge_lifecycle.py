"""Real storage / deterministic model checks; not a real-model quality acceptance."""

import asyncio
import os
from uuid import uuid4

import pytest

from atlasmind.api.service import Citation, HqAnswerRequest, ServiceKnowledge
from atlasmind.domain.common import InvalidState
from atlasmind.runtime import LOCAL_PRINCIPAL_ID, create_runtime
from atlasmind.settings import Settings
from tests.integration.test_real_mvp_flow import RepeatableAI

pytestmark = pytest.mark.skipif(
    os.getenv("ATLASMIND_RUN_REAL_MVP") != "1", reason="real storage not requested"
)


class Model(RepeatableAI):
    async def complete_json(self, prompt, **kwargs):
        if prompt.startswith("Route this authorized HQ question"):
            return {"route": "knowledge", "query": "客服联系总部"}
        return {
            "reasonCode": "TEST",
            "retrievers": [{"id": "vector"}, {"id": "bm25"}],
            "postRetrieval": [{"id": "rerank"}],
        }


async def upload(runtime, scope, text="客服联系总部 PostgreSQL", document_id=None):
    args = dict(
        file_name="faq.txt",
        media_type="text/plain",
        content=text.encode(),
        scope_ids=frozenset({scope}),
        metadata={},
        actor_id=LOCAL_PRINCIPAL_ID,
        idempotency_key=str(uuid4()),
        correlation_id=str(uuid4()),
    )
    if document_id:
        return await runtime.knowledge.add_version(document_id=document_id, **args)
    return await runtime.knowledge.upload(
        title="合成客服验收", source_key=f"service-test/{uuid4()}", **args
    )


async def revoke(runtime, scope, document_id):
    await runtime.knowledge.revoke_document(
        document_id, frozenset({scope}), actor_id=LOCAL_PRINCIPAL_ID, correlation_id=str(uuid4())
    )


def citation(row):
    return Citation(**{k: row[k] for k in ("document_id", "version_id", "chunk_id", "digest")})


async def test_scopes_swap_revoke_and_digest_with_real_storage():
    runtime = create_runtime(Settings(), ai=Model())
    scope, private = str(uuid4()), str(uuid4())
    service = ServiceKnowledge(runtime, scope)
    documents = []
    try:
        for sid in (scope, private):
            accepted = await upload(runtime, sid)
            documents.append((sid, accepted["document"]["id"]))
            assert (await runtime.knowledge.process_next())["state"] == "SEARCHABLE"
        result = await service.search("客服联系总部")
        assert len(result["data"]) == 1
        item = citation(result["data"][0])
        assert (await service.validate([item]))["valid"]
        assert not (await ServiceKnowledge(runtime, private).validate([item]))["valid"]
        hq_answer = await service.answer(HqAnswerRequest(query="请介绍客服联系总部文档"))
        assert len(hq_answer["citations"]) == 1
        assert hq_answer["citations"][0]["chunk_id"] == str(item.chunk_id)
        assert not (
            await ServiceKnowledge(runtime, private).validate([citation(hq_answer["citations"][0])])
        )["valid"]
        assert not (
            await service.validate([item.model_copy(update={"digest": "sha256:" + "0" * 64})])
        )["valid"]
        await runtime.knowledge.add_version(
            document_id=documents[0][1],
            file_name="new.txt",
            media_type="text/plain",
            content="更新后联系总部 PostgreSQL".encode(),
            scope_ids=frozenset({scope, private}),
            metadata={},
            actor_id=LOCAL_PRINCIPAL_ID,
            idempotency_key=str(uuid4()),
            correlation_id=str(uuid4()),
        )
        assert (await runtime.knowledge.process_next())["state"] == "SEARCHABLE"
        assert not (await service.validate([item]))["valid"]
        updated = (await service.search("客服联系总部"))["data"]
        assert len(updated) == 1 and updated[0]["version_id"] != str(item.version_id)
        await revoke(runtime, scope, documents[0][1])
        assert not (await service.validate([citation(updated[0])]))["valid"]
        assert (await service.search("客服联系总部"))["data"] == []
        empty_hq = await service.answer(HqAnswerRequest(query="请介绍客服联系总部文档"))
        assert not empty_hq["citations"] and "没有足够证据" in empty_hq["answer"]
    finally:
        for sid, did in documents:
            await revoke(runtime, sid, did)
        await runtime.close()


async def test_revocation_while_ingestion_is_waiting_on_model():
    entered, release = asyncio.Event(), asyncio.Event()

    class WaitingModel(Model):
        async def embed(self, texts):
            entered.set()
            await release.wait()
            return await super().embed(texts)

    runtime = create_runtime(Settings(), ai=WaitingModel())
    scope = str(uuid4())
    accepted = await upload(runtime, scope)
    task = asyncio.create_task(runtime.knowledge.process_next())
    try:
        await asyncio.wait_for(entered.wait(), 10)
        await revoke(runtime, scope, accepted["document"]["id"])
        release.set()
        await asyncio.wait_for(task, 20)
        service = ServiceKnowledge(runtime, scope)
        assert (await service.search("客服联系总部"))["data"] == []
    finally:
        release.set()
        await task
        await revoke(runtime, scope, accepted["document"]["id"])
        await runtime.close()


async def test_late_old_ingestion_does_not_replace_newer_active_version():
    runtime = create_runtime(Settings(), ai=Model())
    scope = str(uuid4())
    accepted = await upload(runtime, scope)
    did = accepted["document"]["id"]
    try:
        old = await runtime.knowledge._claim_next()
        latest = await upload(runtime, scope, "新版客服 PostgreSQL", did)
        assert (await runtime.knowledge.process_next())["state"] == "SEARCHABLE"
        with pytest.raises(InvalidState):
            await runtime.knowledge._process_claimed(old)
        doc = await runtime.knowledge.get_document(did, frozenset({scope}))
        assert doc["activeVersionId"] == latest["versionId"]
    finally:
        await revoke(runtime, scope, did)
        await runtime.close()
