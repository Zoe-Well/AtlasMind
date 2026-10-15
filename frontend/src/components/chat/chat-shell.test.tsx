import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { QueryProvider } from "@/components/providers/query-provider";
import { ChatShell } from "./chat-shell";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("ChatShell", () => {
  it("labels local persistent data and submits a knowledge question", async () => {
    const user = userEvent.setup();
    const submit = vi.fn().mockResolvedValue(undefined);
    render(
      <QueryProvider>
        <ChatShell mode="local" onSubmit={submit} />
      </QueryProvider>,
    );

    expect(screen.getByText("本地真实数据")).toBeInTheDocument();
    await user.type(screen.getByLabelText("向企业知识库提问"), "退款期限是多少？");
    await user.click(screen.getByRole("button", { name: "发送问题" }));
    expect(submit).toHaveBeenCalledWith("退款期限是多少？");
  });

  it("shows the authorization-filtered evidence excerpt returned by the real API", async () => {
    server.use(http.post("/api/agent-runs", () => HttpResponse.json({
      id: "00000000-0000-4000-8000-000000000201",
      correlationId: "00000000-0000-4000-8000-000000000202",
      state: "COMPLETED",
      taskType: "SIMPLE",
      createdAt: "2026-08-25T00:00:00Z",
      finishedAt: "2026-08-25T00:00:01Z",
      answer: {
        text: "退款需要在七日内提出。",
          confidence: "MEDIUM",
          evidenceStatus: "SUFFICIENT",
          graphPaths: [{
            entities: ["退款服务", "退款队列", "支付团队"],
            relations: ["WRITES_TO", "OWNED_BY"],
            directions: [true, true],
            sources: [
              { chunkId: "00000000-0000-4000-8000-000000000204", locator: "第 2 章 · 第 3 段" },
              { chunkId: "00000000-0000-4000-8000-000000000204", locator: "第 2 章 · 第 3 段" },
            ],
          }],
        citations: [{
          id: "00000000-0000-4000-8000-000000000203",
          claimLocator: "退款需要在七日内提出。",
          supportStatus: "SUPPORTED",
          source: {
            type: "DOCUMENT",
            id: "00000000-0000-4000-8000-000000000204",
            version: "00000000-0000-4000-8000-000000000205",
            locator: "第 2 章 · 第 3 段",
            title: "退款管理办法",
            excerpt: "申请人应当在收到商品后的七日内提交退款材料。",
          },
        }],
      },
      links: { self: "/v1/agent-runs/00000000-0000-4000-8000-000000000201" },
    }, { status: 202 })));
    const user = userEvent.setup();
    render(<QueryProvider><ChatShell mode="local" /></QueryProvider>);
    await user.type(screen.getByLabelText("向企业知识库提问"), "退款期限是多少？");
    await user.click(screen.getByRole("button", { name: "发送问题" }));
    expect(await screen.findByText("退款管理办法")).toBeInTheDocument();
    expect(screen.getByText("退款服务 —WRITES_TO→ 退款队列 —OWNED_BY→ 支付团队")).toBeInTheDocument();
    expect(screen.getByText("申请人应当在收到商品后的七日内提交退款材料。")).toBeInTheDocument();
  });
});
