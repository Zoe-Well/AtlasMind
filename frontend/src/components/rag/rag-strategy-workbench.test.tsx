import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, expect, it } from "vitest";

import { QueryProvider } from "@/components/providers/query-provider";
import { RagStrategyWorkbench } from "@/components/rag/rag-strategy-workbench";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const strategies = {
  query_rewrite: { enabled: true, settings: {} },
  multi_query: { enabled: true, settings: { count: 2 } },
  hyde: { enabled: false, settings: {} },
  self_query: {
    enabled: false,
    settings: { allowedMetadataFields: ["businessOwner", "classification"] },
  },
  vector: { enabled: true, settings: {} },
  bm25: { enabled: true, settings: {} },
  graph: { enabled: true, settings: {} },
  fusion: { enabled: true, settings: {} },
  rerank: { enabled: true, settings: {} },
};

const budget = {
  totalTimeoutMs: 8000,
  strategyTimeoutMs: 2500,
  maxLlmCalls: 4,
  maxEmbeddingCalls: 6,
  maxRetrievalCalls: 8,
  maxQueryVariants: 4,
  maxCandidatesPerRetriever: 40,
  maxTotalCandidates: 120,
  resultLimit: 8,
  maxStrategyRetries: 0,
};

const stages: Record<string, string> = {
  query_rewrite: "QUERY_PROCESSING",
  multi_query: "QUERY_PROCESSING",
  hyde: "QUERY_PROCESSING",
  self_query: "QUERY_PROCESSING",
  vector: "RETRIEVAL",
  bm25: "RETRIEVAL",
  graph: "RETRIEVAL",
  fusion: "FUSION",
  rerank: "RERANK",
};

it("loads, validates, and versions internal Retrieval Strategy configuration", async () => {
  let version = 3;
  server.use(
    http.get("/api/platform/rag/policy", () =>
      HttpResponse.json({ version, strategies, budget, canManage: true }),
    ),
    http.get("/api/platform/rag/strategies", () =>
      HttpResponse.json({
        policyVersion: version,
        strategies: Object.keys(strategies).map((id) => ({
          id,
          stage: stages[id],
          description: id,
          enabled: strategies[id as keyof typeof strategies].enabled,
          settings: strategies[id as keyof typeof strategies].settings,
          settingsSchema: {},
          planParametersSchema: {},
          conflictsWith:
            id === "multi_query" ? ["hyde"] : id === "hyde" ? ["multi_query"] : [],
        })),
      }),
    ),
    http.put("/api/platform/rag/policy", async ({ request }) => {
      const body = (await request.json()) as {
        strategies: Record<string, { enabled: boolean; settings: Record<string, unknown> }>;
        budget: typeof budget;
      };
      expect(body.strategies.hyde.enabled).toBe(true);
      expect(body.strategies.multi_query.enabled).toBe(false);
      version += 1;
      return HttpResponse.json({ ...body, version, canManage: true });
    }),
  );

  const user = userEvent.setup();
  render(<QueryProvider><RagStrategyWorkbench /></QueryProvider>);

  expect(await screen.findByText("策略 v3")).toBeInTheDocument();
  expect(screen.getByText("knowledge_search")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "配置策略" }));
  await user.click(screen.getByRole("checkbox", { name: /HyDE/ }));
  await user.click(screen.getByRole("button", { name: "保存新版本" }));

  await waitFor(() => expect(screen.queryByText("配置 Advanced RAG")).not.toBeInTheDocument());
  expect(await screen.findByText("策略 v4")).toBeInTheDocument();
});
