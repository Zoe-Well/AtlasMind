"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CircleAlert, LoaderCircle } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { RunStatus } from "@/components/runs/run-status";
import { RetrievalActivityTimeline } from "@/components/runs/retrieval-activity-timeline";
import { Badge } from "@/components/ui/badge";
import { atlasEventTypes, initialAgentStreamState, parseAgentEvent, reduceAgentEvent } from "@/lib/agent-events";
import { readAgentRun, type AgentRun, type GraphPath } from "@/lib/api/client";

export const terminalStates = new Set<AgentRun["state"]>(["COMPLETED","PARTIAL","FAILED","TIMED_OUT","CANCELLED"]);
const graphPathText=(path:GraphPath)=>path.entities.reduce((text,entity,index)=>{
  if(index===0)return entity;
  const relation=path.relations[index-1];
  return path.directions[index-1]!==false
    ? `${text} —${relation}→ ${entity}`
    : `${text} ←${relation}— ${entity}`;
},"");


export function ChatTurn({initialRun,onSelect}:{initialRun:AgentRun;onSelect:()=>void}) {
  const queryClient=useQueryClient();
  const live=useQuery({
    queryKey:["agent-runs",initialRun.id], queryFn:()=>readAgentRun(initialRun.id),
    initialData:initialRun,
    enabled:!terminalStates.has(initialRun.state),
    refetchInterval:query=>terminalStates.has(query.state.data?.state??initialRun.state)?false:5000,
  });
  const run=live.data;
  const [agentStream,setAgentStream]=useState(initialAgentStreamState);
  const [streamError,setStreamError]=useState<string|null>(null);
  const runId=run.id,runTerminal=terminalStates.has(run.state);
  useEffect(()=>{
    if(runTerminal)return;
    const source=new EventSource(`/api/platform/agent-runs/${encodeURIComponent(runId)}/events`);
    const receive=(message:MessageEvent<string>)=>{try{
      const event=parseAgentEvent(JSON.parse(message.data));
      setAgentStream(previous=>reduceAgentEvent(previous,event));
      if(event.type==="STATE_SNAPSHOT"){
        const snapshot=(event as unknown as {snapshot:AgentRun}).snapshot;
        if(snapshot.id===runId)queryClient.setQueryData<AgentRun>(["agent-runs",runId],previous=>({...previous,...snapshot}));
      }
      if(event.type==="RUN_FINISHED"||event.type==="RUN_ERROR"){
        setStreamError(null);source.close();
        void queryClient.invalidateQueries({queryKey:["conversations"]});
        void queryClient.invalidateQueries({queryKey:["conversation"]});
        void queryClient.invalidateQueries({queryKey:["agent-runs"]});
      }
    }catch{setStreamError("运行事件格式异常，正在通过状态查询恢复。");source.close()}};
    for(const type of atlasEventTypes)source.addEventListener(type,receive as EventListener);
    source.onopen=()=>setStreamError(null);
    source.onerror=()=>setStreamError("实时连接暂时中断，正在自动恢复…");
    return()=>source.close();
  },[runId,runTerminal,queryClient]);
  const answerText=runTerminal?run.answer?.text:(agentStream.output||run.answer?.text);
  return <section className="mb-10" aria-label={`第 ${run.turnIndex??1} 轮问答`}>
    <p className="mb-4 text-center text-[10px] text-[#858995]">{new Date(run.createdAt).toLocaleString("zh-CN")}</p>
    <div className="ml-auto w-[min(560px,82%)] whitespace-pre-wrap rounded-2xl bg-[#f0f1ff] px-5 py-4 leading-7 text-[#383b46]">{run.query??"原问题未保存，无法恢复；以下为当时保存的回答。"}</div>
        <article className="mt-9">
          <div className="flex items-center gap-2.5 text-[#20212a]"><span className="grid size-8 place-items-center rounded-[9px] bg-[#4d55ca] text-xs font-bold text-white">A</span><strong className="font-semibold">AtlasMind</strong><RunStatus state={run.state}/></div>
          <div className="ml-[42px] mt-[18px] max-w-[780px] leading-7">
            {run.state==="QUEUED"||run.state==="RUNNING"?<p className="flex items-center gap-2 text-[#858995]"><LoaderCircle className="size-4 animate-spin text-[#4d55ca]"/>Agent 正在处理，连接中断后会自动恢复…</p>:null}
            {agentStream.activities.length||agentStream.tools.length||agentStream.retrievalActivities.length?<div className="mt-4 grid gap-2 rounded-xl border border-[#deded9] bg-[#fafaf8] p-4" aria-label="Agent 实时执行过程">
              {agentStream.activities.slice(-6).map(activity=><div key={activity.id} className="flex items-start gap-2 text-[11px] leading-5 text-[#656975]">{activity.state==="RUNNING"?<LoaderCircle className="mt-1 size-3 shrink-0 animate-spin text-[#4d55ca]"/>:<Check className="mt-1 size-3 shrink-0 text-[#287552]"/>}<span>{activity.summary}</span></div>)}
              {agentStream.tools.map(tool=><details key={tool.id} className="rounded-lg bg-white px-3 py-2"><summary className="cursor-pointer text-[10px] font-semibold text-[#535761]">{tool.status==="RUNNING"?"调用中":"已调用"} · {tool.name}{typeof tool.evidenceCount==="number"?` · ${tool.evidenceCount} 条证据`:""}</summary>{tool.arguments?<pre className="mt-2 overflow-auto whitespace-pre-wrap text-[9px] leading-4 text-[#858995]">{JSON.stringify(tool.arguments,null,2)}</pre>:null}</details>)}
              {agentStream.retrievalActivities.length?<details className="rounded-lg border border-[#e5e5e0] bg-[#f5f5f1] px-3 py-2.5">
                <summary className="cursor-pointer text-[10px] font-semibold text-[#535761]">查看详细检索过程 · {agentStream.retrievalActivities.at(-1)?.summary}</summary>
                <div className="mt-3"><RetrievalActivityTimeline activities={agentStream.retrievalActivities} compact/></div>
              </details>:null}
            </div>:null}
            {answerText?<><p className="mt-5 whitespace-pre-wrap text-[14px] leading-8 text-[#343741]">{answerText}</p>{!run.answer?<p className="mt-2 text-[10px] text-[#858995]">回答生成中，引用尚在校验…</p>:null}</>:null}
            {run.answer?<><div className="mt-5 flex gap-2"><Badge className="bg-[#e8f5ee] text-[#287552]"><Check className="mr-1 size-3"/>证据 {run.answer.evidenceStatus}</Badge><Badge>置信度 {run.answer.confidence}</Badge></div>{(agentStream.graphPaths.length?agentStream.graphPaths:run.answer.graphPaths)?.length?<div className="mt-5 rounded-xl border border-[#deded9] bg-[#fafaf8] p-4"><strong className="text-xs text-[#20212a]">关系路径</strong><ul className="mt-2 grid gap-2 text-[11px] leading-5 text-[#656975]">{(agentStream.graphPaths.length?agentStream.graphPaths:(run.answer.graphPaths??[])).slice(0,5).map((path,index)=><li key={`${graphPathText(path)}-${index}`}>{graphPathText(path)}</li>)}</ul></div>:null}{run.answer.limitations?.length?<div className="mt-5 rounded-xl bg-[#fbf2df] p-4 text-xs leading-6 text-[#8a5a17]"><strong className="flex items-center gap-2"><CircleAlert className="size-4"/>限制说明</strong><ul className="mt-1 list-disc pl-5">{run.answer.limitations.map((item)=><li key={item}>{item}</li>)}</ul></div>:null}</>:null}
            {agentStream.error&&!run.failure?<div className="rounded-xl bg-[#faeaea] p-4 text-xs text-[#9b4040]">{agentStream.error.message}</div>:null}
            {run.failure?<div className="rounded-xl bg-[#faeaea] p-4 text-xs text-[#9b4040]">{run.failure.message}</div>:null}
            {run.pendingApproval?<Link href={`/approvals/${run.pendingApproval.id}`} className="mt-5 inline-flex rounded-lg bg-[#fbf2df] px-3 py-2 text-xs font-semibold text-[#8a5a17]">运行等待人工审批 · 查看详情</Link>:null}
            <button type="button" onClick={onSelect} className="mt-5 block text-xs font-semibold text-[#4d55ca]">查看本轮来源（{run.answer?.citations.length??0}）</button>
            <Link href={`/runs/${run.id}`} className="mt-6 block text-[11px] font-semibold text-[#4d55ca] hover:underline">查看本轮运行详情</Link>
          </div>
        </article>
        {streamError?<p role="alert" className="mt-4 text-xs text-[#9b4040]">{streamError}</p>:null}

    {live.error?<p role="alert" className="mt-3 text-xs text-[#9b4040]">状态查询失败，将自动重试。{live.error.message}</p>:null}
  </section>;
}
