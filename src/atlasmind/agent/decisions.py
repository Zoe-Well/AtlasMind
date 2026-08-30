"""Structured, auditable Agent decisions without hidden reasoning traces."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

AgentMode = Literal["AUTO", "SIMPLE", "MULTI_SOURCE", "GRAPH"]
# search_graph is retained only to deserialize historical run decisions. The live
# server-owned Agent tool catalog never exposes or registers it.
AgentToolName = Literal["knowledge_search", "query_structured_data", "search_graph"]


class AgentDecision(BaseModel):
    """One bounded routing decision produced by the planning model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["CALL_TOOL", "ANSWER"]
    tool: AgentToolName | None = None
    arguments: dict[str, object] = Field(default_factory=dict)
    reason_code: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def action_matches_payload(self) -> AgentDecision:
        if self.action == "CALL_TOOL" and self.tool is None:
            raise ValueError("CALL_TOOL requires a tool")
        if self.action == "ANSWER" and (self.tool is not None or self.arguments):
            raise ValueError("ANSWER cannot include a tool or arguments")
        return self


class AgentObservation(BaseModel):
    """Bounded tool result summary supplied to the next planning step."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool: AgentToolName
    status: str
    evidence_count: int = Field(ge=0)
    evidence_summaries: tuple[str, ...] = ()
    reason_code: str | None = None
    warnings: tuple[str, ...] = ()


class AgentToolSpec(BaseModel):
    """Server-owned tool catalog entry visible to the planning model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: AgentToolName
    description: str
    input_schema: dict[str, object]
