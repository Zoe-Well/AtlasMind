"""Conversation persistence/ownership against an explicit disposable PostgreSQL database."""

from __future__ import annotations

import asyncio
import importlib.util
import os
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from atlasmind.agent.langgraph_rag import AgenticRAGResult
from atlasmind.agent.models import AgentRunState
from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.application.real_mvp import PersistentKnowledgeService
from atlasmind.domain.common import InvalidState, ResourceNotAvailable, utc_now
from atlasmind.identity.models import Action
from atlasmind.infrastructure.openai_compatible import GroundedAnswer

pytestmark = pytest.mark.skipif(
    not os.getenv("ATLASMIND_CONVERSATION_TEST_DB"),
    reason="disposable PostgreSQL required",
)


class AnswerGraph:
    def __init__(self) -> None:
        self.wait: asyncio.Event | None = None
        self.state = AgentRunState.COMPLETED
        self.fail = False

    async def run(self, state: Any, context: Any) -> AgenticRAGResult:
        if self.wait is not None:
            await self.wait.wait()
        if self.fail:
            raise RuntimeError("synthetic model failure")
        return AgenticRAGResult(
            state=self.state,
            answer=GroundedAnswer(answer=f"回答:{state.query}", citation_ids=()),
            evidence=(),
            observations=(),
            steps=(),
            tool_calls=0,
        )


@pytest.fixture
async def environment():
    url = os.environ["ATLASMIND_CONVERSATION_TEST_DB"]
    assert "/atlasmind_conversations_test_" in url, "tests require a disposable database"
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    graph = AnswerGraph()
    services = []

    def service():
        dependency = cast(Any, object())
        value = PersistentKnowledgeService(sessions, dependency, dependency, dependency, dependency)
        value._agent_graph = graph  # type: ignore[assignment]
        services.append(value)
        return value

    now = utc_now()
    context = AuthContext(
        principal_id=str(uuid4()),
        correlation_id=str(uuid4()),
        role_codes=frozenset({"employee"}),
        scope_ids=frozenset({str(uuid4())}),
        allowed_actions=frozenset(Action),
        authz_revision=1,
        policy_revision=1,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )
    try:
        yield service, context, graph, engine
    finally:
        if graph.wait is not None:
            graph.wait.set()
        for value in services:
            await value.close()
        await engine.dispose()


async def test_questions_answers_and_conversation_survive_service_recreation(environment):
    make, context, _, _ = environment
    service = make()
    first = await service.ask(query="第一问\n保留换行", mode="AUTO", context=context)
    second = await service.ask(
        query="第二问", mode="SIMPLE", context=context, conversation_id=str(first["conversationId"])
    )
    restored = make()
    page = await restored.conversations.read(
        str(first["conversationId"]), context.principal_id, read_run=restored.get_run
    )
    assert [item["query"] for item in page["items"]] == ["第一问\n保留换行", "第二问"]
    assert [item["turnIndex"] for item in page["items"]] == [1, 2]
    assert page["items"][0]["answer"]["text"] == "回答:第一问\n保留换行"
    assert page["items"][1]["id"] == second["id"]
    assert page["nextBefore"] is None
    assert len((await restored.conversations.list(context.principal_id))["items"]) == 1
    events = await restored.list_run_events(str(first["id"]), context.principal_id, after=0)
    snapshot = next(
        item.payload["snapshot"] for item in events if item.event_type == "STATE_SNAPSHOT"
    )
    assert snapshot["query"] == "第一问\n保留换行"
    assert snapshot["conversationId"] == first["conversationId"]


async def test_other_user_cannot_list_read_append_or_stream_conversation(environment):
    make, context, _, _ = environment
    service = make()
    run = await service.ask(query="private question", mode="AUTO", context=context)
    other = replace(context, principal_id=str(uuid4()))
    assert (await service.conversations.list(other.principal_id))["items"] == []
    for identifier in (str(run["conversationId"]), str(uuid4())):
        with pytest.raises(ResourceNotAvailable):
            await service.conversations.read(
                identifier, other.principal_id, read_run=service.get_run
            )
        with pytest.raises(ResourceNotAvailable):
            await service.ask(
                query="attack", mode="AUTO", context=other, conversation_id=identifier
            )
    with pytest.raises(ResourceNotAvailable):
        await service.get_run(str(run["id"]), other.principal_id)
    with pytest.raises(ResourceNotAvailable):
        await service.list_run_events(str(run["id"]), other.principal_id, after=0)
    assert len((await service.list_runs(context.principal_id))["items"]) == 1


