import { Check, CircleAlert, LoaderCircle, Minus, X } from "lucide-react";

import type { RetrievalActivity } from "@/lib/agent-events";

const strategyLabels: Record<string, string> = {
  query_rewrite: "查询改写",
  multi_query: "多查询扩展",
  hyde: "HyDE 增强",
  self_query: "元数据条件",
  vector: "向量检索",
  bm25: "关键词检索",
  graph: "知识图谱检索",
  fusion: "RRF 融合",
  rerank: "候选重排",
};

const stageLabels: Record<RetrievalActivity["stage"], string> = {
  PLAN: "检索计划",
  QUERY_PROCESSING: "查询处理",
  RETRIEVAL: "并行召回",
  FUSION: "候选融合",
  RERANK: "候选重排",
  EVIDENCE: "证据构建",
  WORKFLOW: "检索流程",
};

const metricLabels: Record<string, string> = {
  durationMs: "耗时",
  candidateCount: "候选",
  inputCandidateCount: "输入",
  outputCandidateCount: "输出",
  evidenceCount: "证据",
  graphPathCount: "关系路径",
  graphEvidenceCount: "图谱证据",
  queryVariantCount: "查询表达",
  metadataFilterCount: "元数据条件",
  embeddingCallCount: "Embedding 调用",
  retrievalCallCount: "检索调用",
  estimatedLlmCalls: "预计模型调用",
  estimatedEmbeddingCalls: "预计 Embedding 调用",
  estimatedRetrievalCalls: "预计检索调用",
  estimatedQueryVariants: "预计查询表达",
};

function metricText(name: string, value: number) {
  return name === "durationMs" ? `${value} ms` : `${value}`;
}

function ActivityIcon({ activity }: { activity: RetrievalActivity }) {
  if (activity.status === "RUNNING") return <LoaderCircle className="size-3 animate-spin" />;
  if (activity.status === "FAILED") return <X className="size-3" />;
  if (activity.status === "DEGRADED") return <CircleAlert className="size-3" />;
  if (activity.status === "SKIPPED" || activity.status === "EMPTY") return <Minus className="size-3" />;
  return <Check className="size-3" />;
}

export function RetrievalActivityTimeline({
  activities,
  compact = false,
}: {
  activities: RetrievalActivity[];
  compact?: boolean;
}) {
  if (!activities.length) return null;
  const visible = compact ? activities.slice(-8) : activities;

  return <ol className="grid gap-2">
    {visible.map((activity) => {
      const tone = activity.status === "FAILED"
        ? "bg-[#faeaea] text-[#9b4040]"
        : activity.status === "DEGRADED"
          ? "bg-[#fbf2df] text-[#8a5a17]"
          : activity.status === "RUNNING"
            ? "bg-[#eceeff] text-[#4d55ca]"
            : "bg-[#e8f5ee] text-[#287552]";
      const metrics = Object.entries(activity.metrics)
        .filter(([name]) => name !== "rankingCount")
        .slice(0, compact ? 3 : 6);

      return <li key={activity.id} className="grid grid-cols-[22px_minmax(0,1fr)] gap-2.5 rounded-lg bg-white px-3 py-2.5">
        <span className={`mt-0.5 grid size-[22px] place-items-center rounded-full ${tone}`}>
          <ActivityIcon activity={activity} />
        </span>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <strong className="text-[10px] text-[#535761]">
              {activity.strategyId ? strategyLabels[activity.strategyId] : stageLabels[activity.stage]}
            </strong>
            <span className="text-[9px] text-[#a0a3ac]">{stageLabels[activity.stage]}</span>
          </div>
          <p className="mt-0.5 text-[10px] leading-5 text-[#737783]">{activity.summary}</p>
          {activity.selectedStrategies.length ? <div className="mt-2 flex flex-wrap gap-1.5">
            {activity.selectedStrategies.map((strategy) => <span key={strategy} className="rounded-full bg-[#f0f1ff] px-2 py-0.5 text-[9px] text-[#4d55ca]">
              {strategyLabels[strategy] ?? strategy}
            </span>)}
          </div> : null}
          {metrics.length ? <dl className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[9px] text-[#858995]">
            {metrics.map(([name, value]) => <div key={name} className="flex gap-1">
              <dt>{metricLabels[name] ?? name}</dt><dd className="font-semibold text-[#656975]">{metricText(name, value)}</dd>
            </div>)}
          </dl> : null}
        </div>
      </li>;
    })}
  </ol>;
}
