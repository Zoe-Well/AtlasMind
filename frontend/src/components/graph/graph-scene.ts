import { MultiDirectedGraph } from "graphology";

import type { GraphEdge, GraphNode, GraphSnapshot } from "@/lib/api/client";
import { DEFAULT_EDGE_COLOR, entityColor } from "./graph-style";

export interface SceneNodeAttributes {
  x: number;
  y: number;
  label: string;
  size: number;
  color: string;
  entityType: string;
  aliases: string[];
  mentionCount: number;
  documentCount: number;
  importance: number;
  community: number;
  isImportant: boolean;
  highlighted?: boolean;
}

export interface SceneEdgeAttributes {
  label: string;
  size: number;
  color: string;
  relationType: string;
  confidence: number;
  evidenceCount: number;
}

export type GraphScene = MultiDirectedGraph<SceneNodeAttributes, SceneEdgeAttributes>;

export function createGraphScene() {
  return new MultiDirectedGraph<SceneNodeAttributes, SceneEdgeAttributes>();
}

function seededPosition(id: string, index: number) {
  let hash = 2166136261;
  for (const character of id) hash = Math.imul(hash ^ character.charCodeAt(0), 16777619);
  const angle = ((hash >>> 0) / 4294967295) * Math.PI * 2;
  const radius = 1 + Math.sqrt(index + 1) * 0.45;
  return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
}

function attributesForNode(node: GraphNode, position: { x: number; y: number }) {
  return {
    ...position,
    label: node.name,
    size: 6,
    color: entityColor(node.type),
    entityType: node.type,
    aliases: node.aliases,
    mentionCount: node.mentionCount,
    documentCount: node.documentCount,
    importance: 0,
    community: 0,
    isImportant: false,
  } satisfies SceneNodeAttributes;
}

function attributesForEdge(edge: GraphEdge) {
  return {
    label: edge.type,
    relationType: edge.type,
    confidence: edge.confidence,
    evidenceCount: edge.evidence.length,
    size: 0.7 + edge.confidence,
    color: DEFAULT_EDGE_COLOR,
  } satisfies SceneEdgeAttributes;
}

export function mergeGraphScene(
  graph: GraphScene,
  snapshot: GraphSnapshot,
  options: { replace?: boolean; anchorId?: string } = {},
) {
  if (options.replace) graph.clear();
  const initialOrder = graph.order;

  snapshot.nodes.forEach((node, index) => {
    if (graph.hasNode(node.id)) {
      graph.mergeNodeAttributes(node.id, attributesForNode(node, {
        x: graph.getNodeAttribute(node.id, "x"),
        y: graph.getNodeAttribute(node.id, "y"),
      }));
      return;
    }
    let position = seededPosition(node.id, initialOrder + index);
    if (options.anchorId && graph.hasNode(options.anchorId)) {
      position = {
        x: graph.getNodeAttribute(options.anchorId, "x") + position.x * 0.18,
        y: graph.getNodeAttribute(options.anchorId, "y") + position.y * 0.18,
      };
    }
    graph.addNode(node.id, attributesForNode(node, position));
  });

  for (const edge of snapshot.edges) {
    if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target)) continue;
    if (graph.hasEdge(edge.id)) graph.mergeEdgeAttributes(edge.id, attributesForEdge(edge));
    else graph.addDirectedEdgeWithKey(
      edge.id,
      edge.source,
      edge.target,
      attributesForEdge(edge),
    );
  }

  graph.forEachNode((node) => {
    const degree = graph.degree(node);
    const documents = graph.getNodeAttribute(node, "documentCount");
    graph.setNodeAttribute(node, "size", Math.min(18, 5.5 + Math.sqrt(degree + documents) * 2.1));
  });
}

export function graphNode(graph: GraphScene, nodeId: string): GraphNode {
  const attributes = graph.getNodeAttributes(nodeId);
  return {
    id: nodeId,
    name: attributes.label,
    type: attributes.entityType,
    aliases: attributes.aliases,
    mentionCount: attributes.mentionCount,
    documentCount: attributes.documentCount,
  };
}
