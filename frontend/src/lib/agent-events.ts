import { EventSchemas, EventType, type AGUIEvent } from "@ag-ui/core";

import type { AgentRun, Citation, GraphPath } from "@/lib/api/client";

interface AtlasMetadata {
  schemaVersion: "1.0";
  eventId: string;
  sequence: number;
  runId: string;
  correlationId: string;
  traceId?: string;
  visibility: "PUBLIC";
}

export type AtlasAgentEvent = AGUIEvent & { metadata: AtlasMetadata };

export interface AgentActivity {
  id: string;
  summary: string;
  reasonCode?: string;
  state: "RUNNING" | "SUCCEEDED" | "FAILED";
}

export interface AgentToolActivity {
  id: string;
  name: string;
  arguments?: Record<string, unknown>;
  status: "RUNNING" | "SUCCEEDED" | "EMPTY" | "FAILED";
  evidenceCount?: number;
  reasonCode?: string;
}

export type RetrievalActivityStatus =
  | "RUNNING"
  | "SUCCEEDED"
  | "EMPTY"
  | "SKIPPED"
  | "DEGRADED"
  | "FAILED";

export interface RetrievalActivity {
  id: string;
  parentId?: string;
  stage: "PLAN" | "QUERY_PROCESSING" | "RETRIEVAL" | "FUSION" | "RERANK" | "EVIDENCE" | "WORKFLOW";
  strategyId?: string;
  status: RetrievalActivityStatus;
  summary: string;
  metrics: Record<string, number>;
  selectedStrategies: string[];
  degradationCode?: string;
}

export interface AgentStreamState {
  sequence: number;
  output: string;
  activities: AgentActivity[];
  tools: AgentToolActivity[];
  retrievalActivities: RetrievalActivity[];
  citations: Citation[];
  graphPaths: GraphPath[];
  run: AgentRun | null;
  error: { code?: string; message: string } | null;
  terminal: boolean;
}

export const initialAgentStreamState: AgentStreamState = {
  sequence: 0,
  output: "",
  activities: [],
  tools: [],
  retrievalActivities: [],
  citations: [],
  graphPaths: [],
  run: null,
  error: null,
  terminal: false,
};

export const atlasEventTypes = [
  EventType.RUN_STARTED,
  EventType.RUN_FINISHED,
  EventType.RUN_ERROR,
  EventType.STEP_STARTED,
  EventType.STEP_FINISHED,
  EventType.ACTIVITY_SNAPSHOT,
  EventType.TOOL_CALL_START,
  EventType.TOOL_CALL_ARGS,
  EventType.TOOL_CALL_END,
  EventType.TOOL_CALL_RESULT,
  EventType.TEXT_MESSAGE_START,
  EventType.TEXT_MESSAGE_CONTENT,
  EventType.TEXT_MESSAGE_END,
  EventType.STATE_SNAPSHOT,
  EventType.CUSTOM,
] as const;

export function parseAgentEvent(value: unknown): AtlasAgentEvent {
  const parsed = EventSchemas.parse(value);
  const event = {
    ...(value as Record<string, unknown>),
    ...parsed,
  } as AtlasAgentEvent;
  const metadata = event.metadata;
  if (
    !metadata
    || metadata.schemaVersion !== "1.0"
    || !Number.isSafeInteger(metadata.sequence)
    || metadata.sequence < 1
    || typeof metadata.eventId !== "string"
    || !metadata.eventId
    || typeof metadata.runId !== "string"
    || !metadata.runId
    || typeof metadata.correlationId !== "string"
    || !metadata.correlationId
    || metadata.visibility !== "PUBLIC"
  ) {
    throw new Error("Unsupported Agent event schema");
  }
  return event;
}

function upsertActivity(
  items: AgentActivity[],
  next: AgentActivity,
): AgentActivity[] {
  const index = items.findIndex((item) => item.id === next.id);
  if (index < 0) return [...items, next];
  return items.map((item, itemIndex) => itemIndex === index ? { ...item, ...next } : item);
}

