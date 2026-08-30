"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  CircleAlert,
  LoaderCircle,
  RefreshCw,
  Settings2,
  SlidersHorizontal,
} from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { OverlayPanel } from "@/components/ui/overlay-panel";
import {
  readRagPolicy,
  readRagStrategies,
  updateRagPolicy,
  type RagPolicy,
} from "@/lib/api/client";

const STRATEGY_LABELS: Record<string, { name: string; description: string }> = {
  query_rewrite: { name: "Query Rewrite", description: "在检索前生成一个保留原意的规范查询" },
  multi_query: { name: "Multi-Query", description: "生成有界的替代表达；默认与 HyDE 互斥" },
  hyde: { name: "HyDE", description: "生成仅供向量召回使用的假设文档，不作为证据" },
  self_query: { name: "Self-Query", description: "从问题中抽取白名单元数据等值过滤" },
  vector: { name: "Vector", description: "使用 pgvector 召回授权范围内的活动 Chunk" },
  bm25: { name: "BM25", description: "使用 PostgreSQL 关键词检索召回活动 Chunk" },
  graph: { name: "GraphRAG", description: "实体链接与有界遍历后回溯原始 Chunk" },
  fusion: { name: "Fusion", description: "多路召回后执行确定性 RRF 融合" },
  rerank: { name: "Rerank", description: "仅在候选集非空时执行有界重排" },
};

const STAGE_LABELS: Record<string, string> = {
  QUERY_PROCESSING: "Query Processing",
  RETRIEVAL: "Retrieval",
  FUSION: "Fusion",
  RERANK: "Rerank",
};

