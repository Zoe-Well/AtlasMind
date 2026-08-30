"use client";

import {
  SigmaContainer,
  useCamera,
  useFullScreen,
  useSetSettings,
  useSigma,
} from "@react-sigma/core";
import "@react-sigma/core/lib/style.css";
import { Expand, Focus, Minus, Plus, Shrink } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { EdgeDisplayData } from "sigma/types";

import type { GraphScene } from "./graph-scene";
import {
  ACTIVE_EDGE_COLOR,
  ENTITY_COLORS,
  ENTITY_LABELS,
  MUTED_EDGE_COLOR,
  MUTED_NODE_COLOR,
} from "./graph-style";
import { GraphEvents } from "./graph-events";
import { GraphLayout } from "./graph-layout";
import { getGraphLayoutProfile } from "./graph-layout-config";
import {
  cameraRatioToZoomPercent,
  clampZoomPercent,
  MAX_ZOOM_PERCENT,
  MIN_ZOOM_PERCENT,
  zoomPercentToCameraRatio,
} from "./graph-camera";

export interface GraphCanvasProps {
  graph: GraphScene;
  revision: number;
  hoveredNode: string | null;
  selectedNode: string | null;
  selectedEdge: string | null;
  onHoverNode: (nodeId: string | null) => void;
  onSelectNode: (nodeId: string | null) => void;
  onSelectEdge: (edgeId: string | null) => void;
  onExpandNode: (nodeId: string) => void;
}

function GraphAppearance({ hoveredNode, selectedNode, selectedEdge }: Pick<GraphCanvasProps, "hoveredNode" | "selectedNode" | "selectedEdge">) {
  const sigma = useSigma();
  const setSettings = useSetSettings();
  const focusNode = hoveredNode ?? selectedNode;

  useEffect(() => {
    const selectedEdgeNodes = new Set<string>(
      selectedEdge && sigma.getGraph().hasEdge(selectedEdge)
        ? sigma.getGraph().extremities(selectedEdge)
        : [],
    );
    setSettings({
      nodeReducer: (node, data) => {
        const next = { ...data };
        const cameraRatio = sigma.getCamera().getState().ratio;
        const important = Boolean(data.isImportant);
        if (!focusNode && !selectedEdge && !important && cameraRatio > 0.82) next.label = "";
        if (!focusNode && !selectedEdge && !important && cameraRatio > 1.35) next.size = Math.max(4.5, data.size * 0.82);
        if (focusNode) {
          const related = node === focusNode || sigma.getGraph().areNeighbors(node, focusNode);
          if (!related) {
            next.color = MUTED_NODE_COLOR;
            next.label = "";
          } else if (node === focusNode) {
            next.highlighted = true;
            next.size = data.size * 1.32;
            next.zIndex = 3;
          }
        } else if (selectedEdgeNodes.has(node)) {
          next.highlighted = true;
          next.size = data.size * 1.18;
          next.zIndex = 2;
        }
        return next;
      },
      edgeReducer: (edge, data) => {
        const next: Partial<EdgeDisplayData> = { ...data, label: null };
        const extremities = sigma.getGraph().extremities(edge);
        const incident = focusNode ? extremities.includes(focusNode) : false;
        if (selectedEdge === edge || incident) {
          next.color = ACTIVE_EDGE_COLOR;
          next.size = Math.max(1.8, data.size * 1.6);
          next.label = data.label;
        } else if (focusNode || selectedEdge) {
          next.color = MUTED_EDGE_COLOR;
        }
        return next;
      },
    });
    sigma.refresh();
  }, [focusNode, selectedEdge, setSettings, sigma]);

  useEffect(() => {
    if (!selectedNode || !sigma.getGraph().hasNode(selectedNode)) return;
    const displayData = sigma.getNodeDisplayData(selectedNode);
    if (!displayData) return;
    const camera = sigma.getCamera();
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    camera.animate(
      {
        x: displayData.x,
        y: displayData.y,
        ratio: Math.min(camera.getState().ratio, 0.72),
      },
      { duration: reducedMotion ? 0 : 420 },
    );
  }, [selectedNode, sigma]);

  return null;
}

