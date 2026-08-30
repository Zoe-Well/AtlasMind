import { UndirectedGraph } from "graphology";
import louvain from "graphology-communities-louvain";
import pagerank from "graphology-metrics/centrality/pagerank";

import type { GraphScene } from "./graph-scene";

export interface GraphSceneAnalytics {
  communityCount: number;
  modularity: number;
}

function normalized(value: number, minimum: number, maximum: number) {
  if (maximum <= minimum) return maximum > 0 ? 1 : 0;
  return (value - minimum) / (maximum - minimum);
}

function numericExtent(values: number[]) {
  if (!values.length) return { minimum: 0, maximum: 0 };
  return {
    minimum: Math.min(...values),
    maximum: Math.max(...values),
  };
}

function undirectedProjection(graph: GraphScene) {
  const projection = new UndirectedGraph<{ label: string }, { weight: number }>();
  graph.forEachNode((node, attributes) => projection.addNode(node, { label: attributes.label }));
  graph.forEachEdge((_edge, attributes, source, target) => {
    if (source === target) return;
    const weight = Math.max(0.1, attributes.confidence);
    if (projection.hasEdge(source, target)) {
      projection.updateEdgeAttribute(source, target, "weight", (current) => Number(current ?? 0) + weight);
    } else {
      projection.addEdge(source, target, { weight });
    }
  });
  return projection;
}

function arrangeByCommunity(graph: GraphScene, communities: Record<string, number>) {
  const grouped = new Map<number, string[]>();
  graph.forEachNode((node) => {
    const community = communities[node] ?? 0;
    grouped.set(community, [...(grouped.get(community) ?? []), node]);
  });

  const communityIds = [...grouped.keys()].sort((left, right) => left - right);
  const centerRadius = Math.max(2.5, Math.sqrt(graph.order) * 0.8);
  communityIds.forEach((community, communityIndex) => {
    const centerAngle = communityIds.length === 1 ? 0 : (communityIndex / communityIds.length) * Math.PI * 2;
    const centerX = communityIds.length === 1 ? 0 : Math.cos(centerAngle) * centerRadius;
    const centerY = communityIds.length === 1 ? 0 : Math.sin(centerAngle) * centerRadius;
    const nodes = grouped.get(community) ?? [];
    nodes.sort();
    nodes.forEach((node, nodeIndex) => {
      const angle = (nodeIndex / Math.max(nodes.length, 1)) * Math.PI * 2 + centerAngle;
      const radius = 0.45 + Math.sqrt(nodeIndex + 1) * 0.32;
      graph.mergeNodeAttributes(node, {
        x: centerX + Math.cos(angle) * radius,
        y: centerY + Math.sin(angle) * radius,
      });
    });
  });
}

export function arrangeLocalGraph(
  graph: GraphScene,
  rootEntityId: string,
  maxDepth: number,
) {
  if (!graph.hasNode(rootEntityId)) return;

  const hops = new Map<string, number>([[rootEntityId, 0]]);
  const queue = [rootEntityId];
  for (let cursor = 0; cursor < queue.length; cursor += 1) {
    const node = queue[cursor];
    const hop = hops.get(node) ?? 0;
    if (hop >= maxDepth) continue;
    for (const neighbor of graph.neighbors(node).sort()) {
      if (hops.has(neighbor)) continue;
      hops.set(neighbor, hop + 1);
      queue.push(neighbor);
    }
  }

  const rings = new Map<number, string[]>();
  for (const node of graph.nodes()) {
    const hop = hops.get(node) ?? maxDepth + 1;
    rings.set(hop, [...(rings.get(hop) ?? []), node]);
  }

  graph.setNodeAttribute(rootEntityId, "x", 0);
  graph.setNodeAttribute(rootEntityId, "y", 0);
  for (const [hop, nodes] of [...rings.entries()].sort(([left], [right]) => left - right)) {
    if (hop === 0) continue;
    nodes.sort();
    const radius = hop * 3.5;
    const angleOffset = ((hop - 1) * Math.PI) / Math.max(nodes.length, 1);
    nodes.forEach((node, index) => {
      const angle = (index / nodes.length) * Math.PI * 2 + angleOffset;
      graph.mergeNodeAttributes(node, {
        x: Math.cos(angle) * radius,
        y: Math.sin(angle) * radius,
      });
    });
  }
}

export function analyzeGraphScene(
  graph: GraphScene,
  options: { arrangeCommunities?: boolean } = {},
): GraphSceneAnalytics {
  if (!graph.order) return { communityCount: 0, modularity: 0 };

  const ranks = graph.size
    ? pagerank(graph, { getEdgeWeight: "confidence", alpha: 0.85 })
    : Object.fromEntries(graph.nodes().map((node) => [node, 1 / graph.order]));
  const projection = undirectedProjection(graph);
  const communityResult = projection.size
    ? louvain.detailed(projection, { getEdgeWeight: "weight", randomWalk: false })
    : {
        communities: Object.fromEntries(projection.nodes().map((node, index) => [node, index])),
        count: projection.order,
        modularity: 0,
      };

  const rankExtent = numericExtent(Object.values(ranks));
  const degrees = graph.nodes().map((node) => graph.degree(node));
  const degreeExtent = numericExtent(degrees);
  const documents = graph.nodes().map((node) => graph.getNodeAttribute(node, "documentCount"));
  const documentExtent = numericExtent(documents);

  const scored = graph.nodes().map((node) => {
    const rankScore = normalized(ranks[node] ?? 0, rankExtent.minimum, rankExtent.maximum);
    const degreeScore = normalized(graph.degree(node), degreeExtent.minimum, degreeExtent.maximum);
    const documentScore = normalized(
      graph.getNodeAttribute(node, "documentCount"),
      documentExtent.minimum,
      documentExtent.maximum,
    );
    return { node, score: rankScore * 0.55 + degreeScore * 0.3 + documentScore * 0.15 };
  });
  scored.sort((left, right) => right.score - left.score || left.node.localeCompare(right.node));
  const importantCount = Math.max(1, Math.min(12, Math.ceil(graph.order * 0.22)));
  const importantNodes = new Set(scored.slice(0, importantCount).map(({ node }) => node));

  for (const { node, score } of scored) {
    graph.mergeNodeAttributes(node, {
      importance: score,
      community: communityResult.communities[node] ?? 0,
      isImportant: importantNodes.has(node),
      size: 6 + score * 10,
    });
  }

  if (options.arrangeCommunities) arrangeByCommunity(graph, communityResult.communities);

  return {
    communityCount: communityResult.count,
    modularity: communityResult.modularity,
  };
}
