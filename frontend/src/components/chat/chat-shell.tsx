"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, BookOpen, Check, ChevronDown, CircleAlert, FileText, LoaderCircle, Paperclip, Search, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { RunStatus } from "@/components/runs/run-status";
import { RetrievalActivityTimeline } from "@/components/runs/retrieval-activity-timeline";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { atlasEventTypes, initialAgentStreamState, parseAgentEvent, reduceAgentEvent } from "@/lib/agent-events";
import { createAgentRun, type AgentMode, type AgentRun, type GraphPath } from "@/lib/api/client";

const formSchema=z.object({query:z.string().trim().min(1,"请输入问题").max(16_000,"问题内容过长"),mode:z.enum(["AUTO","SIMPLE","MULTI_SOURCE","GRAPH"])});
type FormValues=z.infer<typeof formSchema>;
const terminalStates=new Set<AgentRun["state"]>(["COMPLETED","PARTIAL","FAILED","TIMED_OUT","CANCELLED"]);
const subscribe=()=>()=>undefined;
const clientSnapshot=()=>true;
const serverSnapshot=()=>false;
const graphPathText=(path:GraphPath)=>path.entities.reduce((text,entity,index)=>{
  if(index===0)return entity;
  const relation=path.relations[index-1];
  return path.directions[index-1]!==false
    ? `${text} —${relation}→ ${entity}`
    : `${text} ←${relation}— ${entity}`;
},"");

export interface ChatShellProps{mode:"local"|"oidc";onSubmit?:(query:string)=>Promise<void>}

