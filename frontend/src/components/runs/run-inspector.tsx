"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, Copy, Fingerprint, LoaderCircle, RefreshCw, ShieldCheck, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { RunStatus } from "@/components/runs/run-status";
import { RetrievalActivityTimeline } from "@/components/runs/retrieval-activity-timeline";
import { Button } from "@/components/ui/button";
import {
  atlasEventTypes,
  initialAgentStreamState,
  parseAgentEvent,
  reduceAgentEvent,
  type AgentToolActivity,
} from "@/lib/agent-events";
import { readAgentRun, type AgentRun, type GraphPath, type RunStepSummary } from "@/lib/api/client";
import {
  runStateLabel,
  runStepDescription,
  runStepLabel,
  runStepStateLabel,
  runTypeDescription,
  runTypeLabel,
  shortIdentifier,
} from "@/lib/presentation";

const terminal = new Set<AgentRun["state"]>([
  "COMPLETED", "PARTIAL", "FAILED", "TIMED_OUT", "CANCELLED",
]);

const format = (value?: string | null) => value
  ? new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "medium" }).format(new Date(value))
  : "—";

const graphPathText = (path: GraphPath) => path.entities.reduce((text, entity, index) => {
  if (index === 0) return entity;
  const relation = path.relations[index - 1];
  return path.directions[index - 1] !== false
    ? `${text} —${relation}→ ${entity}`
    : `${text} ←${relation}— ${entity}`;
}, "");