export function RagStrategyWorkbench() {
  const queryClient = useQueryClient();
  const policy = useQuery({ queryKey: ["rag-policy"], queryFn: readRagPolicy });
  const catalog = useQuery({ queryKey: ["rag-strategies"], queryFn: readRagStrategies });
  const [editorOpen, setEditorOpen] = useState(false);
  const [draft, setDraft] = useState<RagPolicy | null>(null);

  const save = useMutation({
    mutationFn: () => {
      if (!draft) throw new Error("RAG 策略尚未加载完成。");
      return updateRagPolicy({ strategies: draft.strategies, budget: draft.budget });
    },
    onSuccess: (next) => {
      queryClient.setQueryData(["rag-policy"], next);
      void queryClient.invalidateQueries({ queryKey: ["rag-strategies"] });
      setEditorOpen(false);
    },
  });

  const enabledCount = Object.values(policy.data?.strategies ?? {}).filter(
    (item) => item.enabled,
  ).length;
  const enabledRetrievers = ["vector", "bm25", "graph"].filter(
    (id) => draft?.strategies[id]?.enabled,
  );
  const invalidFusion =
    enabledRetrievers.length > 1 && draft?.strategies.fusion?.enabled === false;
  const noRetriever = enabledRetrievers.length === 0;
  const grouped = useMemo(() => {
    const result = new Map<string, NonNullable<typeof catalog.data>["strategies"]>();
    for (const item of catalog.data?.strategies ?? []) {
      result.set(item.stage, [...(result.get(item.stage) ?? []), item]);
    }
    return result;
  }, [catalog.data]);

  const refresh = () => {
    void policy.refetch();
    void catalog.refetch();
  };

  const openEditor = () => {
    if (!policy.data) return;
    setDraft(policy.data);
    save.reset();
    setEditorOpen(true);
  };

  const toggle = (strategyId: string) => {
    setDraft((current) => {
      if (!current || !current.strategies[strategyId]) return current;
      const enabling = !current.strategies[strategyId].enabled;
      const strategies = {
        ...current.strategies,
        [strategyId]: { ...current.strategies[strategyId], enabled: enabling },
      };
      if (enabling && strategyId === "multi_query" && strategies.hyde) {
        strategies.hyde = { ...strategies.hyde, enabled: false };
      }
      if (enabling && strategyId === "hyde" && strategies.multi_query) {
        strategies.multi_query = { ...strategies.multi_query, enabled: false };
      }
      return { ...current, strategies };
    });
  };

  const updateBudget = (key: keyof RagPolicy["budget"], value: number) => {
    setDraft((current) =>
      current ? { ...current, budget: { ...current.budget, [key]: value } } : current,
    );
  };

  const loading = policy.isFetching || catalog.isFetching;

  return <div>
    <header className="page-topbar"><div><p className="mb-1 text-[10px] text-[#858995]">检索配置</p><h1 className="page-title">RAG 策略</h1></div><div className="flex gap-2"><Button variant="secondary" size="sm" onClick={refresh}><RefreshCw className="size-3.5"/>刷新</Button>{policy.data?.canManage ? <Button size="sm" onClick={openEditor}><Settings2 className="size-3.5"/>配置策略</Button> : null}</div></header>
    <div className="page-content">
      <div className="flex flex-wrap items-end justify-between gap-5"><div><p className="eyebrow">Retrieval workflow</p><h2 className="heading-xl">固定阶段、按计划执行</h2><p className="mt-2 max-w-3xl text-xs leading-6 text-[#858995]">外层 Agent 只调用 knowledge_search。Planner 只生成结构化 Plan；LangGraph Runtime 按 Query Processing → Retrieval → Fusion → Rerank 的固定顺序执行内部 Strategy。</p></div>{policy.data ? <Badge className="bg-[#e8f5ee] text-[#287552]"><Check className="mr-1 size-3"/>策略 v{policy.data.version}</Badge> : null}</div>

      <div className="mt-7 grid grid-cols-4 gap-4 max-[1000px]:grid-cols-2"><div className="panel p-5"><p className="text-[10px] text-[#858995]">内部 Strategy</p><strong className="mt-3 block text-2xl text-[#20212a]">{catalog.data?.strategies.length ?? "—"}</strong></div><div className="panel p-5"><p className="text-[10px] text-[#858995]">当前启用</p><strong className="mt-3 block text-2xl text-[#20212a]">{policy.data ? enabledCount : "—"}</strong></div><div className="panel p-5"><p className="text-[10px] text-[#858995]">查询总预算</p><strong className="mt-3 block text-sm text-[#20212a]">{policy.data ? `${policy.data.budget.totalTimeoutMs} ms` : "—"}</strong></div><div className="panel p-5"><p className="text-[10px] text-[#858995]">Agent Tool</p><strong className="mt-3 block font-mono text-xs text-[#4d55ca]">knowledge_search</strong></div></div>

      {loading ? <div className="mt-6 flex items-center gap-2 text-xs text-[#858995]"><LoaderCircle className="size-4 animate-spin"/>正在读取当前策略…</div> : null}
      {policy.isError || catalog.isError ? <div className="mt-6 rounded-xl bg-[#faeaea] p-4 text-xs text-[#9b4040]">{policy.error?.message ?? catalog.error?.message}</div> : null}

      {["QUERY_PROCESSING", "RETRIEVAL", "FUSION", "RERANK"].map((stage) => <section key={stage} className="panel mt-6"><div className="panel-head"><div><h3 className="panel-title">{STAGE_LABELS[stage]}</h3><p className="mt-1 text-[10px] text-[#858995]">阶段顺序由 Runtime 固定，Planner 无权调整</p></div><Badge>{grouped.get(stage)?.filter((item) => item.enabled).length ?? 0} 启用</Badge></div><div>{(grouped.get(stage) ?? []).map((item) => { const labels = STRATEGY_LABELS[item.id] ?? { name: item.id, description: item.description }; return <div key={item.id} className="grid grid-cols-[1fr_auto_auto] items-center gap-4 border-t border-[#ecece8] px-[18px] py-4 first:border-t-0"><div className="flex items-center gap-3"><span className="grid size-9 place-items-center rounded-lg bg-[#f0f1ff] text-[#4d55ca]"><SlidersHorizontal className="size-4"/></span><span><strong className="block text-xs text-[#20212a]">{labels.name}</strong><small className="mt-1 block text-[10px] leading-5 text-[#858995]">{labels.description}</small></span></div><Badge>{item.stage}</Badge><span className={`text-[10px] font-semibold ${item.enabled ? "text-[#287552]" : "text-[#858995]"}`}>{item.enabled ? "已启用" : "已关闭"}</span></div>; })}</div></section>)}
    </div>

    <OverlayPanel open={editorOpen} onOpenChange={setEditorOpen} title="配置 Advanced RAG" description="开关只决定 Planner 可选择的 Strategy；Runtime 始终负责顺序、预算和异常降级。" wide footer={<><Button variant="secondary" onClick={() => setEditorOpen(false)}>取消</Button><Button onClick={() => save.mutate()} disabled={!draft || noRetriever || invalidFusion || save.isPending}>{save.isPending ? <LoaderCircle className="size-4 animate-spin"/> : null}保存新版本</Button></>}>
      <div className="grid grid-cols-2 gap-3 max-[800px]:grid-cols-1">{catalog.data?.strategies.map((item) => { const checked = draft?.strategies[item.id]?.enabled ?? false; const labels = STRATEGY_LABELS[item.id] ?? { name: item.id, description: item.description }; return <label key={item.id} className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 ${checked ? "border-[#777edc] bg-[#f2f2ff]" : "border-[#deded9] bg-white"}`}><input type="checkbox" className="mt-0.5 size-4 accent-[#4d55ca]" checked={checked} onChange={() => toggle(item.id)}/><span><span className="block text-xs font-semibold text-[#20212a]">{labels.name}</span><span className="mt-1 block text-[10px] leading-5 text-[#858995]">{labels.description}</span>{item.conflictsWith.length ? <span className="mt-1 block text-[9px] text-[#8a5a17]">与 {item.conflictsWith.join("、")} 互斥</span> : null}</span></label>; })}</div>

      <div className="mt-6 grid grid-cols-3 gap-4 max-[800px]:grid-cols-1"><label className="grid gap-2 text-xs font-semibold">总超时（ms）<input className="field" type="number" min={500} max={8000} value={draft?.budget.totalTimeoutMs ?? 8000} onChange={(event) => updateBudget("totalTimeoutMs", Number(event.target.value))}/></label><label className="grid gap-2 text-xs font-semibold">最大 LLM 调用<input className="field" type="number" min={1} max={6} value={draft?.budget.maxLlmCalls ?? 4} onChange={(event) => updateBudget("maxLlmCalls", Number(event.target.value))}/></label><label className="grid gap-2 text-xs font-semibold">最大 Query Variants<input className="field" type="number" min={1} max={5} value={draft?.budget.maxQueryVariants ?? 3} onChange={(event) => updateBudget("maxQueryVariants", Number(event.target.value))}/></label></div>
      {noRetriever ? <p className="mt-4 flex items-center gap-2 text-[11px] text-[#9b4040]"><CircleAlert className="size-4"/>至少启用 Vector、BM25、GraphRAG 中的一种 Retriever。</p> : null}
      {invalidFusion ? <p className="mt-4 flex items-center gap-2 text-[11px] text-[#9b4040]"><CircleAlert className="size-4"/>启用多路 Retriever 时必须启用 Fusion。</p> : null}
      {save.isError ? <p className="mt-4 text-[11px] text-[#9b4040]">{save.error.message}</p> : null}
      <p className="mt-5 rounded-lg bg-[#f5f5f2] p-3 text-[10px] leading-5 text-[#656975]">Rewrite、Self-Query、Multi-Query 和 HyDE 即使内部调用 LLM，也不会注册为 Agent Tool。GraphRAG 仅扩大 Chunk 召回，最终证据仍来自原始文档 Chunk。</p>
    </OverlayPanel>
  </div>;
}
