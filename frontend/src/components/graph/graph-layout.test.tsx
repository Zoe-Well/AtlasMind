import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createGraphScene, type GraphScene } from "./graph-scene";

const layoutInstances = vi.hoisted(() => [] as Array<{
  killed: boolean;
  start: ReturnType<typeof vi.fn>;
  stop: ReturnType<typeof vi.fn>;
  kill: ReturnType<typeof vi.fn>;
}>);
const sigmaMock = vi.hoisted(() => ({
  getCamera: vi.fn(() => ({ animate: vi.fn() })),
  getGraph: vi.fn(),
  getNodeDisplayData: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("@react-sigma/core", () => ({ useSigma: () => sigmaMock }));
vi.mock("graphology-layout-noverlap", () => ({ default: { assign: vi.fn() } }));
vi.mock("graphology-layout-forceatlas2/worker", () => ({
  default: class MockForceAtlas2LayoutSupervisor {
    killed = false;
    start = vi.fn(() => {
      if (this.killed) throw new Error("layout was killed");
    });
    stop = vi.fn();
    kill = vi.fn(() => { this.killed = true; });

    constructor() {
      layoutInstances.push(this);
    }
  },
}));

import { GraphLayout } from "./graph-layout";
import { getGraphLayoutProfile } from "./graph-layout-config";

describe("GraphLayout worker lifecycle", () => {
  let graph: GraphScene;

  beforeEach(() => {
    vi.useFakeTimers();
    layoutInstances.length = 0;
    graph = createGraphScene();
    graph.addNode("entity-a", {
      x: 0,
      y: 0,
      label: "AtlasMind",
      size: 6,
      color: "#4d55ca",
      entityType: "PRODUCT",
      aliases: [],
      mentionCount: 1,
      documentCount: 1,
      importance: 0,
      community: 0,
      isImportant: false,
    });
    sigmaMock.getGraph.mockReturnValue(graph);
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
  });

  it("creates a fresh worker after a scene revision instead of restarting a killed worker", () => {
    const view = render(<GraphLayout revision={0} />);
    expect(layoutInstances).toHaveLength(1);
    expect(layoutInstances[0].start).toHaveBeenCalledOnce();

    view.rerender(<GraphLayout revision={1} />);

    expect(layoutInstances).toHaveLength(2);
    expect(layoutInstances[0].kill).toHaveBeenCalledOnce();
    expect(layoutInstances[0].killed).toBe(true);
    expect(layoutInstances[1].start).toHaveBeenCalledOnce();
    expect(layoutInstances[1].killed).toBe(false);
  });

  it("increases spacing and reduces label density at configured node thresholds", () => {
    const compact = getGraphLayoutProfile(40);
    const balanced = getGraphLayoutProfile(80);
    const crowded = getGraphLayoutProfile(120);
    const dense = getGraphLayoutProfile(200);

    expect([compact.id, balanced.id, crowded.id, dense.id]).toEqual([
      "COMPACT",
      "BALANCED",
      "CROWDED",
      "DENSE",
    ]);
    expect(crowded.noverlap.settings?.margin).toBeGreaterThan(balanced.noverlap.settings?.margin ?? 0);
    expect(dense.noverlap.settings?.ratio).toBeGreaterThan(crowded.noverlap.settings?.ratio ?? 0);
    expect(dense.labels.density).toBeLessThan(compact.labels.density);
  });
});
