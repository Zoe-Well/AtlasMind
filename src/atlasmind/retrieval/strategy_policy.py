"""Versioned Advanced RAG policy and deterministic plan validation."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrategyStage(StrEnum):
    QUERY_PROCESSING = "QUERY_PROCESSING"
    RETRIEVAL = "RETRIEVAL"
    FUSION = "FUSION"
    RERANK = "RERANK"


class EmptyParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MultiQueryParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    count: int = Field(default=2, ge=1, le=4)


class SelfQuerySettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    allowed_metadata_fields: frozenset[str] = Field(
        default=frozenset({"businessOwner", "classification"}),
        alias="allowedMetadataFields",
        min_length=1,
        max_length=20,
    )


class StrategyConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    settings: dict[str, Any] = Field(default_factory=dict)


class RetrievalRuntimeBudget(BaseModel):
    """User-configurable limits bounded by server-owned hard ceilings."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    total_timeout_ms: int = Field(default=8_000, alias="totalTimeoutMs", ge=500, le=8_000)
    strategy_timeout_ms: int = Field(default=2_500, alias="strategyTimeoutMs", ge=100, le=4_000)
    max_llm_calls: int = Field(default=4, alias="maxLlmCalls", ge=1, le=6)
    max_embedding_calls: int = Field(default=6, alias="maxEmbeddingCalls", ge=1, le=12)
    max_retrieval_calls: int = Field(default=8, alias="maxRetrievalCalls", ge=1, le=12)
    max_query_variants: int = Field(default=3, alias="maxQueryVariants", ge=1, le=5)
    max_candidates_per_retriever: int = Field(
        default=40, alias="maxCandidatesPerRetriever", ge=1, le=80
    )
    max_total_candidates: int = Field(default=120, alias="maxTotalCandidates", ge=8, le=240)
    result_limit: int = Field(default=8, alias="resultLimit", ge=1, le=12)
    max_strategy_retries: int = Field(default=0, alias="maxStrategyRetries", ge=0, le=1)

    @model_validator(mode="after")
    def validate_cross_limits(self) -> RetrievalRuntimeBudget:
        if self.strategy_timeout_ms > self.total_timeout_ms:
            raise ValueError("strategy timeout cannot exceed total timeout")
        if self.result_limit > self.max_total_candidates:
            raise ValueError("result limit cannot exceed total candidate budget")
        return self


class AdvancedRetrievalPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(default=1, ge=1)
    strategies: dict[str, StrategyConfiguration]
    budget: RetrievalRuntimeBudget = RetrievalRuntimeBudget()

    def as_configuration(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"version"}, by_alias=True)

    def as_api_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json", by_alias=True)


def default_advanced_retrieval_policy() -> AdvancedRetrievalPolicy:
    return AdvancedRetrievalPolicy(
        strategies={
            "query_rewrite": StrategyConfiguration(enabled=False),
            "multi_query": StrategyConfiguration(enabled=False, settings={"count": 2}),
            "hyde": StrategyConfiguration(enabled=False),
            "self_query": StrategyConfiguration(
                enabled=False,
                settings={"allowedMetadataFields": ["businessOwner", "classification"]},
            ),
            "vector": StrategyConfiguration(enabled=True),
            "bm25": StrategyConfiguration(enabled=True),
            "graph": StrategyConfiguration(enabled=True),
            "fusion": StrategyConfiguration(enabled=True),
            "rerank": StrategyConfiguration(enabled=True),
        }
    )


class StrategySelection(BaseModel):
    """Untrusted planner selection; ordering is ignored by the runtime."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=100)
    parameters: dict[str, Any] = Field(default_factory=dict)


class RetrievalPlan(BaseModel):
    """Declarative planner output, never an executable instruction list."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    reason_code: str = Field(alias="reasonCode", min_length=1, max_length=100)
    query_processing: tuple[StrategySelection, ...] = Field(
        default=(), alias="queryProcessing", max_length=8
    )
    retrievers: tuple[StrategySelection, ...] = Field(default=(), max_length=4)
    post_retrieval: tuple[StrategySelection, ...] = Field(
        default=(), alias="postRetrieval", max_length=4
    )


