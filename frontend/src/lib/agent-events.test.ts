import { EventType } from "@ag-ui/core";
import { describe, expect, it } from "vitest";

import {
  initialAgentStreamState,
  parseAgentEvent,
  reduceAgentEvent,
} from "@/lib/agent-events";

function event(
  type: EventType,
  sequence: number,
  fields: Record<string, unknown>,
) {
  return parseAgentEvent({
    type,
    ...fields,
    metadata: {
      schemaVersion: "1.0",
      eventId: `event-${sequence}`,
      sequence,
      runId: "run-1",
      correlationId: "correlation-1",
      visibility: "PUBLIC",
    },
  });
}

describe("Agent event reducer", () => {
  it("rejects events without valid public replay metadata", () => {
    expect(() => parseAgentEvent({
      type: EventType.RUN_STARTED,
      threadId: "run-1",
      runId: "run-1",
    })).toThrow("Unsupported Agent event schema");

    expect(() => parseAgentEvent({
      type: EventType.RUN_STARTED,
      threadId: "run-1",
      runId: "run-1",
      metadata: {
        schemaVersion: "1.0",
        eventId: "event-1",
        sequence: 1,
        runId: "run-1",
        correlationId: "correlation-1",
        visibility: "INTERNAL",
      },
    })).toThrow("Unsupported Agent event schema");
  });

  it("is idempotent and never regresses on duplicate or out-of-order events", () => {
    const first = reduceAgentEvent(
      initialAgentStreamState,
      event(EventType.TEXT_MESSAGE_CONTENT, 1, { messageId: "answer", delta: "A" }),
    );
    const duplicate = reduceAgentEvent(
      first,
      event(EventType.TEXT_MESSAGE_CONTENT, 1, { messageId: "answer", delta: "duplicate" }),
    );
    const ahead = reduceAgentEvent(
      duplicate,
      event(EventType.TEXT_MESSAGE_CONTENT, 3, { messageId: "answer", delta: "C" }),
    );
    const late = reduceAgentEvent(
      ahead,
      event(EventType.TEXT_MESSAGE_CONTENT, 2, { messageId: "answer", delta: "B" }),
    );

    expect(duplicate).toBe(first);
    expect(late).toBe(ahead);
    expect(late.sequence).toBe(3);
    expect(late.output).toBe("AC");
  });

  it("reduces public activity, tool, citation and error branches", () => {
    let state = reduceAgentEvent(
      initialAgentStreamState,
      event(EventType.ACTIVITY_SNAPSHOT, 1, {
        messageId: "plan-1",
        activityType: "public_reasoning",
        content: { summary: "正在检索企业文档。", reasonCode: "DOCUMENT_FIRST" },
      }),
    );
    state = reduceAgentEvent(state, event(EventType.TOOL_CALL_START, 2, {
      toolCallId: "tool-1",
      toolCallName: "knowledge_search",
    }));
    state = reduceAgentEvent(state, event(EventType.TOOL_CALL_ARGS, 3, {
      toolCallId: "tool-1",
      delta: JSON.stringify({ query: "使用当前用户问题", limit: 8 }),
    }));
    state = reduceAgentEvent(state, event(EventType.TOOL_CALL_RESULT, 4, {
      messageId: "tool-result-1",
      toolCallId: "tool-1",
      content: JSON.stringify({ status: "SUCCEEDED", evidenceCount: 2 }),
      role: "tool",
    }));
    state = reduceAgentEvent(state, event(EventType.CUSTOM, 5, {
      name: "atlasmind.citations",
      value: [{
        id: "citation-1",
        claimLocator: "claim-1",
        supportStatus: "SUPPORTED",
        source: {
          type: "DOCUMENT",
          id: "document-1",
          version: "version-1",
          locator: "paragraph=1",
          title: "Architecture",
          excerpt: "AtlasMind 使用授权证据。",
        },
      }],
    }));
    state = reduceAgentEvent(state, event(EventType.RUN_ERROR, 6, {
      message: "Agent 运行超时。",
      code: "AGENT_TIMEOUT",
    }));

    expect(state.activities[0]).toMatchObject({
      summary: "正在检索企业文档。",
      reasonCode: "DOCUMENT_FIRST",
    });
    expect(state.tools[0]).toMatchObject({
      name: "knowledge_search",
      arguments: { query: "使用当前用户问题", limit: 8 },
      status: "SUCCEEDED",
      evidenceCount: 2,
    });
    expect(state.citations[0].source.title).toBe("Architecture");
    expect(state.error).toEqual({ code: "AGENT_TIMEOUT", message: "Agent 运行超时。" });
    expect(state.terminal).toBe(true);
  });

  it("reduces allowlisted retrieval activities without retaining unknown fields", () => {
    const running = reduceAgentEvent(
      initialAgentStreamState,
      event(EventType.ACTIVITY_SNAPSHOT, 1, {
        messageId: "tool-1:retrieval:vector",
        activityType: "atlasmind.retrieval",
        parentMessageId: "tool-1",
        content: {
          stage: "RETRIEVAL",
          strategyId: "vector",
          status: "RUNNING",
          summary: "正在执行向量检索。",
          rawQuery: "must-not-be-retained",
        },
      }),
    );
    const completed = reduceAgentEvent(
      running,
      event(EventType.ACTIVITY_SNAPSHOT, 2, {
        messageId: "tool-1:retrieval:vector",
        activityType: "atlasmind.retrieval",
        parentMessageId: "tool-1",
        content: {
          stage: "RETRIEVAL",
          strategyId: "vector",
          status: "SUCCEEDED",
          summary: "向量检索已完成。",
          metrics: { durationMs: 12, candidateCount: 8, secretScore: 0.98 },
          selectedStrategies: ["vector", "untrusted_strategy"],
        },
      }),
    );

    expect(completed.retrievalActivities).toHaveLength(1);
    expect(completed.retrievalActivities[0]).toEqual({
      id: "tool-1:retrieval:vector",
      parentId: "tool-1",
      stage: "RETRIEVAL",
      strategyId: "vector",
      status: "SUCCEEDED",
      summary: "向量检索已完成。",
      metrics: { durationMs: 12, candidateCount: 8 },
      selectedStrategies: ["vector"],
      degradationCode: undefined,
    });
  });
});
