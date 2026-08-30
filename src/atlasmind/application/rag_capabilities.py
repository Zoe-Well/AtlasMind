"""High-level Agent capabilities backed by deterministic internal workflows."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from atlasmind.agent.decisions import AgentToolSpec
from atlasmind.domain.common import new_id, utc_now
from atlasmind.infrastructure.neo4j_runtime import Neo4jRuntime
from atlasmind.retrieval.advanced_workflow import AdvancedRetrievalWorkflow, RetrievalModel
from atlasmind.retrieval.strategy_policy import AdvancedRetrievalPolicy
from atlasmind.tools.contracts import (
    CapabilityRequest,
    CapabilityResult,
    EvidenceEnvelope,
    EvidenceSource,
)
from atlasmind.tools.execution_gateway import CapabilityExecutionContext
from atlasmind.tools.sql_query import SemanticQuery, StructuredDataset, StructuredQueryCompiler


class SearchModel(RetrievalModel, Protocol):
    pass


class KnowledgeSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=1, max_length=4_000)
    limit: int = Field(default=8, ge=1, le=12)
    mode: Literal["AUTO", "SIMPLE", "MULTI_SOURCE", "GRAPH"] = "AUTO"


class StructuredSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset: str = Field(min_length=1, max_length=200)
    metric: str = Field(min_length=1, max_length=200)
    dimensions: tuple[str, ...] = ()
    filters: dict[str, str | int | float] = Field(default_factory=dict)
    limit: int = Field(default=20, ge=1, le=100)


class AgentRAGCapabilities:
    """Small Agent surface; Advanced RAG stays behind knowledge_search."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        model: SearchModel,
        graph: Neo4jRuntime,
        *,
        structured_datasets: tuple[StructuredDataset, ...] = (),
    ) -> None:
        self._sessions = sessions
        self._structured_datasets = structured_datasets
        self._structured_compiler = StructuredQueryCompiler(structured_datasets)
        self._retrieval_workflow = AdvancedRetrievalWorkflow(sessions, model, graph)

    @property
    def retrieval_workflow(self) -> AdvancedRetrievalWorkflow:
        return self._retrieval_workflow

    async def active_retrieval_policy(self) -> AdvancedRetrievalPolicy:
        return await self._retrieval_workflow.load_policy()

    @property
    def tool_specs(self) -> tuple[AgentToolSpec, ...]:
        tools = [
            AgentToolSpec(
                name="knowledge_search",
                description=(
                    "Search authorized enterprise knowledge through one bounded internal retrieval "
                    "workflow. Advanced RAG strategies are internal operators, not Agent tools."
                ),
                input_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 12},
                    },
                },
            )
        ]
        if self._structured_datasets:
            tools.append(
                AgentToolSpec(
                    name="query_structured_data",
                    description=(
                        "Query allowlisted read-only business datasets by semantic metric, "
                        "dimensions, and filters. Raw SQL is never accepted. Available datasets: "
                        + ", ".join(item.name for item in self._structured_datasets)
                    ),
                    input_schema={
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["dataset", "metric"],
                        "properties": {
                            "dataset": {
                                "type": "string",
                                "enum": [item.name for item in self._structured_datasets],
                            },
                            "metric": {"type": "string"},
                            "dimensions": {"type": "array", "items": {"type": "string"}},
                            "filters": {"type": "object"},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                        },
                    },
                )
            )
        return tuple(tools)

    async def knowledge_search(
        self,
        request: CapabilityRequest,
        context: CapabilityExecutionContext,
    ) -> CapabilityResult:
        """Execute the fixed Retrieval Workflow behind one Agent-visible capability."""

        values = KnowledgeSearchInput.model_validate(request.input)
        result = await self._retrieval_workflow.run(
            values.query,
            mode=values.mode,
            limit=values.limit,
            scopes=context.scopes,
            authz_revision=self._authz_revision(request),
            parent_activity_id=request.step_id,
            public_activity_writer=context.public_activity_writer,
        )
        return CapabilityResult(
            status="SUCCEEDED" if result.evidence else "EMPTY",
            evidence=result.evidence,
            reason_code=result.reason_code,
            warnings=result.warnings,
        )

    async def query_structured_data(
        self,
        request: CapabilityRequest,
        context: CapabilityExecutionContext,
    ) -> CapabilityResult:
        values = StructuredSearchInput.model_validate(request.input)
        revision = self._authz_revision(request)
        compiled = self._structured_compiler.compile(
            SemanticQuery(
                dataset=values.dataset,
                metric=values.metric,
                dimensions=values.dimensions,
                filters=values.filters,
                limit=values.limit,
            ),
            scope_ids=context.scopes,
        )
        async with self._sessions() as session, session.begin():
            await session.execute(text("SET TRANSACTION READ ONLY"))
            rows = (await session.execute(text(compiled.statement), compiled.parameters)).mappings()
            facts = tuple(
                json.dumps(dict(row), ensure_ascii=False, sort_keys=True, default=str)
                for row in rows.all()[: values.limit]
            )
        if not facts:
            return CapabilityResult(status="EMPTY", reason_code="NO_STRUCTURED_ROWS")
        canonical = json.dumps(facts, ensure_ascii=False, sort_keys=True)
        evidence_id = new_id()
        envelope = EvidenceEnvelope(
            evidence_id=evidence_id,
            source=EvidenceSource(
                type="STRUCTURED",
                canonical_id=values.dataset,
                version=compiled.dataset_version,
                locator=f"metric={values.metric}",
            ),
            scope_ids=context.scopes,
            content_ref=f"structured-result:{evidence_id}",
            content_digest=f"sha256:{sha256(canonical.encode()).hexdigest()}",
            facts=facts,
            validity="VALID",
            authz_revision=revision,
            verified_at=utc_now(),
        )
        return CapabilityResult(status="SUCCEEDED", evidence=(envelope,))

    @staticmethod
    def _authz_revision(request: CapabilityRequest) -> int:
        prefix = "authz:"
        if not request.auth_context_ref.startswith(prefix):
            raise ValueError("trusted authorization reference required")
        return int(request.auth_context_ref.removeprefix(prefix))