function IdentifierRow({ label, value, description }: {
  label: string;
  value?: string | null;
  description: string;
}) {
  const [copied, setCopied] = useState(false);
  if (!value) return null;

  async function copy() {
    await navigator.clipboard.writeText(value!);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return <div>
    <dt className="flex items-center gap-2 text-[10px] font-semibold text-[#535761]">
      <Fingerprint className="size-3" />{label}
    </dt>
    <dd className="mt-2 flex items-start gap-2">
      <span className="min-w-0 flex-1 break-all font-mono text-[9px] text-[#656975]">{value}</span>
      <button type="button" onClick={copy} className="flex shrink-0 items-center gap-1 text-[9px] font-semibold text-[#4d55ca]" aria-label={`复制${label}`}>
        <Copy className="size-3" />{copied ? "已复制" : "复制"}
      </button>
    </dd>
    <p className="mt-2 text-[9px] leading-4 text-[#858995]">{description}</p>
  </div>;
}

function StepIcon({ step }: { step: RunStepSummary }) {
  if (step.state === "SUCCEEDED") return <Check className="size-3" />;
  if (step.state === "FAILED") return <X className="size-3" />;
  if (step.state === "RUNNING") return <LoaderCircle className="size-3 animate-spin" />;
  return <span className="text-[9px] font-semibold">{step.ordinal}</span>;
}

function RunStepTimeline({ steps }: { steps: RunStepSummary[] }) {
  if (!steps.length) {
    return <p className="rounded-xl bg-[#f5f5f1] p-4 text-[10px] leading-5 text-[#858995]">
      运行步骤尚未生成，服务开始处理后会在这里实时显示 Agent 的决策、检索和引用校验过程。
    </p>;
  }

  return <div>{steps.map((step, index) => {
    const iconTone = step.state === "FAILED"
      ? "bg-[#faeaea] text-[#9b4040]"
      : step.state === "RUNNING"
        ? "bg-[#eceeff] text-[#4d55ca]"
        : step.state === "SUCCEEDED"
          ? "bg-[#e8f5ee] text-[#287552]"
          : "bg-[#ecece8] text-[#858995]";
    const connector = index < steps.length - 1
      ? "pb-6 before:absolute before:bottom-0 before:left-[11px] before:top-6 before:w-px before:bg-[#deded9]"
      : "";

    return <div key={step.id} className={`relative grid grid-cols-[24px_1fr] gap-3 ${connector}`}>
      <span className={`relative z-10 grid size-6 place-items-center rounded-full ${iconTone}`}>
        <StepIcon step={step} />
      </span>
      <div>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <strong className="text-[11px] text-[#20212a]">{runStepLabel(step)}</strong>
          <span className="text-[9px] text-[#858995]">{runStepStateLabel(step.state)}</span>
        </div>
        <p className="mt-1 text-[10px] leading-5 text-[#858995]">{runStepDescription(step)}</p>
        {step.startedAt || step.finishedAt
          ? <p className="mt-1 text-[9px] text-[#a0a3ac]">{format(step.finishedAt ?? step.startedAt)}</p>
          : null}
      </div>
    </div>;
  })}</div>;
}

const toolLabels: Record<string, string> = {
  knowledge_search: "企业知识检索",
  query_structured_data: "业务数据查询",
};

const toolStateLabels: Record<AgentToolActivity["status"], string> = {
  RUNNING: "执行中",
  SUCCEEDED: "已完成",
  EMPTY: "未找到证据",
  FAILED: "执行失败",
};

function LiveToolActivity({ tools }: { tools: AgentToolActivity[] }) {
  if (!tools.length) return null;
  return <div className="mt-5 border-t border-[#deded9] pt-4">
    <h4 className="text-[10px] font-semibold text-[#535761]">实时能力调用</h4>
    <ul className="mt-3 grid gap-2">
      {tools.slice(-6).map((tool) => <li key={tool.id} className="rounded-xl bg-[#f5f5f1] px-3 py-2.5">
        <div className="flex items-center justify-between gap-3 text-[10px]">
          <strong className="text-[#535761]">{toolLabels[tool.name] ?? tool.name}</strong>
          <span className={tool.status === "FAILED" ? "text-[#9b4040]" : "text-[#858995]"}>
            {toolStateLabels[tool.status]}
          </span>
        </div>
        {typeof tool.evidenceCount === "number"
          ? <p className="mt-1 text-[9px] text-[#858995]">返回 {tool.evidenceCount} 条可用证据</p>
          : null}
      </li>)}
    </ul>
  </div>;
}

export function RunInspector({ runId }: { runId: string }) {
  const queryClient = useQueryClient();
  const [agentStream, setAgentStream] = useState(initialAgentStreamState);
  const query = useQuery({
    queryKey: ["agent-run", runId],
    queryFn: () => readAgentRun(runId),
    refetchInterval: current => current.state.data && terminal.has(current.state.data.state) ? false : 1500,
  });
  const run = query.data;
  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const source = new EventSource(`/api/platform/agent-runs/${encodeURIComponent(runId)}/events`);
    const receive = (message: MessageEvent<string>) => {
      try {
        const event = parseAgentEvent(JSON.parse(message.data));
        setAgentStream((previous) => reduceAgentEvent(previous, event));
        if (event.type === "STATE_SNAPSHOT") {
          queryClient.setQueryData(["agent-run", runId], (event as unknown as { snapshot: AgentRun }).snapshot);
        }
        if (event.type === "RUN_FINISHED" || event.type === "RUN_ERROR") source.close();
      } catch { source.close(); }
    };
    for (const type of atlasEventTypes) source.addEventListener(type, receive as EventListener);
    return () => source.close();
  }, [queryClient, runId]);

  return <div>
    <header className="page-topbar">
      <div className="flex items-center gap-3">
        <Link href="/runs" className="grid size-8 place-items-center rounded-lg hover:bg-[#f0f0ec]" aria-label="返回运行中心">
          <ArrowLeft className="size-4" />
        </Link>
        <div><p className="mb-1 text-[10px] text-[#858995]">Agent operations</p><h1 className="page-title">运行详情</h1></div>
      </div>
      {run ? <RunStatus state={run.state} /> : null}
    </header>

    <div className="page-content max-w-[1180px]">
      <div className="flex items-start justify-between gap-5">
        <div><p className="eyebrow">Agent run</p><h2 className="heading-xl">运行 #{shortIdentifier(runId)}</h2><p className="mt-2 text-xs leading-6 text-[#858995]">查看本次问答的处理结果和可验证信息。</p></div>
        {query.isFetching ? <span className="flex items-center gap-2 text-[10px] text-[#858995]"><LoaderCircle className="size-3 animate-spin" />同步状态</span> : null}
      </div>

      {query.isError ? <div className="mt-6 rounded-xl bg-[#faeaea] p-4 text-xs text-[#9b4040]">
        <p>{query.error.message}</p><Button className="mt-3" size="sm" variant="danger" onClick={() => query.refetch()}><RefreshCw className="size-3" />重试</Button>
      </div> : null}

      {run ? <>
        <div className="mt-7 grid grid-cols-4 gap-4 max-[900px]:grid-cols-2">
          <div className="panel p-4"><p className="text-[10px] text-[#858995]">问答类型</p><strong className="mt-2 block text-xs text-[#20212a]">{runTypeLabel(run.taskType)}</strong><p className="mt-2 text-[9px] leading-4 text-[#858995]">{runTypeDescription(run.taskType)}</p></div>
          <div className="panel p-4"><p className="text-[10px] text-[#858995]">当前状态</p><strong className="mt-2 block text-xs text-[#20212a]">{runStateLabel(run.state)}</strong></div>
          <div className="panel p-4"><p className="text-[10px] text-[#858995]">开始时间</p><strong className="mt-2 block text-[10px] text-[#20212a]">{format(run.createdAt)}</strong></div>
          <div className="panel p-4"><p className="text-[10px] text-[#858995]">完成时间</p><strong className="mt-2 block text-[10px] text-[#20212a]">{format(run.finishedAt)}</strong></div>
        </div>

        <div className="mt-6 grid grid-cols-[minmax(0,1fr)_330px] gap-5 max-[950px]:grid-cols-1">
          <section className="panel">
            <div className="panel-head"><div><h3 className="panel-title">Agent 执行过程</h3><p className="mt-1 text-[10px] text-[#858995]">展示服务端记录的真实决策、能力调用和校验步骤。</p></div></div>
            <div className="p-5">
              <RunStepTimeline steps={run.steps ?? []} />
              {agentStream.activities.length ? <div className="mt-5 border-t border-[#deded9] pt-4">
                <h4 className="text-[10px] font-semibold text-[#535761]">实时公开摘要</h4>
                <ul className="mt-3 grid gap-2 text-[10px] leading-5 text-[#858995]">
                  {agentStream.activities.slice(-8).map(item => <li key={item.id}>{item.summary}</li>)}
                </ul>
              </div> : null}
              {agentStream.retrievalActivities.length ? <div className="mt-5 border-t border-[#deded9] pt-4">
                <div className="mb-3">
                  <h4 className="text-[10px] font-semibold text-[#535761]">RAG 详细检索过程</h4>
                  <p className="mt-1 text-[9px] leading-4 text-[#858995]">展示实际采用的策略、候选数量、耗时和降级状态，不包含问题正文或模型隐藏推理。</p>
                </div>
                <RetrievalActivityTimeline activities={agentStream.retrievalActivities} />
              </div> : null}
              <LiveToolActivity tools={agentStream.tools} />
              {agentStream.error ? <div className="mt-5 rounded-xl bg-[#faeaea] p-3 text-[10px] text-[#9b4040]">
                <strong>实时执行异常</strong>
                <p className="mt-1">{agentStream.error.message}</p>
                {agentStream.error.code ? <p className="mt-1 font-mono text-[9px]">{agentStream.error.code}</p> : null}
              </div> : null}
            </div>
          </section>
          <aside className="grid content-start gap-4">
            {run.pendingApproval ? <Link href={`/approvals/${run.pendingApproval.id}`} className="flex items-center gap-2 rounded-xl bg-[#fbf2df] p-4 text-[10px] font-semibold text-[#8a5a17]"><ShieldCheck className="size-4" />等待人工审批</Link> : null}
            <details className="panel p-5"><summary className="cursor-pointer text-xs font-semibold text-[#20212a]">技术信息与问题排查</summary><p className="mt-2 text-[9px] leading-4 text-[#858995]">一般使用无需关注这些编号。反馈问题时可复制并提供给技术人员。</p><dl className="mt-5 grid gap-5"><IdentifierRow label="运行编号" value={run.id} description="本次问答的唯一编号，用于定位运行记录和反馈问题。" /><IdentifierRow label="关联编号" value={run.correlationId} description="用于关联本次问答涉及的 API 请求、审计记录和后台任务。" /><IdentifierRow label="追踪编号" value={run.traceId} description="用于在 OpenTelemetry 中查询完整服务链路。" /></dl></details>
          </aside>
        </div>

        {run.answer ? <section className="panel mt-5 p-5"><h3 className="text-xs font-semibold text-[#20212a]">回答结果</h3><p className="mt-3 whitespace-pre-wrap text-xs leading-7">{run.answer.text}</p>{run.answer.graphPaths?.length ? <div className="mt-5 border-t border-[#deded9] pt-4"><h4 className="text-[11px] font-semibold text-[#20212a]">用于回答的关系路径</h4><ul className="mt-3 grid gap-2 text-[10px] leading-5 text-[#656975]">{run.answer.graphPaths.map((path, index) => <li key={`${graphPathText(path)}-${index}`}>{graphPathText(path)}</li>)}</ul></div> : null}</section> : null}
        {run.failure ? <section className="mt-5 rounded-xl bg-[#faeaea] p-4 text-xs text-[#9b4040]"><h3 className="flex items-center gap-2 font-semibold"><X className="size-4" />处理失败</h3><p className="mt-2">{run.failure.message}</p><details className="mt-2"><summary className="cursor-pointer text-[10px] font-semibold">技术信息</summary><p className="mt-2 font-mono text-[9px]">错误代码：{run.failure.code}</p></details></section> : null}
      </> : query.isLoading ? <div className="empty-state"><LoaderCircle className="size-6 animate-spin text-[#4d55ca]" /></div> : null}
    </div>
  </div>;
}
