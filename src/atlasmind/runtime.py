"""Runtime dependency composition for API and ingestion worker processes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from sqlalchemy.ext.asyncio import AsyncEngine

from atlasmind.application.real_mvp import PersistentKnowledgeService, RealAI, RealGraphExtractor
from atlasmind.domain.common import ModelCapabilityUnavailable
from atlasmind.infrastructure.database import create_engine, create_session_factory
from atlasmind.infrastructure.neo4j_graphrag_extraction import Neo4jGraphRAGExtractor
from atlasmind.infrastructure.neo4j_runtime import Neo4jRuntime
from atlasmind.infrastructure.object_store import S3ObjectStore
from atlasmind.infrastructure.openai_compatible import (
    GraphExtraction,
    GroundedAnswer,
    OpenAICompatibleClient,
)
from atlasmind.settings import Settings

LOCAL_PRINCIPAL_ID = "00000000-0000-4000-8000-000000000001"
LOCAL_SCOPE_ID = "00000000-0000-4000-8000-000000000010"


class UnavailableAI:
    """Explicit unavailable boundary used when model capabilities are not configured."""

    def __init__(self, missing_capabilities: tuple[str, ...]) -> None:
        self._missing_capabilities = missing_capabilities

    def _error(self) -> ModelCapabilityUnavailable:
        return ModelCapabilityUnavailable(
            details={"missingCapabilities": list(self._missing_capabilities)}
        )

    async def embed(self, _texts: list[str]) -> list[list[float]]:
        raise self._error()

    async def answer(
        self,
        _query: str,
        _evidence: dict[str, str],
        *,
        graph_facts: tuple[str, ...],
    ) -> GroundedAnswer:
        del graph_facts
        raise self._error()

    async def extract_graph(self, _content: str, *, locator: str) -> GraphExtraction:
        del locator
        raise self._error()


@dataclass(slots=True)
class Runtime:
    settings: Settings
    engine: AsyncEngine
    object_store: S3ObjectStore
    graph: Neo4jRuntime
    ai: RealAI
    knowledge: PersistentKnowledgeService
    missing_model_capabilities: tuple[str, ...] = ()

    @property
    def model_capabilities_configured(self) -> bool:
        return not self.missing_model_capabilities

    async def verify(self) -> None:
        await self.object_store.ensure_bucket()
        await self.graph.verify()

    async def close(self) -> None:
        await self.engine.dispose()
        await self.graph.close()
        close = getattr(self.ai, "close", None)
        if close is not None:
            await close()


def create_runtime(
    settings: Settings,
    *,
    ai: RealAI | None = None,
    graph_extractor: RealGraphExtractor | None = None,
) -> Runtime:
    engine = create_engine(settings.database_url.get_secret_value())
    sessions = create_session_factory(engine)
    object_store = S3ObjectStore(
        bucket=settings.object_store_bucket,
        endpoint_url=str(settings.object_store_endpoint),
        access_key=settings.object_store_access_key.get_secret_value(),
        secret_key=settings.object_store_secret_key.get_secret_value(),
    )
    graph = Neo4jRuntime(
        uri=settings.neo4j_uri,
        username=settings.neo4j_username,
        password=settings.neo4j_password.get_secret_value(),
    )
    missing_capabilities = () if ai is not None else settings.missing_model_capabilities
    model: RealAI
    if ai is not None:
        model = ai
    elif missing_capabilities:
        model = UnavailableAI(missing_capabilities)
    else:
        model = OpenAICompatibleClient(
            chat_base_url=settings.resolved_chat_base_url,
            chat_api_key=settings.resolved_chat_api_key,
            embedding_base_url=settings.resolved_embedding_base_url,
            embedding_api_key=settings.resolved_embedding_api_key,
            chat_model=settings.resolved_chat_model,
            embedding_model=settings.resolved_embedding_model,
            timeout_seconds=settings.model_timeout_seconds,
        )
    extractor = graph_extractor
    if extractor is None:
        if isinstance(model, OpenAICompatibleClient):
            extractor = Neo4jGraphRAGExtractor(model, model_name=settings.resolved_chat_model)
        elif hasattr(model, "extract_graph"):
            extractor = cast(RealGraphExtractor, model)
        else:
            raise ValueError("a graph extractor is required for a custom AI boundary")
    knowledge = PersistentKnowledgeService(
        sessions,
        object_store,
        graph,
        model,
        extractor,
        missing_ai_capabilities=missing_capabilities,
    )
    return Runtime(
        settings,
        engine,
        object_store,
        graph,
        model,
        knowledge,
        missing_capabilities,
    )
