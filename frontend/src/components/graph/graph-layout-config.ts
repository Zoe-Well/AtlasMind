import type { ForceAtlas2Settings } from "graphology-layout-forceatlas2";
import type { NoverlapLayoutParameters } from "graphology-layout-noverlap";

export interface GraphLayoutProfile {
  id: "COMPACT" | "BALANCED" | "CROWDED" | "DENSE";
  maximumNodes: number;
  durationMs: number;
  forceAtlas2: ForceAtlas2Settings;
  noverlap: NoverlapLayoutParameters;
  labels: {
    density: number;
    gridCellSize: number;
    renderedSizeThreshold: number;
  };
}

const COMMON_FORCE_ATLAS_SETTINGS = {
  edgeWeightInfluence: 0.65,
  linLogMode: true,
  outboundAttractionDistribution: true,
  strongGravityMode: false,
} satisfies ForceAtlas2Settings;

export const GRAPH_LAYOUT_PROFILES: readonly GraphLayoutProfile[] = [
  {
    id: "COMPACT",
    maximumNodes: 40,
    durationMs: 4_200,
    forceAtlas2: {
      ...COMMON_FORCE_ATLAS_SETTINGS,
      barnesHutOptimize: false,
      gravity: 0.1,
      scalingRatio: 8,
      slowDown: 13,
    },
    noverlap: {
      maxIterations: 140,
      settings: { expansion: 1.1, gridSize: 20, margin: 3, ratio: 1.2, speed: 2 },
    },
    labels: { density: 0.45, gridCellSize: 132, renderedSizeThreshold: 7 },
  },
  {
    id: "BALANCED",
    maximumNodes: 80,
    durationMs: 5_000,
    forceAtlas2: {
      ...COMMON_FORCE_ATLAS_SETTINGS,
      barnesHutOptimize: false,
      gravity: 0.11,
      scalingRatio: 11,
      slowDown: 15,
    },
    noverlap: {
      maxIterations: 190,
      settings: { expansion: 1.12, gridSize: 22, margin: 4, ratio: 1.3, speed: 2 },
    },
    labels: { density: 0.36, gridCellSize: 144, renderedSizeThreshold: 7.5 },
  },
  {
    id: "CROWDED",
    maximumNodes: 120,
    durationMs: 6_200,
    forceAtlas2: {
      ...COMMON_FORCE_ATLAS_SETTINGS,
      barnesHutOptimize: true,
      gravity: 0.1,
      scalingRatio: 16,
      slowDown: 18,
    },
    noverlap: {
      maxIterations: 260,
      settings: { expansion: 1.15, gridSize: 24, margin: 5.5, ratio: 1.4, speed: 2 },
    },
    labels: { density: 0.28, gridCellSize: 158, renderedSizeThreshold: 8 },
  },
  {
    id: "DENSE",
    maximumNodes: Number.POSITIVE_INFINITY,
    durationMs: 7_500,
    forceAtlas2: {
      ...COMMON_FORCE_ATLAS_SETTINGS,
      barnesHutOptimize: true,
      gravity: 0.08,
      scalingRatio: 21,
      slowDown: 22,
    },
    noverlap: {
      maxIterations: 360,
      settings: { expansion: 1.18, gridSize: 28, margin: 7, ratio: 1.55, speed: 2 },
    },
    labels: { density: 0.2, gridCellSize: 176, renderedSizeThreshold: 9 },
  },
];

export function getGraphLayoutProfile(nodeCount: number): GraphLayoutProfile {
  return GRAPH_LAYOUT_PROFILES.find(({ maximumNodes }) => nodeCount <= maximumNodes)
    ?? GRAPH_LAYOUT_PROFILES[GRAPH_LAYOUT_PROFILES.length - 1];
}