export function ChatShell({mode,onSubmit}:ChatShellProps){
  const queryClient=useQueryClient();
  const hydrated=useSyncExternalStore(subscribe,clientSnapshot,serverSnapshot);
  const [question,setQuestion]=useState<string|null>(null);
  const [run,setRun]=useState<AgentRun|null>(null);
  const [agentStream,setAgentStream]=useState(initialAgentStreamState);
  const [streamError,setStreamError]=useState<string|null>(null);
  const {register,handleSubmit,reset,formState:{errors}}=useForm<FormValues>({resolver:zodResolver(formSchema),defaultValues:{query:"",mode:"AUTO"}});
  const mutation=useMutation({
    mutationFn:async({query,mode:runMode}:FormValues)=>{if(onSubmit){await onSubmit(query);return null}return createAgentRun(query,runMode as AgentMode)},
    onSuccess:(created,values)=>{setQuestion(values.query);setStreamError(null);setAgentStream(initialAgentStreamState);if(created)setRun(created);void queryClient.invalidateQueries({queryKey:["agent-runs"]});reset()},
  });
  const runId=run?.id,runState=run?.state;
  useEffect(()=>{
    if(!runId||!runState||terminalStates.has(runState)||onSubmit)return;
    const source=new EventSource(`/api/agent-runs/${encodeURIComponent(runId)}/events`);
    const receive=(message:MessageEvent<string>)=>{try{
      const event=parseAgentEvent(JSON.parse(message.data));
      setAgentStream(previous=>reduceAgentEvent(previous,event));
      if(event.type==="STATE_SNAPSHOT")setRun((event as unknown as {snapshot:AgentRun}).snapshot);
      if(event.type==="RUN_FINISHED"||event.type==="RUN_ERROR"){source.close();void queryClient.invalidateQueries({queryKey:["agent-runs"]})}
    }catch{setStreamError("运行事件格式异常，已停止实时更新。");source.close()}};
    for(const type of atlasEventTypes)source.addEventListener(type,receive as EventListener);
    source.onopen=()=>setStreamError(null);
    source.onerror=()=>setStreamError("实时连接暂时中断，正在自动恢复…");
    return()=>source.close();
  },[runId,runState,onSubmit,queryClient]);
  const citations=agentStream.citations.length?agentStream.citations:(run?.answer?.citations??[]);
  const answerText=agentStream.output||run?.answer?.text;

  return <div className="min-h-screen">
    <header className="page-topbar">
      <div><p className="mb-1 text-[10px] text-[#858995]">智能问答</p><h1 className="page-title">企业知识助手</h1></div>
      <div className="flex items-center gap-2">
        <span className="inline-flex min-h-8 items-center gap-2 rounded-full border border-[#deded9] bg-white px-3 text-[11px] text-[#555964]"><span className="size-1.5 rounded-full bg-[#287552]"/>{mode==="local"?"本地真实数据":"企业知识库"}<ChevronDown className="size-3"/></span>
      </div>
    </header>
    <div className="grid min-h-[calc(100vh-72px)] grid-cols-[minmax(0,1fr)_380px] max-[1120px]:grid-cols-[minmax(0,1fr)_330px] max-[900px]:grid-cols-1">
      <section className="relative min-w-0 px-[50px] pb-[178px] pt-9 max-[1120px]:px-7 max-[900px]:px-5">
        {!question&&!run?<div className="mx-auto grid min-h-[52vh] max-w-2xl place-items-center text-center">
          <div><span className="mx-auto grid size-12 place-items-center rounded-xl bg-[#eceeff] text-[#4d55ca]"><Sparkles className="size-5"/></span><h2 className="mt-5 text-[25px] font-semibold tracking-[-.025em] text-[#20212a]">今天想了解什么？</h2><p className="mx-auto mt-2 max-w-lg text-xs leading-6 text-[#858995]">我会从当前身份有权访问的企业知识中寻找答案，并在右侧列出支持结论的来源。</p><div className="mt-6 flex flex-wrap justify-center gap-2"><span className="rounded-full border border-[#deded9] bg-white px-3 py-2 text-[11px]">退款申请需要哪些材料？</span><span className="rounded-full border border-[#deded9] bg-white px-3 py-2 text-[11px]">本季度政策有哪些变化？</span></div></div>
        </div>:null}
        {question?<><p className="mb-[18px] text-center text-[10px] text-[#858995]">刚刚</p><div className="ml-auto w-[min(560px,82%)] rounded-2xl bg-[#f0f1ff] px-5 py-4 leading-7 text-[#383b46]">{question}</div></>:null}
        {run?<article className="mt-9">
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
            <Link href={`/runs/${run.id}`} className="mt-6 block text-[11px] font-semibold text-[#4d55ca] hover:underline">查看运行过程与关联 ID</Link>
          </div>
        </article>:null}
        {streamError?<p role="alert" className="mt-4 text-xs text-[#9b4040]">{streamError}</p>:null}
        <form onSubmit={handleSubmit((values)=>mutation.mutate(values))} className="fixed bottom-5 left-[calc(276px+50px)] right-[430px] z-20 rounded-2xl border border-[#deded9] bg-white p-2.5 shadow-[0_8px_28px_rgba(28,31,42,.08)] max-[1180px]:left-[calc(230px+28px)] max-[1120px]:right-[360px] max-[900px]:absolute max-[900px]:bottom-5 max-[900px]:left-5 max-[900px]:right-5">
          <label htmlFor="knowledge-query" className="sr-only">向企业知识库提问</label>
          <textarea id="knowledge-query" rows={2} placeholder="向企业知识库提问，按 Enter 发送…" className="block max-h-40 min-h-[54px] w-full resize-none border-0 bg-transparent px-2 py-2 text-[13px] leading-6 outline-none" {...register("query")}/>
          <div className="flex items-center justify-between border-t border-[#eeeeea] pt-2">
            <div className="flex items-center gap-1"><button type="button" className="grid size-8 place-items-center rounded-lg text-[#858995] hover:bg-[#f0f0ec]" aria-label="附件功能待接入"><Paperclip className="size-4"/></button><select aria-label="任务模式" className="h-8 rounded-lg border-0 bg-transparent px-2 text-[10px] text-[#656975] outline-none" {...register("mode")}><option value="AUTO">自动策略</option><option value="SIMPLE">简单问答</option><option value="MULTI_SOURCE">多源分析</option><option value="GRAPH">图谱检索</option></select></div>
            <Button type="submit" size="icon" className="size-8 rounded-lg" disabled={!hydrated||mutation.isPending} aria-label="发送问题">{mutation.isPending?<LoaderCircle className="size-4 animate-spin"/>:<ArrowUp className="size-4"/>}</Button>
          </div>
          {errors.query||mutation.error?<p role="alert" className="absolute -bottom-5 left-1 text-[10px] text-[#9b4040]">{errors.query?.message??mutation.error?.message}</p>:null}
        </form>
      </section>
      <aside className="border-l border-[#deded9] bg-[#fafaf8] max-[900px]:border-l-0 max-[900px]:border-t">
        <header className="flex min-h-[58px] items-center justify-between border-b border-[#deded9] px-[18px]"><h2 className="flex items-center gap-2 text-[13px] font-semibold text-[#20212a]"><BookOpen className="size-4 text-[#4d55ca]"/>证据来源</h2><Badge>{citations.length} 条</Badge></header>
        <div className="grid gap-3 p-[18px]">
          {citations.map((citation,index)=><article key={citation.id} className="rounded-xl border border-[#deded9] bg-white p-4">
            <div className="flex items-start gap-3"><span className="grid size-8 shrink-0 place-items-center rounded-lg bg-[#f0f1ff] text-[#4d55ca]"><FileText className="size-4"/></span><div className="min-w-0"><p className="truncate text-xs font-semibold text-[#20212a]">{citation.source.title}</p><p className="mt-1 text-[10px] text-[#858995]">来源 {index+1} · {citation.source.version}</p></div></div>
            <p className="mt-3 text-[10px] font-semibold text-[#656975]">{citation.source.locator}</p><p className="mt-2 line-clamp-4 text-[11px] leading-5 text-[#757985]">{citation.source.excerpt??"该段内容支持回答中的相关结论。"}</p>
          </article>)}
          {!citations.length?<div className="empty-state min-h-[320px]"><div><Search className="mx-auto size-8 text-[#b4b6bd]"/><p className="mt-3 text-xs">回答生成后，这里将展示<br/>文档、版本、位置和段落摘要</p><p className="mt-3 text-[10px] text-[#a0a3ab]">证据面板只读，不支持点击跳转</p></div></div>:null}
        </div>
      </aside>
    </div>
  </div>;
}
