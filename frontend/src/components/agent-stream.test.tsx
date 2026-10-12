import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatShell } from "@/components/chat/chat-shell";
import { QueryProvider } from "@/components/providers/query-provider";
import { RunInspector } from "@/components/runs/run-inspector";

const server = setupServer();
const runId = "00000000-0000-4000-8000-000000000201";
const queuedRun = {
  id: runId,
  correlationId: "00000000-0000-4000-8000-000000000202",
  state: "QUEUED",
  taskType: "SIMPLE",
  createdAt: "2026-10-11T00:00:00Z",
  answer: null,
  steps: [],
  links: { self: `/v1/agent-runs/${runId}` },
};

class TestEventSource extends EventTarget {
  static instances: TestEventSource[] = [];
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  close = vi.fn();

  constructor(readonly url: string) {
    super();
    TestEventSource.instances.push(this);
  }

  emit(type: string, sequence: number, fields: Record<string, unknown> = {}) {
    this.dispatchEvent(new MessageEvent(type, { data: JSON.stringify({
      type,
      ...fields,
      metadata: {
        schemaVersion: "1.0", eventId: `event-${sequence}`, sequence,
        runId, correlationId: queuedRun.correlationId, visibility: "PUBLIC",
      },
    }) }));
  }
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
beforeEach(() => {
  TestEventSource.instances = [];
  vi.stubGlobal("EventSource", TestEventSource);
  server.use(
    http.post("/api/agent-runs", () => HttpResponse.json(queuedRun, { status: 202 })),
    http.get(`/api/agent-runs/${runId}`, () => HttpResponse.json(queuedRun)),
  );
});
afterEach(() => { server.resetHandlers(); vi.unstubAllGlobals(); });
afterAll(() => server.close());

describe("Agent event connections", () => {
  it("keeps the authenticated stream through running snapshots and reconnects until completion", async () => {
    render(<QueryProvider><ChatShell mode="local" /></QueryProvider>);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("向企业知识库提问"), "介绍求职者的简历");
    await user.click(screen.getByRole("button", { name: "发送问题" }));
    await waitFor(() => expect(TestEventSource.instances).toHaveLength(1));
    const source = TestEventSource.instances[0];
    expect(source.url).toBe(`/api/platform/agent-runs/${runId}/events`);

    act(() => source.emit("STATE_SNAPSHOT", 1, { snapshot: { ...queuedRun, state: "RUNNING" } }));
    expect(TestEventSource.instances).toHaveLength(1);
    expect(source.close).not.toHaveBeenCalled();
    act(() => source.onerror?.());
    expect(screen.getByRole("alert")).toHaveTextContent("实时连接暂时中断");
    act(() => source.onopen?.());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    act(() => {
      source.emit("TEXT_MESSAGE_CONTENT", 2, { messageId: "answer", delta: "求职者具有 AI 开发经历。" });
      // A replay after reconnection must not duplicate text.
      source.emit("TEXT_MESSAGE_CONTENT", 2, { messageId: "answer", delta: "求职者具有 AI 开发经历。" });
      source.emit("STATE_SNAPSHOT", 3, { snapshot: {
        ...queuedRun, state: "COMPLETED", answer: {
          text: "求职者具有 AI 开发经历。", evidenceStatus: "SUFFICIENT", confidence: "MEDIUM", citations: [],
        },
      } });
      source.emit("RUN_FINISHED", 4, { threadId: runId, runId });
    });
    expect(screen.getByText("求职者具有 AI 开发经历。")).toBeInTheDocument();
    expect(source.close).toHaveBeenCalled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(TestEventSource.instances).toHaveLength(1);
  });

  it("uses the authenticated proxy for run details and closes on the terminal event", async () => {
    const view = render(<QueryProvider><RunInspector runId={runId} /></QueryProvider>);
    await waitFor(() => expect(TestEventSource.instances).toHaveLength(1));
    const source = TestEventSource.instances[0];
    expect(source.url).toBe(`/api/platform/agent-runs/${runId}/events`);
    act(() => source.emit("RUN_FINISHED", 1, { threadId: runId, runId }));
    expect(source.close).toHaveBeenCalled();
    view.unmount();
  });
});
