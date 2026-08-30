import { describe, expect, it } from "vitest";
import noverlap from "graphology-layout-noverlap";

import type { GraphSnapshot } from "@/lib/api/client";
import { analyzeGraphScene, arrangeLocalGraph } from "./graph-analytics";
import { createGraphScene, mergeGraphScene } from "./graph-scene";

const initial: GraphSnapshot = {
  mode: "GLOBAL",
  truncated: false,
  nodes: [
    { id: "entity-a", name: "AtlasMind", type: "PRODUCT", aliases: [], mentionCount: 2, documentCount: 1 },
    { id: "entity-b", name: "PostgreSQL", type: "DATABASE", aliases: ["Postgres"], mentionCount: 1, documentCount: 1 },
  ],
  edges: [{ id: "relation-a", source: "entity-a", target: "entity-b", type: "STORES_IN", confidence: 0.92, evidence: [] }],
};

describe("graph scene", () => {
  it("merges incremental neighbors without duplicating existing entities or relations", () => {
    const graph = createGraphScene();
    mergeGraphScene(graph, initial, { replace: true });
    mergeGraphScene(graph, {
      mode: "LOCAL",
      truncated: false,
      rootEntityId: "entity-a",
      depth: 1,
      nodes: [
        initial.nodes[0],
        { id: "entity-c", name: "Refund API", type: "API", aliases: [], mentionCount: 1, documentCount: 1 },
      ],
      edges: [
        initial.edges[0],
        { id: "relation-b", source: "entity-a", target: "entity-c", type: "EXPOSES", confidence: 0.88, evidence: [] },
      ],
    }, { anchorId: "entity-a" });

    expect(graph.nodes()).toEqual(expect.arrayContaining(["entity-a", "entity-b", "entity-c"]));
    expect(graph.order).toBe(3);
    expect(graph.size).toBe(2);
    expect(graph.getNodeAttribute("entity-c", "entityType")).toBe("API");
  });

  it("replaces the scene when filters or exploration mode change", () => {
    const graph = createGraphScene();
    mergeGraphScene(graph, initial, { replace: true });
    mergeGraphScene(graph, {
      mode: "GLOBAL",
      truncated: false,
      nodes: [initial.nodes[1]],
      edges: [],
    }, { replace: true });

    expect(graph.nodes()).toEqual(["entity-b"]);
    expect(graph.size).toBe(0);
  });

  it("uses PageRank and Louvain to decorate the scene for visual exploration", () => {
    const graph = createGraphScene();
    mergeGraphScene(graph, initial, { replace: true });

    const analytics = analyzeGraphScene(graph, { arrangeCommunities: true });

    expect(analytics.communityCount).toBe(1);
    expect(graph.getNodeAttribute("entity-a", "community")).toBe(0);
    expect(graph.getNodeAttribute("entity-a", "importance")).toBeGreaterThanOrEqual(0);
    expect(graph.getNodeAttribute("entity-a", "size")).toBeGreaterThanOrEqual(6);
    expect(graph.filterNodes((_node, attributes) => attributes.isImportant)).toHaveLength(1);
  });

  it("places local graph hops on stable rings around the selected root", () => {
    const graph = createGraphScene();
    mergeGraphScene(graph, {
      mode: "LOCAL",
      truncated: false,
      rootEntityId: "entity-a",
      depth: 2,
      nodes: [
        initial.nodes[0],
        initial.nodes[1],
        { id: "entity-c", name: "Refund API", type: "API", aliases: [], mentionCount: 1, documentCount: 1 },
      ],
      edges: [
        initial.edges[0],
        { id: "relation-b", source: "entity-b", target: "entity-c", type: "EXPOSES", confidence: 0.88, evidence: [] },
      ],
    }, { replace: true });

    arrangeLocalGraph(graph, "entity-a", 2);

    const radius = (node: string) => Math.hypot(
      graph.getNodeAttribute(node, "x"),
      graph.getNodeAttribute(node, "y"),
    );
    expect(radius("entity-a")).toBe(0);
    expect(radius("entity-a")).toBeLessThan(radius("entity-b"));
    expect(radius("entity-b")).toBeLessThan(radius("entity-c"));

    const firstPositions = graph.mapNodes((node, attributes) => [node, attributes.x, attributes.y]);
    arrangeLocalGraph(graph, "entity-a", 2);
    expect(graph.mapNodes((node, attributes) => [node, attributes.x, attributes.y])).toEqual(firstPositions);
  });

  it("separates nodes whose rendered areas overlap", () => {
    const graph = createGraphScene();
    mergeGraphScene(graph, initial, { replace: true });
    graph.mergeNodeAttributes("entity-a", { x: 0, y: 0, size: 6 });
    graph.mergeNodeAttributes("entity-b", { x: 0.1, y: 0, size: 6 });

    noverlap.assign(graph, {
      maxIterations: 120,
      settings: { gridSize: 20, margin: 2.5, expansion: 1.1, ratio: 1.15, speed: 2 },
    });

    const distance = Math.hypot(
      graph.getNodeAttribute("entity-a", "x") - graph.getNodeAttribute("entity-b", "x"),
      graph.getNodeAttribute("entity-a", "y") - graph.getNodeAttribute("entity-b", "y"),
    );
    expect(distance).toBeGreaterThanOrEqual(18.7);
  });
});