function GraphViewportControls() {
  const sigma = useSigma();
  const { zoomIn, zoomOut, reset, goto } = useCamera({ duration: 180, factor: 1.4 });
  const { isFullScreen, toggle } = useFullScreen();
  const editing = useRef(false);
  const [zoomInput, setZoomInput] = useState(() => String(cameraRatioToZoomPercent(sigma.getCamera().getState().ratio)));

  useEffect(() => {
    const camera = sigma.getCamera();
    const updateZoom = () => {
      if (!editing.current) setZoomInput(String(cameraRatioToZoomPercent(camera.getState().ratio)));
    };
    camera.on("updated", updateZoom);
    updateZoom();
    return () => { camera.off("updated", updateZoom); };
  }, [sigma]);

  const applyZoomInput = () => {
    const parsed = Number(zoomInput);
    const percent = clampZoomPercent(parsed);
    editing.current = false;
    setZoomInput(String(percent));
    goto({ ratio: zoomPercentToCameraRatio(percent) });
  };

  const controlClass = "grid size-8 shrink-0 place-items-center border-0 bg-transparent text-[#555b68] transition hover:bg-[#f0f2f7] hover:text-[#20212a]";

  return <div className="absolute right-4 top-4 z-20 flex items-center overflow-hidden rounded-lg border border-[#dfe3eb] bg-white/95 shadow-[0_5px_18px_rgba(31,41,55,0.10)] backdrop-blur" aria-label="图谱视图控制">
    <button type="button" className={controlClass} onClick={() => zoomOut()} aria-label="缩小"><Minus className="size-3.5"/></button>
    <label className="relative flex h-8 w-[72px] items-center border-x border-[#e5e7ed] bg-[#fafbfc]">
      <span className="sr-only">缩放百分比</span>
      <input
        className="h-full w-full border-0 bg-transparent pl-2 pr-6 text-right text-[10px] font-semibold tabular-nums text-[#31333d] outline-none"
        type="number"
        min={MIN_ZOOM_PERCENT}
        max={MAX_ZOOM_PERCENT}
        step={10}
        value={zoomInput}
        onChange={(event) => setZoomInput(event.target.value)}
        onFocus={() => { editing.current = true; }}
        onBlur={() => { if (editing.current) applyZoomInput(); }}
        onKeyDown={(event) => {
          if (event.key === "Enter") event.currentTarget.blur();
          if (event.key === "Escape") {
            editing.current = false;
            setZoomInput(String(cameraRatioToZoomPercent(sigma.getCamera().getState().ratio)));
            event.currentTarget.blur();
          }
        }}
      />
      <span className="pointer-events-none absolute right-2 text-[10px] text-[#858995]">%</span>
    </label>
    <button type="button" className={controlClass} onClick={() => zoomIn()} aria-label="放大"><Plus className="size-3.5"/></button>
    <button type="button" className={`${controlClass} border-l border-[#e5e7ed]`} onClick={() => reset()} aria-label="定位并适应窗口"><Focus className="size-3.5"/></button>
    {document.fullscreenEnabled ? <button type="button" className={`${controlClass} border-l border-[#e5e7ed]`} onClick={toggle} aria-label={isFullScreen ? "退出全屏" : "进入全屏"}>{isFullScreen ? <Shrink className="size-3.5"/> : <Expand className="size-3.5"/>}</button> : null}
  </div>;
}

export function GraphCanvas(props: GraphCanvasProps) {
  const layoutProfile = getGraphLayoutProfile(props.graph.order);
  return <SigmaContainer
    graph={props.graph}
    className="relative h-full min-h-[560px] w-full bg-[#f7f8fb]"
    style={{
      height: "100%",
      minHeight: 560,
      width: "100%",
      backgroundColor: "#f7f8fb",
      backgroundImage: "radial-gradient(circle, rgba(112, 119, 143, 0.13) 1px, transparent 1px)",
      backgroundSize: "22px 22px",
    }}
    settings={{
      allowInvalidContainer: true,
      defaultEdgeType: "line",
      enableEdgeEvents: true,
      edgeLabelColor: { color: "#555b68" },
      edgeLabelSize: 10,
      hideEdgesOnMove: props.graph.order > 100,
      labelColor: { color: "#31333d" },
      labelDensity: layoutProfile.labels.density,
      labelFont: "Inter, ui-sans-serif, system-ui, sans-serif",
      labelGridCellSize: layoutProfile.labels.gridCellSize,
      labelRenderedSizeThreshold: layoutProfile.labels.renderedSizeThreshold,
      labelSize: 12,
      labelWeight: "500",
      maxCameraRatio: 8,
      minCameraRatio: 0.08,
      renderEdgeLabels: true,
      stagePadding: 56,
      zIndex: true,
    }}
  >
    <GraphLayout revision={props.revision} />
    <GraphAppearance
      hoveredNode={props.hoveredNode}
      selectedNode={props.selectedNode}
      selectedEdge={props.selectedEdge}
    />
    <GraphEvents
      onHoverNode={props.onHoverNode}
      onSelectNode={props.onSelectNode}
      onSelectEdge={props.onSelectEdge}
      onExpandNode={props.onExpandNode}
    />
    <GraphViewportControls />
    <div className="pointer-events-none absolute left-4 top-4 z-10 rounded-lg border border-white/80 bg-white/85 px-3 py-2 text-[10px] text-[#656975] shadow-sm backdrop-blur max-[760px]:hidden">
      拖拽节点 · 滚轮缩放 · 双击展开邻居
    </div>
    <div className="pointer-events-none absolute bottom-4 left-4 z-10 max-w-[calc(100%-96px)] rounded-lg border border-white/80 bg-white/90 px-3 py-2 shadow-sm backdrop-blur">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[9px] text-[#656975]">
        {(["SYSTEM", "PRODUCT", "SERVICE", "API", "ERROR_CODE", "TECH_COMPONENT"] as const).map((type) => <span key={type} className="inline-flex items-center gap-1.5"><i className="size-2 rounded-full" style={{ background: ENTITY_COLORS[type] }}/>{ENTITY_LABELS[type]}</span>)}
        <span className="text-[#858995]">节点大小 = 重要度</span>
      </div>
    </div>
  </SigmaContainer>;
}
