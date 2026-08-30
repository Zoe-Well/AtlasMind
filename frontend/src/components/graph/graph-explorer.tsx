"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Filter,
  Info,
  LoaderCircle,
  Network,
  PanelRightClose,
  PanelRightOpen,
  RefreshCw,
  Search,
  Sparkles,
} from "lucide-react";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  readGraphNeighbors,
  readGraphSnapshot,
  searchGraphEntities,
  type GraphPolicy,
} from "@/lib/api/client";
import { EntityInspector } from "./entity-inspector";
import { analyzeGraphScene, arrangeLocalGraph } from "./graph-analytics";
import type { GraphCanvasProps } from "./graph-canvas";
import { createGraphScene, mergeGraphScene } from "./graph-scene";
import { ENTITY_LABELS, entityColor } from "./graph-style";
import { RelationInspector } from "./relation-inspector";

type Depth = 1 | 2 | 3;
const TOP_ENTITY_LIMITS = [20, 40, 80, 120, 200] as const;

function TestGraphCanvas(props: GraphCanvasProps) {
  return <div className="relative h-[560px] overflow-auto bg-[#f8f8f6] p-5" aria-label="知识图谱关系网络"><div className="flex flex-wrap gap-2">{props.graph.mapNodes((node, attributes) => <button key={node} type="button" onClick={() => props.onSelectNode(node)} className="rounded-full border bg-white px-3 py-2 text-xs">{attributes.label}</button>)}</div><div className="mt-4 flex flex-wrap gap-2">{props.graph.mapEdges((edge, attributes) => <button key={edge} type="button" aria-label={`查看关系 ${attributes.label}`} onClick={() => props.onSelectEdge(edge)} className="rounded border bg-white px-2 py-1 text-[10px]">{attributes.label}</button>)}</div></div>;
}

const GraphCanvas = process.env.NODE_ENV === "test"
  ? TestGraphCanvas
  : dynamic(() => import("./graph-canvas").then((module) => module.GraphCanvas), { ssr: false });

