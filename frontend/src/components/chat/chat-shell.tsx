"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, BookOpen, ChevronDown, FileText, LoaderCircle, Paperclip, Search, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { ChatTurn, terminalStates } from "@/components/chat/chat-turn";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { createAgentRun, readAgentRun, readConversation, type AgentRun } from "@/lib/api/client";

const formSchema=z.object({query:z.string().trim().min(1,"请输入问题").max(16_000,"问题内容过长"),mode:z.enum(["AUTO","SIMPLE","MULTI_SOURCE","GRAPH"])});
type FormValues=z.infer<typeof formSchema>;
const subscribe=()=>()=>undefined;
const clientSnapshot=()=>true;
const serverSnapshot=()=>false;
export interface ChatShellProps{mode:"local"|"oidc";conversationId?:string;onSubmit?:(query:string)=>Promise<void>}

export function ChatShell({mode,conversationId,onSubmit}:ChatShellProps){
  const router=useRouter();
  const queryClient=useQueryClient();
  const hydrated=useSyncExternalStore(subscribe,clientSnapshot,serverSnapshot);
  const [createdRuns,setCreatedRuns]=useState<AgentRun[]>([]);
  const [submittedQuestion,setSubmittedQuestion]=useState<string|null>(null);
  const [selectedRunId,setSelectedRunId]=useState<string|null>(null);
  const history=useInfiniteQuery({
    queryKey:["conversation",conversationId],
    queryFn:({pageParam})=>readConversation(conversationId!,pageParam),
    initialPageParam:undefined as number|undefined,
    getNextPageParam:page=>page.nextBefore??undefined,
    enabled:Boolean(conversationId),retry:false,
  });
  const saved=history.data?.pages.slice().reverse().flatMap(page=>page.items)??[];
  const turns=[...new Map([...saved,...createdRuns].map(item=>[item.id,item])).values()]
    .sort((a,b)=>(a.turnIndex??0)-(b.turnIndex??0));
  const latest=turns.at(-1);
  const latestId=latest?.id;
  const endOfConversation=useRef<HTMLDivElement>(null);
  useEffect(()=>{if(latestId)endOfConversation.current?.scrollIntoView?.({block:"end"})},[latestId]);
  const liveLatest=useQuery({queryKey:["agent-runs",latest?.id],queryFn:()=>readAgentRun(latest!.id),enabled:false});
  const busy=Boolean(latest&&!terminalStates.has((liveLatest.data??latest).state));
  const selectedInitial=turns.find(item=>item.id===selectedRunId)??latest;
  const liveSelected=useQuery({queryKey:["agent-runs",selectedInitial?.id],queryFn:()=>readAgentRun(selectedInitial!.id),enabled:false});
  const selected=liveSelected.data??selectedInitial;
  const citations=selected?.answer?.citations??[];
  const {register,handleSubmit,reset,formState:{errors}}=useForm<FormValues>({resolver:zodResolver(formSchema),defaultValues:{query:"",mode:"AUTO"}});
  const mutation=useMutation({
    mutationFn:async({query,mode:runMode}:FormValues)=>{
      if(onSubmit){await onSubmit(query);return null}
      return createAgentRun(query,runMode,conversationId??latest?.conversationId??undefined);
    },
    onSuccess:(created,values)=>{
      setSubmittedQuestion(values.query);
      if(created){
        const turn={...created,query:created.query??values.query};
        queryClient.setQueryData(["agent-runs",created.id],turn);
        setCreatedRuns(previous=>[...previous,turn]);setSelectedRunId(created.id);
        if(!conversationId&&created.conversationId)router.replace(`/chat/${encodeURIComponent(created.conversationId)}`,{scroll:false});
      }
      void queryClient.invalidateQueries({queryKey:["conversations"]});
      void queryClient.invalidateQueries({queryKey:["conversation",conversationId]});
      void queryClient.invalidateQueries({queryKey:["agent-runs"]});reset();
    },
  });
  return <div className="min-h-screen">
    <header className="page-topbar">
      <div><p className="mb-1 text-[10px] text-[#858995]">智能问答</p><h1 className="page-title max-w-[45vw] truncate">{history.data?.pages[0].conversation.title??"企业知识助手"}</h1></div>
      <div className="flex items-center gap-2">
        <span className="inline-flex min-h-8 items-center gap-2 rounded-full border border-[#deded9] bg-white px-3 text-[11px] text-[#555964]"><span className="size-1.5 rounded-full bg-[#287552]"/>{mode==="local"?"本地真实数据":"企业知识库"}<ChevronDown className="size-3"/></span>
      </div>
    </header>
    <div className="grid min-h-[calc(100vh-72px)] grid-cols-[minmax(0,1fr)_380px] max-[1120px]:grid-cols-[minmax(0,1fr)_330px] max-[900px]:grid-cols-1">
      <section className="relative min-w-0 px-[50px] pb-[178px] pt-9 max-[1120px]:px-7 max-[900px]:px-5">
        {!conversationId&&!turns.length&&!submittedQuestion?<div className="mx-auto grid min-h-[52vh] max-w-2xl place-items-center text-center">
          <div><span className="mx-auto grid size-12 place-items-center rounded-xl bg-[#eceeff] text-[#4d55ca]"><Sparkles className="size-5"/></span><h2 className="mt-5 text-[25px] font-semibold tracking-[-.025em] text-[#20212a]">今天想了解什么？</h2><p className="mx-auto mt-2 max-w-lg text-xs leading-6 text-[#858995]">我会从当前身份有权访问的企业知识中寻找答案，并在右侧列出支持结论的来源。</p><div className="mt-6 flex flex-wrap justify-center gap-2"><span className="rounded-full border border-[#deded9] bg-white px-3 py-2 text-[11px]">退款申请需要哪些材料？</span><span className="rounded-full border border-[#deded9] bg-white px-3 py-2 text-[11px]">本季度政策有哪些变化？</span></div></div>
        </div>:null}
        {conversationId&&history.isPending?<p className="text-sm text-[#858995]">正在恢复对话…</p>:null}
        {history.error?<div role="alert" className="text-sm text-[#9b4040]">{history.error.message}<button type="button" onClick={()=>void history.refetch()} className="ml-3 underline">重试</button></div>:null}
        {history.hasNextPage?<button type="button" disabled={history.isFetchingNextPage} onClick={()=>void history.fetchNextPage()} className="mb-6 text-xs text-[#4d55ca]">{history.isFetchingNextPage?"正在加载…":"加载更早的问答"}</button>:null}
        {turns.map(item=><ChatTurn key={item.id} initialRun={item} onSelect={()=>setSelectedRunId(item.id)}/>)}
        <div ref={endOfConversation} className="scroll-mb-44"/>
        {submittedQuestion&&!turns.length?<div className="ml-auto rounded-2xl bg-[#f0f1ff] px-5 py-4">{submittedQuestion}</div>:null}
        <form onSubmit={handleSubmit((values)=>{if(!busy&&!mutation.isPending)mutation.mutate(values)})} className="fixed bottom-5 left-[calc(276px+50px)] right-[430px] z-20 rounded-2xl border border-[#deded9] bg-white p-2.5 shadow-[0_8px_28px_rgba(28,31,42,.08)] max-[1180px]:left-[calc(230px+28px)] max-[1120px]:right-[360px] max-[900px]:absolute max-[900px]:bottom-5 max-[900px]:left-5 max-[900px]:right-5">
          <label htmlFor="knowledge-query" className="sr-only">向企业知识库提问</label>
          <textarea id="knowledge-query" rows={2} placeholder="向企业知识库提问…" className="block max-h-40 min-h-[54px] w-full resize-none border-0 bg-transparent px-2 py-2 text-[13px] leading-6 outline-none" {...register("query")}/>
          <div className="flex items-center justify-between border-t border-[#eeeeea] pt-2">
            <div className="flex items-center gap-1"><button type="button" className="grid size-8 place-items-center rounded-lg text-[#858995] hover:bg-[#f0f0ec]" aria-label="附件功能待接入"><Paperclip className="size-4"/></button><select aria-label="任务模式" className="h-8 rounded-lg border-0 bg-transparent px-2 text-[10px] text-[#656975] outline-none" {...register("mode")}><option value="AUTO">自动策略</option><option value="SIMPLE">简单问答</option><option value="MULTI_SOURCE">多源分析</option><option value="GRAPH">图谱检索</option></select></div>
            <Button type="submit" size="icon" className="size-8 rounded-lg" disabled={!hydrated||mutation.isPending||busy||Boolean(conversationId&&(history.isPending||history.isError))} aria-label="发送问题">{mutation.isPending?<LoaderCircle className="size-4 animate-spin"/>:<ArrowUp className="size-4"/>}</Button>
          </div>
          {errors.query||mutation.error?<p role="alert" className="absolute -bottom-5 left-1 text-[10px] text-[#9b4040]">{errors.query?.message??mutation.error?.message}</p>:null}
        </form>
      </section>
      <aside className="border-l border-[#deded9] bg-[#fafaf8] max-[900px]:border-l-0 max-[900px]:border-t">
        <header className="flex min-h-[58px] items-center justify-between border-b border-[#deded9] px-[18px]"><h2 className="flex items-center gap-2 text-[13px] font-semibold text-[#20212a]"><BookOpen className="size-4 text-[#4d55ca]"/>证据来源</h2><Badge>{citations.length} 条</Badge></header>
        <div className="grid gap-3 p-[18px]">
          {selected?<p className="text-[10px] text-[#858995]">第 {selected.turnIndex??1} 轮问答的证据来源</p>:null}
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