function updateTool(
  items: AgentToolActivity[],
  id: string,
  update: Partial<AgentToolActivity>,
): AgentToolActivity[] {
  const index = items.findIndex((item) => item.id === id);
  if (index < 0) {
    return [...items, { id, name: String(update.name ?? "unknown"), status: "RUNNING", ...update }];
  }
  return items.map((item, itemIndex) => itemIndex === index ? { ...item, ...update } : item);
}

const retrievalStages = new Set<RetrievalActivity["stage"]>([
  "PLAN", "QUERY_PROCESSING", "RETRIEVAL", "FUSION", "RERANK", "EVIDENCE", "WORKFLOW",
]);
const retrievalStatuses = new Set<RetrievalActivityStatus>([
  "RUNNING", "SUCCEEDED", "EMPTY", "SKIPPED", "DEGRADED", "FAILED",
]);
const retrievalStrategies = new Set([
  "query_rewrite", "multi_query", "hyde", "self_query",
  "vector", "bm25", "graph", "fusion", "rerank",
]);
const retrievalMetricNames = new Set([
  "durationMs", "candidateCount", "rankingCount", "graphPathCount",
  "embeddingCallCount", "retrievalCallCount", "inputCandidateCount",
  "outputCandidateCount", "queryVariantCount", "metadataFilterCount",
  "evidenceCount", "graphEvidenceCount", "estimatedLlmCalls",
  "estimatedEmbeddingCalls", "estimatedRetrievalCalls", "estimatedQueryVariants",
]);

function parseRetrievalActivity(
  id: string,
  parentId: string | undefined,
  content: Record<string, unknown>,
): RetrievalActivity | null {
  const stage = String(content.stage) as RetrievalActivity["stage"];
  const status = String(content.status) as RetrievalActivityStatus;
  if (!retrievalStages.has(stage) || !retrievalStatuses.has(status)) return null;
  const summary = typeof content.summary === "string" ? content.summary.trim().slice(0, 240) : "";
  if (!summary) return null;
  const strategyId = typeof content.strategyId === "string"
    && retrievalStrategies.has(content.strategyId)
    ? content.strategyId
    : undefined;
  const metrics: Record<string, number> = {};
  if (content.metrics && typeof content.metrics === "object" && !Array.isArray(content.metrics)) {
    for (const [name, raw] of Object.entries(content.metrics as Record<string, unknown>)) {
      if (retrievalMetricNames.has(name) && typeof raw === "number" && Number.isSafeInteger(raw) && raw >= 0) {
        metrics[name] = raw;
      }
    }
  }
  const selectedStrategies = Array.isArray(content.selectedStrategies)
    ? content.selectedStrategies
      .filter((item): item is string => typeof item === "string" && retrievalStrategies.has(item))
      .slice(0, 12)
    : [];
  return {
    id,
    parentId,
    stage,
    strategyId,
    status,
    summary,
    metrics,
    selectedStrategies,
    degradationCode: typeof content.degradationCode === "string"
      ? content.degradationCode.slice(0, 100)
      : undefined,
  };
}

function upsertRetrievalActivity(
  items: RetrievalActivity[],
  next: RetrievalActivity,
): RetrievalActivity[] {
  const index = items.findIndex((item) => item.id === next.id);
  if (index < 0) return [...items, next];
  return items.map((item, itemIndex) => itemIndex === index ? next : item);
}