async def test_active_turn_rejects_concurrent_append_then_accepts_after_cancel(environment):
    make, context, graph, _ = environment
    service = make()
    graph.wait = asyncio.Event()
    first = await service.start_ask(query="waiting", mode="AUTO", context=context)
    with pytest.raises(InvalidState):
        await service.start_ask(
            query="overlap",
            mode="AUTO",
            context=context,
            conversation_id=str(first["conversationId"]),
        )
    cancelled = await service.cancel_run(str(first["id"]), context.principal_id)
    assert cancelled["state"] == "CANCELLED"
    graph.wait.set()
    second = await service.ask(
        query="after cancel",
        mode="AUTO",
        context=context,
        conversation_id=str(first["conversationId"]),
    )
    assert second["turnIndex"] == 2
    assert second["state"] == "COMPLETED"


@pytest.mark.parametrize(
    "state", [AgentRunState.FAILED, AgentRunState.TIMED_OUT, AgentRunState.PARTIAL]
)
async def test_terminal_turns_remain_visible_and_allow_next_question(environment, state):
    make, context, graph, _ = environment
    service = make()
    graph.state = state
    first = await service.ask(query="first", mode="AUTO", context=context)
    graph.state = AgentRunState.COMPLETED
    second = await service.ask(
        query="retry", mode="AUTO", context=context, conversation_id=str(first["conversationId"])
    )
    assert (await service.get_run(str(first["id"]), context.principal_id))["state"] == state.value
    assert second["turnIndex"] == 2


async def test_unexpected_failure_keeps_question_and_can_be_reopened(environment):
    make, context, graph, _ = environment
    service = make()
    graph.fail = True
    with pytest.raises(RuntimeError):
        await service.ask(query="failed question", mode="AUTO", context=context)
    run = (await service.list_runs(context.principal_id))["items"][0]
    assert run["state"] == "FAILED" and run["query"] == "failed question"
    assert run["conversationId"]


async def test_earlier_page_cursor_is_stable_when_new_turn_is_added(environment):
    make, context, _, _ = environment
    service = make()
    first = await service.ask(query="one", mode="AUTO", context=context)
    cid = str(first["conversationId"])
    for query in ("two", "three"):
        await service.ask(query=query, mode="AUTO", context=context, conversation_id=cid)
    page = await service.conversations.read(
        cid, context.principal_id, read_run=service.get_run, limit=2
    )
    assert [item["query"] for item in page["items"]] == ["two", "three"]
    await service.ask(query="four", mode="AUTO", context=context, conversation_id=cid)
    earlier = await service.conversations.read(
        cid, context.principal_id, read_run=service.get_run, limit=2, before=page["nextBefore"]
    )
    assert [item["query"] for item in earlier["items"]] == ["one"]
    assert earlier["nextBefore"] is None
    await service.ask(query="separate conversation", mode="AUTO", context=context)
    recent = await service.conversations.list(context.principal_id, limit=1)
    older = await service.conversations.list(
        context.principal_id, limit=1, offset=recent["nextOffset"]
    )
    assert older["items"][0]["id"] == cid and older["nextOffset"] is None


async def test_database_rejects_cross_owner_membership(environment):
    make, context, _, engine = environment
    run = await make().ask(query="one", mode="AUTO", context=context)
    async with engine.begin() as connection:
        with pytest.raises(IntegrityError):
            await connection.execute(
                text("UPDATE agent_runs SET principal_id = :other WHERE id = :id"),
                {"other": uuid4(), "id": UUID(str(run["id"]))},
            )


async def test_legacy_migration_preserves_answers_and_marks_missing_questions(environment):
    _, _, _, engine = environment
    path = Path(__file__).parents[2] / "migrations/versions/0016_conversations.py"
    spec = importlib.util.spec_from_file_location("conversation_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def migrate(connection):
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()

    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            schema = "migration_" + uuid4().hex
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            await connection.execute(
                text("""
                CREATE TABLE agent_runs (
                    id uuid PRIMARY KEY, principal_id uuid NOT NULL,
                    created_at timestamptz NOT NULL, finished_at timestamptz, answer text
                )
            """)
            )
            identifier, principal = uuid4(), uuid4()
            await connection.execute(
                text("""
                INSERT INTO agent_runs VALUES (:id, :principal, now(), now(), 'legacy answer')
            """),
                {"id": identifier, "principal": principal},
            )
            await connection.run_sync(migrate)
            row = (
                (
                    await connection.execute(
                        text("""
                SELECT run.*, conversation.title FROM agent_runs run
                JOIN conversations conversation ON conversation.id = run.conversation_id
            """)
                    )
                )
                .mappings()
                .one()
            )
            assert row["answer"] == "legacy answer"
            assert row["query_text"] is None and row["turn_index"] == 1
            assert row["conversation_id"] == identifier
            assert "原问题未保存" in row["title"]
        finally:
            await transaction.rollback()
