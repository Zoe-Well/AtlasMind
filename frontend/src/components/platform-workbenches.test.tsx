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

  it("requires explicit confirmation before merging graph entities", async () => {
    server.use(
      http.get("/api/platform/graph/conflicts", () => HttpResponse.json({ relations: ["entity-source"] })),
      http.post("/api/platform/graph/entities/entity-source/merge", async ({ request }) => {
        expect(await request.json()).toEqual({ targetEntityId: "entity-target", approved: true });
        return HttpResponse.json({ id: "entity-source", status: "MERGED", mergedIntoId: "entity-target" });
      }),
    );
    const user = userEvent.setup();
    wrapped(<GraphGovernance />);
    await user.click(await screen.findByRole("button", { name: /关系冲突/ }));
    await user.type(screen.getByLabelText("目标规范实体 ID"), "entity-target");
    expect(screen.getByRole("button", { name: "执行合并" })).toBeDisabled();
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "执行合并" }));
    expect(await screen.findByText(/已合并至 entity-target/)).toBeInTheDocument();
  });

  it("creates an evaluation and displays deterministic gates", async () => {
    server.use(
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
