"""Opt-in real-model identity regression using synthetic authorized evidence.

Set ATLASMIND_RUN_MODEL_EVAL=1 with the configured Chat and Embedding settings.
These tests do not create documents or mutate indexes. Failure output uses synthetic data only.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

from atlasmind.evaluation.snapshots import EvaluationManifest
from atlasmind.infrastructure.openai_compatible import (
    ANSWER_PROMPT_VERSION,
    OpenAICompatibleClient,
)
from atlasmind.settings import load_settings

DATASET = Path(__file__).parents[1] / "fixtures" / "evaluation" / "answer_identity.jsonl"
CASES = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines()]
pytestmark = [
    pytest.mark.evaluation,
    pytest.mark.skipif(
        os.getenv("ATLASMIND_RUN_MODEL_EVAL") != "1",
        reason="real-model identity evaluation was not requested",
    ),
]


@pytest_asyncio.fixture
async def model() -> AsyncIterator[OpenAICompatibleClient]:
    settings = load_settings()
    client = OpenAICompatibleClient(
        chat_base_url=settings.resolved_chat_base_url,
        chat_api_key=settings.resolved_chat_api_key,
        embedding_base_url=settings.resolved_embedding_base_url,
        embedding_api_key=settings.resolved_embedding_api_key,
        chat_model=settings.resolved_chat_model,
        embedding_model=settings.resolved_embedding_model,
        timeout_seconds=settings.model_timeout_seconds,
        thinking_enabled=settings.chat_thinking_enabled,
    )
    adapter = (
        Path(__file__).parents[2] / "src" / "atlasmind" / "infrastructure" / "openai_compatible.py"
    )
    dataset_digest = f"sha256:{sha256(DATASET.read_bytes()).hexdigest()}"
    manifest = EvaluationManifest(
        code_version=f"sha256:{sha256(adapter.read_bytes()).hexdigest()}",
        dataset=f"answer-identity@1:{dataset_digest}",
        knowledge_snapshot=dataset_digest,
        index_generation="not-used-direct-authorized-evidence",
        retrieval_policy="not-used-answer-stage-regression",
        model=settings.resolved_chat_model,
        prompt=ANSWER_PROMPT_VERSION,
        evaluator="required-facts-forbidden-facts-citation-allowlist@1",
        seed=0,
    )
    print(json.dumps({"identityEvaluationManifest": manifest.as_dict()}, ensure_ascii=False))
    try:
        yield client
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
@pytest.mark.parametrize("streaming", [False, True], ids=["json", "stream"])
async def test_answer_resolves_identity_from_authorized_sources(
    model: OpenAICompatibleClient, case: dict[str, Any], streaming: bool
) -> None:
    evidence = case["evidence"]
    if streaming:
        async def discard(_delta: str) -> None:
            pass

        result = await model.stream_answer(case["query"], evidence, discard)
    else:
        result = await model.answer(case["query"], evidence)

    assert result.answer.strip()
    for alternatives in case["required_groups"]:
        assert any(term in result.answer for term in alternatives), (
            f"{case['id']}: missing required identity facts or clarification"
        )
    assert all(term not in result.answer for term in case["forbidden"]), (
        f"{case['id']}: unsupported identity or injected output: "
        f"{[term for term in case['forbidden'] if term in result.answer]}; answer={result.answer}"
    )
    assert set(result.citation_ids).issubset(evidence), f"{case['id']}: citation outside evidence"
    assert set(case["required_citations"]).issubset(result.citation_ids), (
        f"{case['id']}: missing citation for the documented person"
    )
