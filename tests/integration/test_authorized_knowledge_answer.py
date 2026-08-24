"""US1 end-to-end authorization, answer, revocation, and citation scenarios."""

from datetime import UTC, datetime, timedelta

import pytest

from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.application.query_knowledge import QueryKnowledge
from atlasmind.domain.common import AuthorizationDenied
from atlasmind.identity.models import Action, AuthorizationSnapshot
from atlasmind.infrastructure.ai_ports import DeterministicEmbedder
from atlasmind.retrieval.lexical_pg import InMemoryLexicalRetriever
from atlasmind.retrieval.pipeline import RetrievalPipeline
from atlasmind.retrieval.policy import RetrievalPolicy
from atlasmind.retrieval.vector_pg import InMemoryVectorRetriever
from tests.fixtures.load_basic_knowledge import load_basic_knowledge


def auth(revision: int = 1) -> AuthContext:
    now = datetime.now(UTC)
    return AuthContext(
        principal_id="employee",
        role_codes=frozenset({"employee"}),
        scope_ids=frozenset({"public"}),
        allowed_actions=frozenset({Action.READ, Action.CITE}),
        authz_revision=revision,
        policy_revision=1,
        correlation_id="00000000-0000-0000-0000-000000000001",
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
    )


def use_case() -> QueryKnowledge:
    chunks = load_basic_knowledge()
    embedder = DeterministicEmbedder()
    pipeline = RetrievalPipeline(
        InMemoryVectorRetriever(chunks),
        InMemoryLexicalRetriever(chunks),
        embedder.embed,
        RetrievalPolicy("simple", 1),
    )
    return QueryKnowledge(pipeline)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_authorized_answer_has_locator_and_no_forbidden_content() -> None:
    run = await use_case().execute(
        "What is the refund policy?",
        auth(),
        AuthorizationSnapshot(1, frozenset({"public"})),
        active_generation=1,
    )
    assert run.evidence_status == "SUFFICIENT"
    assert "30 days" in (run.answer or "")
    assert "FORBIDDEN_MARKER" not in repr(run)
    assert run.citations[0].source.locator == "page=1;paragraph=2"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_no_answer_and_revocation_race_fail_safe() -> None:
    no_answer = await use_case().execute(
        "lunar office policy",
        auth(),
        AuthorizationSnapshot(1, frozenset({"public"})),
        active_generation=2,
    )
    assert no_answer.evidence_status == "INSUFFICIENT"

    with pytest.raises(AuthorizationDenied):
        await use_case().execute(
            "refund",
            auth(1),
            AuthorizationSnapshot(2, frozenset({"public"})),
            active_generation=1,
        )
