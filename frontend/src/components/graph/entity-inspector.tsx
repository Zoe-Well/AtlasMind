"use client";

import { useQuery } from "@tanstack/react-query";
import { ExternalLink, LoaderCircle, Network, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { readGraphEntity } from "@/lib/api/client";
import { ENTITY_LABELS } from "./graph-style";

interface Props {
  entityId: string | null;
  onClose: () => void;
  onExpand: (entityId: string) => void;
}

export function EntityInspector({ entityId, onClose, onExpand }: Props) {
  const entity = useQuery({
    queryKey: ["graph-entity", entityId],
    queryFn: () => readGraphEntity(entityId!),
    enabled: Boolean(entityId),
  });

  if (!entityId) return null;

  return <aside className="flex h-full min-h-[560px] flex-col bg-white" aria-label="实体详情">
    <header className="flex items-start justify-between gap-3 border-b border-[#deded9] px-5 py-4">
      <div className="min-w-0"><h3 className="truncate text-sm font-semibold text-[#20212a]">{entity.data?.name ?? "实体详情"}</h3><p className="mt-1 text-[10px] leading-5 text-[#858995]">实体信息来自当前身份可访问的活动文档</p></div>
      <Button variant="ghost" size="icon" className="size-8 shrink-0" onClick={onClose} aria-label="关闭"><X className="size-4"/></Button>
    </header>
    <div className="min-h-0 flex-1 overflow-auto p-5">
    {entity.isLoading ? <div className="flex items-center gap-2 text-xs text-[#858995]"><LoaderCircle className="size-4 animate-spin"/>正在读取实体…</div> : null}
    {entity.isError ? <p role="alert" className="rounded-lg bg-[#faeaea] p-3 text-xs text-[#9b4040]">{entity.error.message}</p> : null}
    {entity.data ? <div>
      <div className="flex flex-wrap items-center gap-2">
        <Badge className="bg-[#eceeff] text-[#4d55ca]">{ENTITY_LABELS[entity.data.type] ?? entity.data.type}</Badge>
        <Badge>{entity.data.degree} 条授权关系</Badge>
        <Badge>{entity.data.documentCount} 份来源文档</Badge>
      </div>

      <section className="mt-6">
        <h3 className="text-xs font-semibold text-[#20212a]">别名</h3>
        <div className="mt-3 flex flex-wrap gap-2">
          {entity.data.aliases.length ? entity.data.aliases.map((alias) => <span key={alias} className="rounded-full bg-[#f1f1ed] px-2.5 py-1 text-[10px] text-[#656975]">{alias}</span>) : <span className="text-[10px] text-[#858995]">没有记录其他别名</span>}
        </div>
      </section>

      {Object.keys(entity.data.properties).length ? <section className="mt-6">
        <h3 className="text-xs font-semibold text-[#20212a]">属性</h3>
        <dl className="mt-3 grid gap-2 rounded-xl bg-[#f7f7f4] p-4 text-[10px]">
          {Object.entries(entity.data.properties).map(([key, value]) => <div key={key} className="flex justify-between gap-4"><dt className="text-[#858995]">{key}</dt><dd className="text-right text-[#20212a]">{String(value)}</dd></div>)}
        </dl>
      </section> : null}

      <section className="mt-6">
        <h3 className="text-xs font-semibold text-[#20212a]">来源与 Provenance</h3>
        <div className="mt-3 grid gap-3">
          {entity.data.sourceDocuments.map((source) => <article key={`${source.chunkId}-${source.locator}`} className="rounded-xl border border-[#deded9] p-4">
            <div className="flex items-start justify-between gap-4">
              <div><strong className="text-[11px] text-[#20212a]">{source.documentTitle}</strong><p className="mt-1 text-[10px] text-[#858995]">{source.locator} · 置信度 {Math.round(source.confidence * 100)}%</p></div>
              <a href={`/knowledge?documentId=${encodeURIComponent(source.documentId)}&chunkId=${encodeURIComponent(source.chunkId)}`} className="inline-flex items-center gap-1 text-[10px] font-semibold text-[#4d55ca]"><ExternalLink className="size-3"/>查看原文</a>
            </div>
            <p className="mt-3 text-[10px] text-[#656975]">文中表达：{source.surface}</p>
          </article>)}
        </div>
      </section>
    </div> : null}
    </div>
    <footer className="border-t border-[#deded9] p-4"><Button className="w-full" onClick={() => onExpand(entityId)}><Network className="size-4"/>展开一跳邻居</Button></footer>
  </aside>;
}
