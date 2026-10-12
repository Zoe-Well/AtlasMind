"""OpenAI-compatible model adapter contracts for the real-data MVP."""

from __future__ import annotations

import json

import httpx
import pytest

from atlasmind.infrastructure.openai_compatible import OpenAICompatibleClient


@pytest.mark.parametrize("enabled", [None, False, True])
async def test_explicit_thinking_mode_is_optional_and_preserves_token_budget(enabled) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["max_tokens"] == 1800
        if enabled is None:
            assert "thinking" not in payload
        else:
            assert payload["thinking"] == {"type": "enabled" if enabled else "disabled"}
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = OpenAICompatibleClient(
            base_url="https://model.test/v1",
            api_key="test",
            chat_model="test",
            embedding_model="test",
            thinking_enabled=enabled,
            http_client=http,
        )
        assert await client.complete("Extract the supplied facts") == "{}"


@pytest.mark.asyncio
async def test_embedding_and_structured_graph_extraction_use_configured_models() -> None:
    requests: list[tuple[str, dict[str, object], str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append((str(request.url), payload, request.headers["authorization"]))
        if request.url.path.endswith("/embeddings"):
            return httpx.Response(
                200,
                json={"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]},
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "entities": [
                                        {"name": "AtlasMind", "type": "PRODUCT", "aliases": []},
                                        {"name": "PostgreSQL", "type": "SYSTEM", "aliases": []},
                                    ],
                                    "relations": [
                                        {
                                            "source": "AtlasMind",
                                            "target": "PostgreSQL",
                                            "type": "USES",
                                            "confidence": 0.98,
                                        }
                                    ],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://models.example.test/v1",
    )
    client = OpenAICompatibleClient(
        chat_base_url="https://chat.example.test/v1",
        chat_api_key="chat-secret",
        embedding_base_url="https://embedding.example.test/v1",
        embedding_api_key="embedding-secret",
        chat_model="chat-model",
        embedding_model="embedding-model",
        http_client=http,
    )

    assert await client.embed(["AtlasMind uses PostgreSQL"]) == [[0.1, 0.2, 0.3]]
    graph = await client.extract_graph(
        "AtlasMind uses PostgreSQL",
        locator="paragraph:1",
    )

    assert graph.relations[0].relation_type == "USES"
    assert requests[0][1]["model"] == "embedding-model"
    assert requests[1][1]["model"] == "chat-model"
    assert requests[0][0] == "https://embedding.example.test/v1/embeddings"
    assert requests[0][2] == "Bearer embedding-secret"
    assert requests[1][0] == "https://chat.example.test/v1/chat/completions"
    assert requests[1][2] == "Bearer chat-secret"
    await http.aclose()


@pytest.mark.asyncio
async def test_answer_rejects_citations_not_present_in_supplied_evidence() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"answer": "Unsupported", "citation_ids": ["unknown-chunk"]}
                            )
                        }
                    }
                ]
            },
        )

    http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://models.example.test/v1",
    )
    client = OpenAICompatibleClient(
        base_url="https://models.example.test/v1",
        api_key="test-secret",
        chat_model="chat-model",
        embedding_model="embedding-model",
        http_client=http,
    )

    with pytest.raises(ValueError, match="MODEL_CITATION_OUTSIDE_EVIDENCE"):
        await client.answer(
            "What does AtlasMind use?",
            {"chunk-1": "AtlasMind uses PostgreSQL."},
            graph_facts=(),
        )
    await http.aclose()


@pytest.mark.asyncio
async def test_stream_answer_emits_deltas_stops_at_done_and_validates_citations() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        chunks = [
            {"choices": [{"delta": {"content": "AtlasMind 使用 "}}]},
            {"choices": [{"delta": {"content": "PostgreSQL [SOURCE chunk-1]"}}]},
        ]
        body = "".join(f"data: {json.dumps(item)}\n\n" for item in chunks)
        body += "data: [DONE]\n\n"
        return httpx.Response(200, content=body.encode())

    http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://models.example.test/v1",
    )
    client = OpenAICompatibleClient(
        base_url="https://models.example.test/v1",
        api_key="test-secret",
        chat_model="chat-model",
        embedding_model="embedding-model",
        http_client=http,
    )
    deltas: list[str] = []

    async def on_text(delta: str) -> None:
        deltas.append(delta)

    answer = await client.stream_answer(
        "What does AtlasMind use?",
        {"chunk-1": "AtlasMind uses PostgreSQL."},
        on_text,
    )

    assert deltas == ["AtlasMind 使用 ", "PostgreSQL [SOURCE chunk-1]"]
    assert answer.citation_ids == ("chunk-1",)
    await http.aclose()


@pytest.mark.asyncio
async def test_stream_answer_rejects_malformed_sse_payload() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"data: {not-json}\n\ndata: [DONE]\n\n")

    http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://models.example.test/v1",
    )
    client = OpenAICompatibleClient(
        base_url="https://models.example.test/v1",
        api_key="test-secret",
        chat_model="chat-model",
        embedding_model="embedding-model",
        http_client=http,
    )

    with pytest.raises(ValueError, match="MODEL_STREAM_RESPONSE_INVALID"):
        await client.stream_answer(
            "Question",
            {"chunk-1": "Evidence"},
            lambda _delta: _completed(),
        )
    await http.aclose()


@pytest.mark.asyncio
async def test_stream_answer_rejects_citation_outside_evidence_allowlist() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        payload = {"choices": [{"delta": {"content": "Unsupported [SOURCE unknown-chunk]"}}]}
        body = f"data: {json.dumps(payload)}\n\ndata: [DONE]\n\n"
        return httpx.Response(200, content=body.encode())

    http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://models.example.test/v1",
    )
    client = OpenAICompatibleClient(
        base_url="https://models.example.test/v1",
        api_key="test-secret",
        chat_model="chat-model",
        embedding_model="embedding-model",
        http_client=http,
    )

    with pytest.raises(ValueError, match="MODEL_CITATION_OUTSIDE_EVIDENCE"):
        await client.stream_answer(
            "Question",
            {"chunk-1": "Evidence"},
            lambda _delta: _completed(),
        )
    await http.aclose()


async def _completed() -> None:
    return None


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_answer_without_identity_evidence_does_not_call_model(streaming: bool) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        pytest.fail("An empty evidence set must not be answered from model knowledge")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = OpenAICompatibleClient(
            base_url="https://models.example.test/v1",
            api_key="test-secret",
            chat_model="chat-model",
            embedding_model="embedding-model",
            http_client=http,
        )
        if streaming:
            result = await client.stream_answer(
                "介绍一下陈文帝的简历", {}, lambda _delta: _completed()
            )
        else:
            result = await client.answer("介绍一下陈文帝的简历", {})

    assert result.answer == "当前授权知识中没有足够证据回答该问题。"
    assert result.citation_ids == ()