export function GraphExplorer({ policy }: { policy: GraphPolicy }) {
  const scene = useMemo(() => createGraphScene(), []);
  const defaultGlobalLimit = Math.min(200, Math.max(20, policy.maxNodes));
  const globalLimitOptions = useMemo(
    () => [...new Set<number>([...TOP_ENTITY_LIMITS, defaultGlobalLimit])].sort((left, right) => left - right),
    [defaultGlobalLimit],
  );
  const [mode, setMode] = useState<"GLOBAL" | "LOCAL">("GLOBAL");
  const [globalLimit, setGlobalLimit] = useState(defaultGlobalLimit);
  const [rootEntityId, setRootEntityId] = useState<string | null>(null);
  const [depth, setDepth] = useState<Depth>(1);
  const [entityTypes, setEntityTypes] = useState<string[]>(policy.allowedEntityTypes);
  const [relationTypes, setRelationTypes] = useState<string[]>(policy.allowedRelationTypes);
  const [minimumConfidence, setMinimumConfidence] = useState(policy.minimumRelationConfidence);
  const [filterOpen, setFilterOpen] = useState(false);
  const [searchText, setSearchText] = useState("");
  const [revision, setRevision] = useState(0);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<string | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(true);

  const activeEntityTypes = entityTypes.filter((value) => (policy.allowedEntityTypes as readonly string[]).includes(value));
  const activeRelationTypes = relationTypes.filter((value) => (policy.allowedRelationTypes as readonly string[]).includes(value));

  useEffect(() => {
    const touch = () => setRevision((value) => value + 1);
    const events = ["nodeAdded", "nodeDropped", "edgeAdded", "edgeDropped", "cleared"] as const;
    for (const event of events) scene.on(event, touch);
    return () => { for (const event of events) scene.off(event, touch); };
  }, [scene]);

  const sceneQuery = useQuery({
    queryKey: ["graph-scene", mode, mode === "GLOBAL" ? globalLimit : null, rootEntityId, depth, activeEntityTypes.join(","), activeRelationTypes.join(","), minimumConfidence],
    queryFn: () => mode === "LOCAL" && rootEntityId
      ? readGraphNeighbors(rootEntityId, { depth, entityTypes: activeEntityTypes, relationTypes: activeRelationTypes, minimumConfidence, limit: policy.maxNodes })
      : readGraphSnapshot({ entityTypes: activeEntityTypes, relationTypes: activeRelationTypes, minimumConfidence, limit: globalLimit }),
    enabled: mode === "GLOBAL" || Boolean(rootEntityId),
  });

  useEffect(() => {
    if (!sceneQuery.data) return;
    mergeGraphScene(scene, sceneQuery.data, { replace: true });
    const analytics = analyzeGraphScene(scene, { arrangeCommunities: sceneQuery.data.mode === "GLOBAL" });
    if (sceneQuery.data.mode === "LOCAL" && sceneQuery.data.rootEntityId) {
      arrangeLocalGraph(scene, sceneQuery.data.rootEntityId, sceneQuery.data.depth ?? depth);
      scene.setAttribute("layoutRootEntityId", sceneQuery.data.rootEntityId);
    } else {
      scene.removeAttribute("layoutRootEntityId");
    }
    scene.setAttribute("communityCount", analytics.communityCount);
  }, [depth, scene, sceneQuery.data]);

  const expand = useMutation({
    mutationFn: (entityId: string) => readGraphNeighbors(entityId, {
      depth: 1,
      entityTypes: activeEntityTypes,
      relationTypes: activeRelationTypes,
      minimumConfidence,
      limit: policy.maxNodes,
    }),
    onSuccess: (snapshot, entityId) => {
      mergeGraphScene(scene, snapshot, { anchorId: entityId });
      const analytics = analyzeGraphScene(scene);
      scene.setAttribute("communityCount", analytics.communityCount);
    },
  });

  const search = useMutation({
    mutationFn: () => searchGraphEntities(searchText, activeEntityTypes, 12),
  });

  const openLocalGraph = useCallback((entityId: string) => {
    setMode("LOCAL");
    setRootEntityId(entityId);
    setSelectedEdge(null);
    setSelectedNode(entityId);
    setInspectorOpen(true);
    search.reset();
  }, [search]);

  const handleExpand = useCallback((entityId: string) => {
    expand.mutate(entityId);
  }, [expand]);

  const relationNames = (() => {
    if (!selectedEdge || !scene.hasEdge(selectedEdge)) return {};
    const [source, target] = scene.extremities(selectedEdge);
    return {
      sourceName: scene.getNodeAttribute(source, "label"),
      targetName: scene.getNodeAttribute(target, "label"),
    };
  })();

  const toggle = (value: string, current: string[], change: (next: string[]) => void) => {
    change(current.includes(value) ? current.filter((item) => item !== value) : [...current, value]);
  };
  const nextGlobalLimit = globalLimitOptions.find((value) => value > globalLimit);

  return <section className="panel mt-5 overflow-hidden" aria-label="知识图谱探索窗口">
      <div className="panel-head flex-wrap">
        <div>
          <div className="flex flex-wrap items-center gap-2"><h3 className="panel-title">Knowledge Graph Explorer</h3><Badge className={mode === "LOCAL" ? "bg-[#eceeff] text-[#4d55ca]" : ""}>{mode === "LOCAL" ? `${depth}-hop Local Graph` : `全局概览 · Top ${globalLimit}`}</Badge>{Number(scene.getAttribute("communityCount") ?? 0) > 1 ? <Badge>{Number(scene.getAttribute("communityCount"))} 个社区</Badge> : null}</div>
          <p className="mt-1 text-[10px] text-[#858995]">当前 Scene：{scene.order} 个实体 · {scene.size} 条关系 · 节点大小表示重要度</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant={mode === "GLOBAL" ? "primary" : "secondary"} onClick={() => { setMode("GLOBAL"); setRootEntityId(null); }}>全局</Button>
          {[1, 2, 3].map((value) => <Button key={value} size="sm" variant={mode === "LOCAL" && depth === value ? "primary" : "secondary"} disabled={!rootEntityId} onClick={() => { setMode("LOCAL"); setDepth(value as Depth); }}>{value} 跳</Button>)}
          {mode === "GLOBAL" ? <label className="flex h-[30px] items-center gap-1.5 rounded-[9px] border border-[#deded9] bg-white px-2.5 text-[10px] font-semibold text-[#656975]">Top 实体<select className="border-0 bg-transparent text-[10px] font-semibold text-[#20212a] outline-none" aria-label="全局 Top 实体数量" value={globalLimit} onChange={(event) => setGlobalLimit(Number(event.target.value))}>{globalLimitOptions.map((value) => <option key={value} value={value}>{value}</option>)}</select></label> : null}
          <Button size="sm" variant="secondary" onClick={() => setFilterOpen((value) => !value)}><Filter className="size-3.5"/>过滤</Button>
          <Button size="sm" variant="secondary" onClick={() => setInspectorOpen((value) => !value)} aria-pressed={inspectorOpen}>{inspectorOpen ? <PanelRightClose className="size-3.5"/> : <PanelRightOpen className="size-3.5"/>}{inspectorOpen ? "收起详情" : "打开详情"}</Button>
          <Button size="sm" variant="secondary" onClick={() => sceneQuery.refetch()} disabled={sceneQuery.isFetching}><RefreshCw className={`size-3.5 ${sceneQuery.isFetching ? "animate-spin" : ""}`}/>刷新</Button>
        </div>
      </div>

      <div className="relative border-b border-[#deded9] bg-white p-3">
        <form className="mx-auto flex max-w-2xl gap-2" onSubmit={(event) => { event.preventDefault(); if (searchText.trim()) search.mutate(); }}>
          <label className="relative flex-1"><input className="field pr-9" value={searchText} onChange={(event) => setSearchText(event.target.value)} placeholder="搜索实体名称或别名，进入局部图谱" aria-label="搜索图谱实体"/><Search className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-[#858995]"/></label>
          <Button type="submit" disabled={!searchText.trim() || search.isPending}>{search.isPending ? <LoaderCircle className="size-4 animate-spin"/> : <Sparkles className="size-4"/>}进入图谱</Button>
        </form>
        {search.data ? <div className="absolute left-1/2 top-[58px] z-30 max-h-72 w-[min(620px,calc(100%-32px))] -translate-x-1/2 overflow-auto rounded-xl border border-[#deded9] bg-white p-2 shadow-xl">
          {search.data.items.length ? search.data.items.map((entity) => <button key={entity.id} type="button" className="flex w-full items-center gap-3 rounded-lg p-3 text-left hover:bg-[#f5f5f2]" onClick={() => openLocalGraph(entity.id)}><span className="size-3 rounded-full" style={{ background: entityColor(entity.type) }}/><span><strong className="block text-xs text-[#20212a]">{entity.name}</strong><small className="mt-1 block text-[10px] text-[#858995]">{ENTITY_LABELS[entity.type] ?? entity.type} · {entity.documentCount} 份来源</small></span></button>) : <p className="p-4 text-center text-xs text-[#858995]">没有找到当前身份可见的实体</p>}
        </div> : null}
      </div>

      {filterOpen ? <div className="grid gap-5 border-b border-[#deded9] bg-[#fafaf8] p-4 lg:grid-cols-[1fr_1fr_240px]">
        <fieldset><legend className="text-[10px] font-semibold text-[#656975]">实体类型</legend><div className="mt-2 flex flex-wrap gap-2">{policy.allowedEntityTypes.map((type) => <button key={type} type="button" onClick={() => toggle(type, entityTypes, setEntityTypes)} className={`rounded-full border px-2.5 py-1 text-[10px] ${activeEntityTypes.includes(type) ? "border-[#9ba0e5] bg-[#eceeff] text-[#4d55ca]" : "border-[#deded9] bg-white text-[#858995]"}`}>{ENTITY_LABELS[type] ?? type}</button>)}</div></fieldset>
        <fieldset><legend className="text-[10px] font-semibold text-[#656975]">关系类型</legend><div className="mt-2 flex flex-wrap gap-2">{policy.allowedRelationTypes.map((type) => <button key={type} type="button" onClick={() => toggle(type, relationTypes, setRelationTypes)} className={`rounded-full border px-2.5 py-1 text-[10px] ${activeRelationTypes.includes(type) ? "border-[#9ba0e5] bg-[#eceeff] text-[#4d55ca]" : "border-[#deded9] bg-white text-[#858995]"}`}>{type}</button>)}</div></fieldset>
        <label className="text-[10px] font-semibold text-[#656975]">最低置信度：{Math.round(minimumConfidence * 100)}%<input className="mt-3 w-full accent-[#4d55ca]" type="range" min={0} max={1} step={0.05} value={minimumConfidence} onChange={(event) => setMinimumConfidence(Number(event.target.value))}/><span className="mt-1 block font-normal text-[#858995]">过滤发生在授权查询层</span></label>
      </div> : null}

      {mode === "GLOBAL" ? <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#deded9] bg-[#f7f8fb] px-4 py-2.5 text-[10px] text-[#656975]">
        <span className="flex items-center gap-2"><Info className="size-3.5 text-[#6269d0]"/>全局概览只展示按来源文档数、Mention 数排序的 Top {globalLimit} 重要实体。{sceneQuery.data?.truncated ? "仍有更多授权实体未进入当前 Scene，展开节点也可能发现新邻居。" : "当前过滤条件下的授权实体已全部进入 Scene。"}</span>
        {sceneQuery.data?.truncated && nextGlobalLimit ? <Button size="sm" variant="secondary" onClick={() => setGlobalLimit(nextGlobalLimit)}>加载更多至 {nextGlobalLimit}</Button> : null}
      </div> : null}

      <div className={`grid min-w-0 ${inspectorOpen ? "min-[1100px]:grid-cols-[minmax(0,1fr)_320px]" : "grid-cols-1"}`}>
        <div className="relative min-h-[560px] min-w-0 overflow-hidden bg-[#f8f8f6]">
          {sceneQuery.isError ? <div className="absolute inset-x-4 top-4 z-20 rounded-xl bg-[#faeaea] p-4 text-xs text-[#9b4040]">{sceneQuery.error.message}</div> : null}
          {sceneQuery.isLoading ? <div className="grid min-h-[560px] place-items-center text-xs text-[#858995]"><span className="flex items-center gap-2"><LoaderCircle className="size-4 animate-spin"/>正在构建授权 Scene…</span></div> : <GraphCanvas
            graph={scene}
            revision={revision}
            hoveredNode={hoveredNode}
            selectedNode={selectedNode}
            selectedEdge={selectedEdge}
            onHoverNode={setHoveredNode}
            onSelectNode={(nodeId) => { setSelectedNode(nodeId); if (nodeId) { setSelectedEdge(null); setInspectorOpen(true); } }}
            onSelectEdge={(edgeId) => { setSelectedEdge(edgeId); if (edgeId) { setSelectedNode(null); setInspectorOpen(true); } }}
            onExpandNode={handleExpand}
          />}
          {!sceneQuery.isLoading && scene.order === 0 ? <div className="pointer-events-none absolute inset-0 grid place-items-center"><div className="text-center text-xs text-[#858995]"><Network className="mx-auto mb-3 size-8"/>当前过滤条件下没有可见实体</div></div> : null}
          {expand.isPending ? <div className="absolute bottom-4 left-1/2 z-20 -translate-x-1/2 rounded-full bg-[#20212a] px-4 py-2 text-[10px] text-white shadow-lg"><LoaderCircle className="mr-2 inline size-3 animate-spin"/>正在增量展开邻居</div> : null}
        </div>

        {inspectorOpen ? <div className="min-h-[560px] border-t border-[#deded9] bg-white min-[1100px]:border-l min-[1100px]:border-t-0" aria-label="图谱详情">
          {selectedNode ? <EntityInspector entityId={selectedNode} onClose={() => setInspectorOpen(false)} onExpand={handleExpand}/> : null}
          {selectedEdge ? <RelationInspector relationId={selectedEdge} onClose={() => setInspectorOpen(false)} {...relationNames}/> : null}
          {!selectedNode && !selectedEdge ? <div className="grid min-h-[560px] place-items-center p-8 text-center"><div><Network className="mx-auto size-8 text-[#a3a6af]"/><h4 className="mt-4 text-xs font-semibold text-[#20212a]">选择实体或关系</h4><p className="mt-2 text-[10px] leading-5 text-[#858995]">详情、别名、来源文档和 Provenance 将固定显示在当前图谱窗口右侧。</p></div></div> : null}
        </div> : null}
      </div>
    </section>;
}
