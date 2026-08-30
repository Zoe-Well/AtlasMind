import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { KnowledgeWorkbench } from "@/components/knowledge/knowledge-workbench";
import { QueryProvider } from "@/components/providers/query-provider";
import { RunCenter } from "@/components/runs/run-center";
import { RunInspector } from "@/components/runs/run-inspector";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function wrapped(element: React.ReactNode) {
  return render(<QueryProvider>{element}</QueryProvider>);
}

describe("real-data core workbenches", () => {
  it("derives upload metadata without exposing technical fields", async () => {
    server.use(
      http.get("/api/platform/documents", () => HttpResponse.json({ items: [], total: 0 })),
      http.get("/api/platform/documents/00000000-0000-4000-8000-000000000201", () => HttpResponse.json({
        id: "00000000-0000-4000-8000-000000000201",
        title: "员工手册",
        sourceKey: "manual-upload/refreshed",
        status: "ACTIVE",
        activeVersionId: "00000000-0000-4000-8000-000000000202",
        knowledgeScopes: ["00000000-0000-4000-8000-000000000010"],
        createdAt: "2026-08-25T00:00:00Z",
      })),
      http.post("/api/platform/documents", async ({ request }) => {
        const data = await request.formData();
        expect(data.get("title")).toBe("员工手册");
        expect(data.get("sourceKey")).toMatch(/^manual-upload\/[0-9a-f-]+$/);
        expect(data.get("knowledgeScopeCodes")).toBe("scope-public");
        expect(JSON.parse(String(data.get("metadata")))).toMatchObject({
          classification: "INTERNAL",
        });
        return HttpResponse.json({
          document: {
            id: "00000000-0000-4000-8000-000000000201",
            title: "员工手册",
            sourceKey: String(data.get("sourceKey")),
            status: "ACTIVE",
            activeVersionId: "00000000-0000-4000-8000-000000000202",
            knowledgeScopes: ["00000000-0000-4000-8000-000000000010"],
            createdAt: "2026-08-25T00:00:00Z",
          },
          versionId: "00000000-0000-4000-8000-000000000202",
          ingestionJob: {
            id: "00000000-0000-4000-8000-000000000203",
            documentVersionId: "00000000-0000-4000-8000-000000000202",
            state: "SEARCHABLE",
            currentStage: "ACTIVATING",
            attempt: 1,
            createdAt: "2026-08-25T00:00:00Z",
          },
        }, { status: 202 });
      }),
    );

    const user = userEvent.setup();
    wrapped(<KnowledgeWorkbench />);
    await user.click(screen.getByRole("button", { name: "上传文档" }));
    const file = new File(["handbook"], "员工手册.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText(/点击选择需要上传的文件/), {
      target: { files: [file] },
    });

    expect(screen.getByLabelText(/文档标题/)).toHaveValue("员工手册");
    expect(screen.getByLabelText("保存到")).toHaveValue("企业知识库");
    expect(screen.getByLabelText("信息分级")).toHaveValue("INTERNAL");
    expect(screen.queryByLabelText("稳定来源键")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("知识范围")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "开始导入" }));
    expect(await screen.findByText("已可用于问答")).toBeInTheDocument();
    expect(screen.getByText("100%")).toBeInTheDocument();
    expect(screen.getByText("检查文件")).toBeInTheDocument();
    expect(screen.getByText("发布到知识库")).toBeInTheDocument();
  });

  it("renders the authorized document list without an ID lookup workflow", async () => {
    server.use(http.get("/api/platform/documents", () => HttpResponse.json({
      total: 1,
      items: [{
        id: "00000000-0000-4000-8000-000000000101",
        title: "退款管理办法",
        sourceKey: "policy/refund",
        status: "ACTIVE",
        activeVersionId: "00000000-0000-4000-8000-000000000102",
        knowledgeScopes: ["00000000-0000-4000-8000-000000000010"],
        createdAt: "2026-08-25T00:00:00Z",
      }],
    })));
    wrapped(<KnowledgeWorkbench />);
    expect(await screen.findByText("退款管理办法")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("输入文档 ID")).not.toBeInTheDocument();
    expect(screen.getByText("1 份文档")).toBeInTheDocument();
    expect(screen.getByText("已启用")).toBeInTheDocument();
    expect(screen.getByText("当前版本已发布")).toBeInTheDocument();
    expect(screen.queryByText("00000000-0000-4000-8000-000000000101")).not.toBeInTheDocument();
  });

  it("explains document versions with business-friendly labels", async () => {
    const documentId = "00000000-0000-4000-8000-000000000101";
    const activeVersionId = "00000000-0000-4000-8000-000000000102";
    server.use(
      http.get("/api/platform/documents", () => HttpResponse.json({
        total: 1,
        items: [{ id: documentId, title: "退款管理办法", sourceKey: "policy/refund", status: "ACTIVE", activeVersionId, knowledgeScopes: [], createdAt: "2026-08-25T00:00:00Z" }],
      })),
      http.get(`/api/platform/documents/${documentId}/versions`, () => HttpResponse.json({
        total: 2,
        items: [
          { id: activeVersionId, versionLabel: "v2", lifecycleState: "SEARCHABLE", searchable: true, sizeBytes: 2048, createdAt: "2026-08-25T00:00:00Z" },
          { id: "00000000-0000-4000-8000-000000000103", versionLabel: "v1", lifecycleState: "SEARCHABLE", searchable: true, sizeBytes: 1024, createdAt: "2026-08-24T00:00:00Z" },
        ],
      })),
    );
    const user = userEvent.setup();
    wrapped(<KnowledgeWorkbench />);
    await user.click(await screen.findByRole("button", { name: /退款管理办法/ }));
    expect(await screen.findByText("第 2 版")).toBeInTheDocument();
    expect(screen.getByText("第 1 版")).toBeInTheDocument();
    expect(screen.getByText("当前使用")).toBeInTheDocument();
    expect(screen.getByText("历史版本，不参与当前问答")).toBeInTheDocument();
    expect(screen.getByText(/2.0 KB/)).toBeInTheDocument();
  });

  it("presents run records with summaries, short numbers and Chinese types", async () => {
    server.use(http.get("/api/platform/agent-runs", () => HttpResponse.json({
      total: 1,
      items: [{
        id: "12345678-0000-4000-8000-000000000001",
        correlationId: "87654321-0000-4000-8000-000000000001",
        traceId: "trace-001",
        state: "COMPLETED",
        taskType: "MULTI_SOURCE",
        createdAt: "2026-08-25T00:00:00Z",
        finishedAt: "2026-08-25T00:00:03Z",
        answer: { text: "退款申请需要提交订单编号和付款凭证。", confidence: "HIGH", evidenceStatus: "SUFFICIENT", citations: [] },
        links: { self: "/v1/agent-runs/12345678-0000-4000-8000-000000000001" },
      }],
    })));
    wrapped(<RunCenter />);
    expect(await screen.findByText("退款申请需要提交订单编号和付款凭证。")).toBeInTheDocument();
    expect(screen.getByText("运行 #12345678")).toBeInTheDocument();
    expect(screen.getByText("多来源综合")).toBeInTheDocument();
    expect(screen.queryByText("87654321-0000-4000-8000-000000000001")).not.toBeInTheDocument();
  });

  it("shows a truthful run overview and keeps identifiers in technical details", async () => {
    const runId = "12345678-0000-4000-8000-000000000001";
    server.use(http.get(`/api/agent-runs/${runId}`, () => HttpResponse.json({
      id: runId,
      correlationId: "87654321-0000-4000-8000-000000000001",
      traceId: "trace-001",
      state: "COMPLETED",
      taskType: "GRAPH",
      createdAt: "2026-08-25T00:00:00Z",
      finishedAt: "2026-08-25T00:00:03Z",
      answer: { text: "退款政策与审批流程有关。", confidence: "HIGH", evidenceStatus: "SUFFICIENT", citations: [{ id: "citation-1", claimLocator: "answer:0", supportStatus: "SUPPORTED", source: { type: "DOCUMENT", id: "doc-1", version: "v1", locator: "p1", title: "退款政策" } }] },
      steps: [
        { id: "00000000-0000-4000-8000-000000000201", ordinal: 1, kind: "PLAN", state: "SUCCEEDED", finishedAt: "2026-08-25T00:00:01Z" },
        { id: "00000000-0000-4000-8000-000000000202", ordinal: 2, kind: "RETRIEVAL", state: "SUCCEEDED", capabilityName: "search_graph", finishedAt: "2026-08-25T00:00:02Z" },
        { id: "00000000-0000-4000-8000-000000000203", ordinal: 3, kind: "COMPOSE", state: "SUCCEEDED", finishedAt: "2026-08-25T00:00:03Z" },
        { id: "00000000-0000-4000-8000-000000000204", ordinal: 4, kind: "VERIFY", state: "SUCCEEDED", finishedAt: "2026-08-25T00:00:03Z" },
      ],
      links: { self: `/v1/agent-runs/${runId}` },
    })));
    wrapped(<RunInspector runId={runId} />);
    expect(screen.getByText("运行 #12345678")).toBeInTheDocument();
    expect(await screen.findByText("知识关系问答")).toBeInTheDocument();
    expect(screen.getByText("Agent 执行过程")).toBeInTheDocument();
    expect(screen.getByText("分析问题并选择能力")).toBeInTheDocument();
    expect(screen.getByText("查询知识关系")).toBeInTheDocument();
    expect(screen.getByText("校验回答引用")).toBeInTheDocument();
    expect(screen.getByText("技术信息与问题排查")).toBeInTheDocument();
  });

  it("renders empty and failure states from the real run-list API", async () => {
    server.use(http.get("/api/platform/agent-runs", () => HttpResponse.json({ items: [], total: 0 })));
    const rendered = wrapped(<RunCenter />);
    expect(await screen.findByText("还没有真实运行记录")).toBeInTheDocument();
    rendered.unmount();

    server.use(http.get("/api/platform/agent-runs", () => HttpResponse.json({
      title: "Backend unavailable",
      status: 503,
    }, { status: 503 })));
    wrapped(<RunCenter />);
    expect(await screen.findByText("Backend unavailable", {}, { timeout: 3000 })).toBeInTheDocument();
  });
});
