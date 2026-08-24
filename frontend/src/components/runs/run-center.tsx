"use client";
import { Activity,ArrowRight,CheckCircle2,Clock3,Search,ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
export function RunCenter(){
 const [id,setId]=useState("");const router=useRouter();
 return <div><header className="page-topbar"><div><p className="mb-1 text-[10px] text-[#858995]">Agent operations</p><h1 className="page-title">运行中心</h1></div><Badge className="bg-[#e8f5ee] text-[#287552]">实时状态已连接</Badge></header>
 <div className="page-content"><div><p className="eyebrow">Run center</p><h2 className="heading-xl">运行与执行轨迹</h2><p className="mt-2 max-w-2xl text-xs leading-6 text-[#858995]">查看 Agent 状态、关联 ID、审批等待、失败原因和最终结果。当前契约仅支持按运行 ID 读取。</p></div>
 <div className="mt-7 grid grid-cols-4 gap-4 max-[900px]:grid-cols-2">{[{label:"今日运行",icon:Activity},{label:"进行中",icon:Clock3},{label:"完成",icon:CheckCircle2},{label:"等待审批",icon:ShieldCheck}].map(x=><div className="panel p-5" key={x.label}><div className="flex items-center justify-between"><p className="text-[10px] text-[#858995]">{x.label}</p><x.icon className="size-4 text-[#a0a3ab]"/></div><strong className="mt-3 block text-2xl text-[#20212a]">—</strong><p className="mt-2 text-[10px] text-[#a0a3ab]">列表统计接口待接入</p></div>)}</div>
 <section className="panel mt-6"><div className="panel-head"><div><h3 className="panel-title">运行记录</h3><p className="mt-1 text-[10px] text-[#858995]">输入运行 ID，读取服务端真实状态。</p></div><div className="flex gap-2"><div className="flex h-9 items-center gap-2 rounded-[9px] border border-[#deded9] px-3"><Search className="size-3.5 text-[#858995]"/><input aria-label="运行 ID" value={id} onChange={e=>setId(e.target.value)} className="w-52 border-0 bg-transparent text-[11px] outline-none" placeholder="Agent Run ID"/></div><Button size="sm" disabled={!id.trim()} onClick={()=>router.push(`/runs/${encodeURIComponent(id.trim())}`)}>打开<ArrowRight className="size-3"/></Button></div></div><div className="empty-state"><div><Activity className="mx-auto size-9 text-[#b4b6bd]"/><p className="mt-3 text-xs text-[#656975]">运行列表接口尚未提供</p><p className="mt-2 text-[10px]">从问答结果进入运行详情，或按 ID 读取。</p></div></div></section>
 </div></div>;
}
