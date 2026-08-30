"use client";

import { useQuery } from "@tanstack/react-query";
import { ExternalLink, LoaderCircle, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { readGraphRelation } from "@/lib/api/client";

interface Props {
  relationId: string | null;
  sourceName?: string;
  targetName?: string;
  onClose: () => void;
}

export function RelationInspector({ relationId, sourceName, targetName, onClose }: Props) {
  const relation = useQuery({
    queryKey: ["graph-relation", relationId],
    queryFn: () => readGraphRelation(relationId!),
    enabled: Boolean(relationId),
  });

  if (!relationId) return null;

  return <aside className="flex h-full min-h-[560px] flex-col bg-white" aria-label="关系详情">
    <header className="flex items-start justify-between gap-3 border-b border-[#deded9] px-5 py-4">
      <div><h3 className="text-sm font-semibold text-[#20212a]">关系与原始证据</h3><p className="mt-1 text-[10px] leading-5 text-[#858995]">关系只有保留授权 provenance 后才进入辅助检索图谱</p></div>
      <Button variant="ghost" size="icon" className="size-8 shrink-0" onClick={onClose} aria-label="关闭"><X className="size-4"/></Button>
    </header>
    <div className="min-h-0 flex-1 overflow-auto p-5">
    {relation.isLoading ? <div className="flex items-center gap-2 text-xs text-[#858995]"><LoaderCircle className="size-4 animate-spin"/>正在读取关系证据…</div> : null}
    {relation.isError ? <p role="alert" className="rounded-lg bg-[#faeaea] p-3 text-xs text-[#9b4040]">{relation.error.message}</p> : null}
    {relation.data ? <div>
      <div className="rounded-xl bg-[#f3f3ef] p-4">
        <p className="text-xs font-semibold text-[#20212a]">{sourceName ?? relation.data.source} <span className="text-[#4d55ca]">—{relation.data.type}→</span> {targetName ?? relation.data.target}</p>
        <div className="mt-3 flex gap-2"><Badge>置信度 {Math.round(relation.data.confidence * 100)}%</Badge><Badge>{relation.data.evidence.length} 条授权证据</Badge></div>
      </div>
      <section className="mt-6">
        <h3 className="text-xs font-semibold text-[#20212a]">Provenance</h3>
        <div className="mt-3 grid gap-3">
          {relation.data.evidence.map((source) => <article key={`${source.chunkId}-${source.locator}`} className="rounded-xl border border-[#deded9] p-4">
            <div className="flex items-start justify-between gap-4">
              <div><strong className="text-[11px] text-[#20212a]">{source.documentTitle}</strong><p className="mt-1 text-[10px] text-[#858995]">{source.locator}</p></div>
              <a href={`/knowledge?documentId=${encodeURIComponent(source.documentId)}&chunkId=${encodeURIComponent(source.chunkId)}`} className="inline-flex items-center gap-1 text-[10px] font-semibold text-[#4d55ca]"><ExternalLink className="size-3"/>查看原文</a>
            </div>
          </article>)}
        </div>
      </section>
    </div> : null}
    </div>
  </aside>;
}