class ValidatedRetrievalPlan(BaseModel):
    """Server-owned canonical plan consumed by the fixed LangGraph topology."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reason_code: str
    query_processing: tuple[StrategySelection, ...]
    retrievers: tuple[StrategySelection, ...]
    rerank: bool
    fusion_required: bool
    estimated_llm_calls: int = Field(ge=1)
    estimated_embedding_calls: int = Field(ge=0)
    estimated_retrieval_calls: int = Field(ge=1)
    estimated_query_variants: int = Field(ge=1)


class StrategyDescriptor(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    id: str
    stage: StrategyStage
    order: int = Field(ge=0)
    description: str
    llm_calls: int = Field(default=0, ge=0, le=2)
    conflicts_with: frozenset[str] = frozenset()
    parameter_model: type[BaseModel] = EmptyParameters
    settings_model: type[BaseModel] = EmptyParameters

    def catalog_item(self, configuration: StrategyConfiguration) -> dict[str, object]:
        return {
            "id": self.id,
            "stage": self.stage.value,
            "description": self.description,
            "enabled": configuration.enabled,
            "settings": configuration.settings,
            "settingsSchema": self.settings_model.model_json_schema(),
            "planParametersSchema": self.parameter_model.model_json_schema(),
            "conflictsWith": sorted(self.conflicts_with),
        }


class RetrievalStrategyRegistry:
    """Internal Strategy registry; it is deliberately not an Agent tool registry."""

    def __init__(self) -> None:
        self._items: dict[str, tuple[StrategyDescriptor, object]] = {}

    def register(self, descriptor: StrategyDescriptor, strategy: object) -> None:
        if descriptor.id in self._items:
            raise ValueError("retrieval strategy already registered")
        self._items[descriptor.id] = (descriptor, strategy)

    def descriptor(self, strategy_id: str) -> StrategyDescriptor:
        try:
            return self._items[strategy_id][0]
        except KeyError as exc:
            raise ValueError(f"unknown retrieval strategy: {strategy_id}") from exc

    def strategy(self, strategy_id: str) -> object:
        try:
            return self._items[strategy_id][1]
        except KeyError as exc:
            raise ValueError(f"unknown retrieval strategy: {strategy_id}") from exc

    @property
    def ids(self) -> frozenset[str]:
        return frozenset(self._items)

    def validate_policy(self, policy: AdvancedRetrievalPolicy) -> None:
        unknown = set(policy.strategies) - self.ids
        missing = self.ids - set(policy.strategies)
        if unknown or missing:
            raise ValueError(
                f"retrieval policy strategy catalog mismatch: unknown={sorted(unknown)}, "
                f"missing={sorted(missing)}"
            )
        for strategy_id, configuration in policy.strategies.items():
            descriptor = self.descriptor(strategy_id)
            descriptor.settings_model.model_validate(configuration.settings)
        if not any(
            policy.strategies[strategy_id].enabled for strategy_id in ("vector", "bm25", "graph")
        ):
            raise ValueError("at least one retriever strategy must be enabled")

    def catalog(self, policy: AdvancedRetrievalPolicy) -> list[dict[str, object]]:
        self.validate_policy(policy)
        ordered = sorted(
            (item[0] for item in self._items.values()),
            key=lambda item: (item.stage.value, item.order, item.id),
        )
        return [descriptor.catalog_item(policy.strategies[descriptor.id]) for descriptor in ordered]

    def validate_plan(
        self,
        draft: RetrievalPlan,
        policy: AdvancedRetrievalPolicy,
    ) -> ValidatedRetrievalPlan:
        self.validate_policy(policy)
        selections = (*draft.query_processing, *draft.retrievers, *draft.post_retrieval)
        identifiers = [item.id for item in selections]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("retrieval plan cannot repeat a strategy")

        selected = set(identifiers)
        for item in selections:
            descriptor = self.descriptor(item.id)
            if not policy.strategies[item.id].enabled:
                raise ValueError(f"retrieval plan selected disabled strategy: {item.id}")
            descriptor.parameter_model.model_validate(item.parameters)
            if descriptor.conflicts_with & selected:
                raise ValueError(f"retrieval plan contains conflicting strategy: {item.id}")

        self._validate_stage(draft.query_processing, StrategyStage.QUERY_PROCESSING)
        self._validate_stage(draft.retrievers, StrategyStage.RETRIEVAL)
        self._validate_stage(draft.post_retrieval, StrategyStage.RERANK)
        if not draft.retrievers:
            raise ValueError("retrieval plan requires at least one retriever")

        query_processing = tuple(
            sorted(
                draft.query_processing,
                key=lambda item: (self.descriptor(item.id).order, item.id),
            )
        )
        retrievers = tuple(
            sorted(draft.retrievers, key=lambda item: self.descriptor(item.id).order)
        )
        rerank = any(item.id == "rerank" for item in draft.post_retrieval)

        variants = 1
        if "query_rewrite" in selected:
            variants += 1
        if "multi_query" in selected:
            selection = next(item for item in query_processing if item.id == "multi_query")
            parameters = MultiQueryParameters.model_validate(selection.parameters)
            configured = MultiQueryParameters.model_validate(
                policy.strategies["multi_query"].settings
            )
            if parameters.count > configured.count:
                raise ValueError("multi-query plan exceeds configured query count")
            variants += parameters.count
        retriever_ids = {item.id for item in retrievers}
        if "hyde" in selected and "vector" not in retriever_ids:
            raise ValueError("HyDE requires the vector retriever")
        text_retrievers = len(retriever_ids & {"vector", "bm25"})
        retrieval_calls = variants * text_retrievers + int("graph" in retriever_ids)
        embedding_calls = variants if "vector" in retriever_ids else 0
        if "hyde" in selected and "vector" in retriever_ids:
            embedding_calls += 1
            retrieval_calls += 1
        if "graph" in retriever_ids:
            embedding_calls += 1
        retry_multiplier = policy.budget.max_strategy_retries + 1
        retrieval_calls *= retry_multiplier
        embedding_calls *= retry_multiplier
        strategy_llm_calls = sum(
            self.descriptor(item.id).llm_calls for item in query_processing
        ) + (self.descriptor("rerank").llm_calls if rerank else 0)
        llm_calls = 1 + strategy_llm_calls * retry_multiplier

        if variants > policy.budget.max_query_variants:
            raise ValueError("retrieval plan exceeds query variant budget")
        if retrieval_calls > policy.budget.max_retrieval_calls:
            raise ValueError("retrieval plan exceeds retrieval call budget")
        if embedding_calls > policy.budget.max_embedding_calls:
            raise ValueError("retrieval plan exceeds embedding call budget")
        if llm_calls > policy.budget.max_llm_calls:
            raise ValueError("retrieval plan exceeds LLM call budget")

        fusion_required = retrieval_calls > 1
        if fusion_required and not policy.strategies["fusion"].enabled:
            raise ValueError("multi-route retrieval requires fusion")

        return ValidatedRetrievalPlan(
            reason_code=draft.reason_code,
            query_processing=query_processing,
            retrievers=retrievers,
            rerank=rerank,
            fusion_required=fusion_required,
            estimated_llm_calls=llm_calls,
            estimated_embedding_calls=embedding_calls,
            estimated_retrieval_calls=retrieval_calls,
            estimated_query_variants=variants,
        )

    def _validate_stage(
        self,
        selections: tuple[StrategySelection, ...],
        expected: StrategyStage,
    ) -> None:
        for selection in selections:
            if self.descriptor(selection.id).stage is not expected:
                raise ValueError(f"strategy {selection.id} is not valid in {expected.value} stage")
