"use client";

import { useSigma } from "@react-sigma/core";
import ForceAtlas2LayoutSupervisor from "graphology-layout-forceatlas2/worker";
import noverlap from "graphology-layout-noverlap";
import { useEffect, useMemo } from "react";

import { getGraphLayoutProfile } from "./graph-layout-config";

export function GraphLayout({ revision }: { revision: number }) {
  const sigma = useSigma();
  const order = sigma.getGraph().order;
  const profile = useMemo(() => getGraphLayoutProfile(order), [order]);
  useEffect(() => {
    const graph = sigma.getGraph();
    const layout = new ForceAtlas2LayoutSupervisor(graph, { settings: profile.forceAtlas2 });
    layout.start();
    let focusFrame: number | null = null;
    const duration = Math.min(profile.durationMs, 2_600 + order * 32);
    const timer = window.setTimeout(() => {
      layout.stop();
      noverlap.assign(graph, profile.noverlap);

      const rootEntityId = graph.getAttribute("layoutRootEntityId");
      if (typeof rootEntityId === "string" && graph.hasNode(rootEntityId)) {
        const rootX = graph.getNodeAttribute(rootEntityId, "x");
        const rootY = graph.getNodeAttribute(rootEntityId, "y");
        graph.updateEachNodeAttributes((_node, attributes) => ({
          ...attributes,
          x: attributes.x - rootX,
          y: attributes.y - rootY,
        }), { attributes: ["x", "y"] });
      }
      sigma.refresh();
      if (typeof rootEntityId === "string" && graph.hasNode(rootEntityId)) {
        focusFrame = window.requestAnimationFrame(() => {
          const displayData = sigma.getNodeDisplayData(rootEntityId);
          if (!displayData) return;
          sigma.getCamera().animate(
            { x: displayData.x, y: displayData.y },
            { duration: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 240 },
          );
        });
      }
    }, duration);
    return () => {
      window.clearTimeout(timer);
      if (focusFrame !== null) window.cancelAnimationFrame(focusFrame);
      layout.kill();
    };
  }, [order, profile, revision, sigma]);

  return null;
}
