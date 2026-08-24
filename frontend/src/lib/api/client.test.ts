import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { createAgentRun, type AgentMode, type AgentRun } from "./client";

const acceptedRun: AgentRun = {
  id: "ef6d2a51-3581-46a4-a1d4-9d43c266f9e8",
  correlationId: "b72e2057-5053-4cea-a995-e57ba59a8d54",
  state: "QUEUED",
  taskType: "SIMPLE",
  createdAt: "2026-08-23T00:00:00Z",
  links: { self: "/v1/agent-runs/ef6d2a51-3581-46a4-a1d4-9d43c266f9e8" },
};

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("typed AgentRun client", () => {
  for (const mode of ["AUTO", "SIMPLE", "MULTI_SOURCE", "GRAPH"] satisfies AgentMode[]) {
    it(`sends the ${mode} mode without browser authority fields`, async () => {
      server.use(http.post("/api/agent-runs", async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        expect(body).toEqual({ query: "退款期限是多少？", mode });
        expect(body).not.toHaveProperty("principal");
        expect(body).not.toHaveProperty("roles");
        expect(body).not.toHaveProperty("scopes");
        expect(body).not.toHaveProperty("token");
        return HttpResponse.json(acceptedRun, { status: 202 });
      }));
      await expect(createAgentRun("退款期限是多少？", mode)).resolves.toEqual(acceptedRun);
    });
  }

  it("surfaces model capability configuration errors", async () => {
    server.use(http.post("/api/agent-runs", () => HttpResponse.json({
      title: "The required AI model capability is not configured.",
      detail: "当前功能不可用: 尚未配置生成模型、Embedding 模型。",
      status: 503,
      code: "MODEL_CAPABILITY_NOT_CONFIGURED",
    }, { status: 503 })));

    await expect(createAgentRun("退款期限是多少？", "AUTO")).rejects.toMatchObject({
      message: "当前功能不可用: 尚未配置生成模型、Embedding 模型。",
      status: 503,
      code: "MODEL_CAPABILITY_NOT_CONFIGURED",
    });
  });
});