export function reduceAgentEvent(
  state: AgentStreamState,
  event: AtlasAgentEvent,
): AgentStreamState {
  const sequence = Number(event.metadata.sequence);
  if (!Number.isSafeInteger(sequence) || sequence <= state.sequence) return state;
  const next = { ...state, sequence };
  const value = event as unknown as Record<string, unknown>;

  switch (event.type) {
    case EventType.ACTIVITY_SNAPSHOT: {
      const content = value.content as Record<string, unknown> | undefined;
      const id = String(value.messageId ?? event.metadata.eventId);
      if (value.activityType === "atlasmind.retrieval" && content) {
        const retrievalActivity = parseRetrievalActivity(
          id,
          typeof value.parentMessageId === "string" ? value.parentMessageId : undefined,
          content,
        );
        if (retrievalActivity) {
          next.retrievalActivities = upsertRetrievalActivity(
            state.retrievalActivities,
            retrievalActivity,
          );
        }
      } else if (typeof content?.summary === "string") {
        next.activities = upsertActivity(state.activities, {
          id,
          summary: content.summary,
          reasonCode: typeof content.reasonCode === "string" ? content.reasonCode : undefined,
          state: "SUCCEEDED",
        });
      }
      break;
    }
    case EventType.STEP_STARTED: {
      const id = String(value.stepId ?? `${value.stepName}-${sequence}`);
      next.activities = upsertActivity(state.activities, {
        id,
        summary: `正在执行${String(value.stepName ?? " Agent 步骤")}`,
        state: "RUNNING",
      });
      break;
    }
    case EventType.STEP_FINISHED: {
      const id = String(value.stepId ?? `${value.stepName}-${sequence}`);
      next.activities = upsertActivity(state.activities, {
        id,
        summary: `${String(value.stepName ?? "Agent 步骤")}已完成`,
        state: value.state === "FAILED" ? "FAILED" : "SUCCEEDED",
      });
      break;
    }
    case EventType.TOOL_CALL_START:
      next.tools = updateTool(
        state.tools,
        String(value.toolCallId),
        { name: String(value.toolCallName), status: "RUNNING" },
      );
      break;
    case EventType.TOOL_CALL_ARGS: {
      let args: Record<string, unknown> = {};
      try { args = JSON.parse(String(value.delta ?? "{}")) as Record<string, unknown>; } catch { /* keep safe empty args */ }
      next.tools = updateTool(state.tools, String(value.toolCallId), { arguments: args });
      break;
    }
    case EventType.TOOL_CALL_RESULT: {
      let result: Record<string, unknown> = {};
      try { result = JSON.parse(String(value.content ?? "{}")) as Record<string, unknown>; } catch { /* render generic result */ }
      next.tools = updateTool(state.tools, String(value.toolCallId), {
        status: ["SUCCEEDED", "EMPTY", "FAILED"].includes(String(result.status))
          ? String(result.status) as AgentToolActivity["status"]
          : "SUCCEEDED",
        evidenceCount: typeof result.evidenceCount === "number" ? result.evidenceCount : undefined,
        reasonCode: typeof result.reasonCode === "string" ? result.reasonCode : undefined,
      });
      break;
    }
    case EventType.TEXT_MESSAGE_CONTENT:
      next.output = state.output + String(value.delta ?? "");
      break;
    case EventType.CUSTOM:
      if (value.name === "atlasmind.citations" && Array.isArray(value.value)) {
        next.citations = value.value as Citation[];
      }
      if (value.name === "atlasmind.graph_paths" && Array.isArray(value.value)) {
        next.graphPaths = value.value as GraphPath[];
      }
      break;
    case EventType.STATE_SNAPSHOT: {
      const snapshot = value.snapshot as AgentRun;
      next.run = snapshot;
      if (snapshot.answer) {
        next.output = snapshot.answer.text;
        next.citations = snapshot.answer.citations;
        next.graphPaths = snapshot.answer.graphPaths ?? [];
      } else if (["FAILED", "TIMED_OUT", "CANCELLED"].includes(snapshot.state)) {
        next.output = "";
      }
      break;
    }
    case EventType.RUN_ERROR:
      next.error = {
        code: typeof value.code === "string" ? value.code : undefined,
        message: String(value.message ?? "Agent 运行失败"),
      };
      if (!state.run?.answer) next.output = "";
      next.terminal = true;
      break;
    case EventType.RUN_FINISHED:
      next.terminal = true;
      break;
  }
  return next;
}
