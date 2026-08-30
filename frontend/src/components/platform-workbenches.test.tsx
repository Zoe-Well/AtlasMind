import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { ApprovalWorkbench } from "@/components/approvals/approval-workbench";
import { EvaluationWorkbench } from "@/components/evaluations/evaluation-workbench";
import { GraphGovernance } from "@/components/graph/graph-governance";
import { QueryProvider } from "@/components/providers/query-provider";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function wrapped(element: React.ReactNode) {
  return render(<QueryProvider>{element}</QueryProvider>);
}

describe("platform governance workbenches", () => {
  it("loads an approval and prevents a repeated decision", async () => {
    let state = "PENDING";
    server.use(
      http.get("/api/platform/capabilities", () => HttpResponse.json({ dataMode: "persistent", localSuperAdmin: true, features: { knowledge: true, agentRuns: true, graphConflicts: true, graphBrowse: false, approvals: true, evaluations: true } })),
      http.get("/api/platform/approval-requests/approval-1", () => HttpResponse.json({
        id: "approval-1",
        state,
        capability: "change.create@1",
        expiresAt: "2026-08-23T10:00:00Z",
        targetSummary: "change:refund-service",
        parameterSummary: { risk: "HIGH" },
        correlationId: "correlation-1",
      })),
      http.post("/api/platform/approval-requests/approval-1/decision", async ({ request }) => {
        expect(await request.json()).toMatchObject({ decision: "APPROVE" });
        state = "APPROVED";
        return HttpResponse.json({
          id: "approval-1", state, capability: "change.create@1",
          expiresAt: "2026-08-23T10:00:00Z", targetSummary: "change:refund-service",
          parameterSummary: { risk: "HIGH" }, correlationId: "correlation-1",
        });
      }),
    );
    const user = userEvent.setup();
    wrapped(<ApprovalWorkbench initialApprovalId="approval-1" />);
    expect(await screen.findByText("change:refund-service")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "批准" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "批准" })).toBeDisabled());
    expect(screen.getByText("该审批已进入终态，不能重复决定。")).toBeInTheDocument();
  });

  it("shows authorized entities, relations, provenance, and conflicts from real graph APIs", async () => {
    let policyVersion = 3;
    let allowedEntityTypes = ["PRODUCT", "API"];
    const requestedGraphLimits: string[] = [];
    server.use(
      http.get("/api/platform/graph", ({ request }) => {
        requestedGraphLimits.push(new URL(request.url).searchParams.get("limit") ?? "");
        return HttpResponse.json({
        nodes: [
          { id: "entity-a", name: "Aurora", type: "PROJECT", aliases: [], mentionCount: 2, documentCount: 2 },
          { id: "entity-b", name: "李明", type: "PERSON", aliases: [], mentionCount: 1, documentCount: 1 },
        ],
        edges: [
          { id: "relation-a", source: "entity-a", target: "entity-b", type: "LED_BY", confidence: 0.98, evidence: [
            { documentId: "document-a", documentTitle: "项目说明", documentVersionId: "version-a", chunkId: "chunk-a", locator: "paragraph=1" },
          ] },
        ],
        truncated: true,
      });
      }),
      http.get("/api/platform/graph/conflicts", () => HttpResponse.json({ relations: ["entity-source"] })),
      http.get("/api/platform/graph/relations/relation-a", () => HttpResponse.json({
        id: "relation-a", source: "entity-a", target: "entity-b", type: "LED_BY", confidence: 0.98,
        evidence: [{ documentId: "document-a", documentTitle: "项目说明", documentVersionId: "version-a", chunkId: "chunk-a", locator: "paragraph=1" }],
      })),
      http.get("/api/platform/graph/policy", () => HttpResponse.json({
        version: policyVersion,
        allowedEntityTypes,
        availableEntityTypes: ["SYSTEM", "PRODUCT", "SERVICE", "API", "ERROR_CODE", "ORGANIZATION", "ORG_UNIT", "DATABASE", "QUEUE", "TECH_COMPONENT"],
        allowedRelationTypes: ["USES"],
        minimumEntityConfidence: 0.6,
        minimumRelationConfidence: 0.7,
        seedLimit: 8,
        maxHops: 2,
        maxNodes: 40,
        maxPaths: 24,
        maxGraphChunks: 24,
        allowedAliases: {},
        canManage: true,
      })),
      http.put("/api/platform/graph/policy", async ({ request }) => {
        const body = await request.json() as { allowedEntityTypes: string[] };
        expect(body.allowedEntityTypes).toEqual(["PRODUCT", "API", "ERROR_CODE"]);
        allowedEntityTypes = body.allowedEntityTypes;
        policyVersion += 1;
        return HttpResponse.json({
          ...body,
          version: policyVersion,
          availableEntityTypes: ["SYSTEM", "PRODUCT", "SERVICE", "API", "ERROR_CODE", "ORGANIZATION", "ORG_UNIT", "DATABASE", "QUEUE", "TECH_COMPONENT"],
          canManage: true,
        });
      }),
    );
    const user = userEvent.setup();
    wrapped(<GraphGovernance />);
    expect(await screen.findByText(/2 个实体 · 1 条关系/)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "知识图谱探索窗口" })).toBeInTheDocument();
    expect(screen.getByText("选择实体或关系")).toBeInTheDocument();
    expect(screen.getByText(/全局概览只展示.*Top 40/)).toBeInTheDocument();
    await user.selectOptions(screen.getByRole("combobox", { name: "全局 Top 实体数量" }), "80");
    await waitFor(() => expect(requestedGraphLimits).toContain("80"));
    expect(screen.getByText(/全局概览只展示.*Top 80/)).toBeInTheDocument();
    expect(await screen.findByText("实体保留策略")).toBeInTheDocument();
    expect(screen.getByText("策略 v3")).toBeInTheDocument();
    expect((await screen.findAllByText(/Aurora/)).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "查看关系 LED_BY" }));
    expect(await screen.findByText("项目说明")).toBeInTheDocument();
    expect(screen.getByText("paragraph=1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭" }));
    expect(await screen.findByText("entity-source")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "配置实体" }));
    await user.click(screen.getByRole("checkbox", { name: /错误码/ }));
    await user.click(screen.getByRole("button", { name: "保存新版本" }));
    expect(await screen.findByText("策略 v4")).toBeInTheDocument();
  });

  it("keeps the entity policy read-only when the current identity cannot manage it", async () => {
    server.use(
      http.get("/api/platform/graph", () => HttpResponse.json({ nodes: [], edges: [] })),
      http.get("/api/platform/graph/conflicts", () => HttpResponse.json({ relations: [] })),
      http.get("/api/platform/graph/policy", () => HttpResponse.json({
        version: 2,
        allowedEntityTypes: ["PRODUCT"],
        allowedRelationTypes: ["USES"],
        minimumEntityConfidence: 0.6,
        minimumRelationConfidence: 0.7,
        seedLimit: 8,
        maxHops: 2,
        maxNodes: 40,
        maxPaths: 24,
        maxGraphChunks: 24,
        allowedAliases: {},
      })),
    );
    wrapped(<GraphGovernance />);
    expect(await screen.findByText(/当前账号为只读权限/)).toBeInTheDocument();
    expect(screen.getByText(/当前启用 1 \/ 1 类实体/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "配置实体" })).not.toBeInTheDocument();
  });

  it("creates an evaluation and displays deterministic gates", async () => {
    server.use(
      http.get("/api/platform/capabilities", () => HttpResponse.json({ dataMode: "persistent", localSuperAdmin: true, features: { knowledge: true, agentRuns: true, graphConflicts: true, graphBrowse: false, approvals: true, evaluations: true } })),
      http.post("/api/platform/evaluation-runs", () => HttpResponse.json({
        id: "evaluation-1", dataset: { id: "enterprise-rag-regression", version: "2026.08" },
        state: "QUEUED", createdAt: "2026-08-23T00:00:00Z", gates: [],
      }, { status: 202 })),
      http.get("/api/platform/evaluation-runs/evaluation-1", () => HttpResponse.json({
        id: "evaluation-1", dataset: { id: "enterprise-rag-regression", version: "2026.08" },
        state: "PASSED", createdAt: "2026-08-23T00:00:00Z", reportRef: "report:evaluation-1",
        gates: [{ name: "权限泄露", passed: true, value: 0, threshold: 0 }],
      })),
    );
    const user = userEvent.setup();
    wrapped(<EvaluationWorkbench />);
    await user.click(screen.getByRole("button", { name: "新建评估" }));
    await user.click(screen.getByRole("button", { name: "开始评估" }));
    expect(await screen.findByText("权限泄露")).toBeInTheDocument();
    expect(screen.getByText("report:evaluation-1")).toBeInTheDocument();
  });
});
