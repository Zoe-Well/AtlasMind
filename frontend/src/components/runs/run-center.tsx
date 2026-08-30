"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, CheckCircle2, Clock3, LoaderCircle, RefreshCw, Search, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { RunStatus } from "@/components/runs/run-status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { listAgentRuns } from "@/lib/api/client";
import { runDisplayTitle, runTypeDescription, runTypeLabel, shortIdentifier } from "@/lib/presentation";

const terminal = new Set(["COMPLETED", "PARTIAL", "FAILED", "TIMED_OUT", "CANCELLED"]);
const format = (value: string) => new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));

export function RunCenter(){
 const [search,setSearch]=useState("");
 const runs=useQuery({queryKey:["agent-runs"],queryFn:()=>listAgentRuns(100),refetchInterval:5000});
 const items=useMemo(()=>{const value=search.trim().toLowerCase();return value?runs.data?.items.filter(run=>run.id.toLowerCase().includes(value)||shortIdentifier(run.id).toLowerCase().includes(value)||run.taskType?.toLowerCase().includes(value)||runTypeLabel(run.taskType).toLowerCase().includes(value)||runDisplayTitle(run).toLowerCase().includes(value))??[]:runs.data?.items??[]},[runs.data,search]);
 const stats=[
  {label:"最近运行",value:runs.data?.total??0,icon:Activity},
  {label:"进行中",value:runs.data?.items.filter(run=>!terminal.has(run.state)).length??0,icon:Clock3},
  {label:"已完成",value:runs.data?.items.filter(run=>run.state==="COMPLETED"||run.state==="PARTIAL").length??0,icon:CheckCircle2},
  {label:"等待审批",value:runs.data?.items.filter(run=>run.state==="WAITING_APPROVAL").length??0,icon:ShieldCheck},
 ];
 return <div><header className="page-topbar"><div><p className="mb-1 text-[10px] text-[#858995]">Agent operations</p><h1 className="page-title">运行中心</h1></div><div className="flex items-center gap-2"><Badge className="bg-[#e8f5ee] text-[#287552]">真实运行记录</Badge><Button size="sm" variant="secondary" disabled={runs.isFetching} onClick={()=>runs.refetch()}><RefreshCw className={`size-3 ${runs.isFetching?"animate-spin":""}`}/>刷新</Button></div></header>
 <div className="page-content"><div><p className="eyebrow">Run center</p><h2 className="heading-xl">问答运行记录</h2><p className="mt-2 max-w-2xl text-xs leading-6 text-[#858995]">查看智能问答的处理状态、答案摘要、证据数量和最终结果。技术编号仅在详情中展示。</p></div>
 <div className="mt-7 grid grid-cols-4 gap-4 max-[900px]:grid-cols-2">{stats.map(item=><div className="panel p-5" key={item.label}><div className="flex items-center justify-between"><p className="text-[10px] text-[#858995]">{item.label}</p><item.icon className="size-4 text-[#a0a3ab]"/></div><strong className="mt-3 block text-2xl text-[#20212a]">{runs.isLoading?"—":item.value}</strong><p className="mt-2 text-[10px] text-[#a0a3ab]">来自持久化运行记录</p></div>)}</div>
 <section className="panel mt-6"><div className="panel-head"><div><h3 className="panel-title">运行记录</h3><p className="mt-1 text-[10px] text-[#858995]">最近 100 条当前身份可见运行。</p></div><div className="flex h-9 items-center gap-2 rounded-[9px] border border-[#deded9] px-3"><Search className="size-3.5 text-[#858995]"/><input aria-label="搜索运行" value={search} onChange={event=>setSearch(event.target.value)} className="w-52 border-0 bg-transparent text-[11px] outline-none" placeholder="搜索答案、编号或问答类型"/></div></div>
 {runs.isLoading?<div className="empty-state"><LoaderCircle className="size-7 animate-spin text-[#4d55ca]"/></div>:null}
 {runs.error?<div className="m-5 rounded-xl bg-[#faeaea] p-4 text-xs text-[#9b4040]"><p>{runs.error.message}</p><Button className="mt-3" size="sm" variant="danger" onClick={()=>runs.refetch()}>重试</Button></div>:null}
 {items.length?<div className="table-shell m-4 mt-0 border-0"><table className="data-table"><thead><tr><th>问答摘要</th><th>类型</th><th>状态</th><th>创建时间</th><th>引用</th><th></th></tr></thead><tbody>{items.map(run=><tr key={run.id}><td><span className="block max-w-72 truncate text-[11px] font-semibold text-[#20212a]">{runDisplayTitle(run)}</span><span className="mt-1 block text-[9px] text-[#858995]">运行 #{shortIdentifier(run.id)}</span></td><td><span className="block text-[11px] text-[#20212a]">{runTypeLabel(run.taskType)}</span><span className="mt-1 block text-[9px] text-[#858995]">{runTypeDescription(run.taskType)}</span></td><td><RunStatus state={run.state}/></td><td>{format(run.createdAt)}</td><td>{run.answer?.citations.length??0} 条</td><td><Link href={`/runs/${run.id}`} className="text-[10px] font-semibold text-[#4d55ca]">查看详情 →</Link></td></tr>)}</tbody></table></div>:null}
 {!runs.isLoading&&!runs.error&&!items.length?<div className="empty-state"><div><Activity className="mx-auto size-9 text-[#b4b6bd]"/><p className="mt-3 text-xs text-[#656975]">{search?"没有匹配的运行":"还没有真实运行记录"}</p><p className="mt-2 text-[10px]">在智能问答页面发起问题后，运行会自动显示在这里。</p></div></div>:null}</section>
 </div></div>;
}
