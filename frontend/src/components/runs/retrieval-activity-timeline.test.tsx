import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RetrievalActivityTimeline } from "./retrieval-activity-timeline";

describe("RetrievalActivityTimeline", () => {
  it("renders public strategy progress and bounded metrics", () => {
    render(<RetrievalActivityTimeline activities={[
      {
        id: "tool-1:retrieval:plan",
        stage: "PLAN",
        status: "SUCCEEDED",
        summary: "检索计划已通过校验。",
        metrics: { estimatedRetrievalCalls: 3 },
        selectedStrategies: ["vector", "bm25", "graph", "fusion", "rerank"],
      },
      {
        id: "tool-1:retrieval:vector",
        parentId: "tool-1",
        stage: "RETRIEVAL",
        strategyId: "vector",
        status: "SUCCEEDED",
        summary: "向量检索已完成。",
        metrics: { durationMs: 18, candidateCount: 12 },
        selectedStrategies: [],
      },
    ]} />);

    expect(screen.getByText("检索计划已通过校验。")).toBeInTheDocument();
    expect(screen.getByText("知识图谱检索")).toBeInTheDocument();
    expect(screen.getByText("向量检索已完成。")).toBeInTheDocument();
    expect(screen.getByText("18 ms")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
  });
});
