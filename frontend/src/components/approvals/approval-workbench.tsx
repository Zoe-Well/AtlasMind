"use client";
import { useMutation,useQuery } from "@tanstack/react-query";
import { CheckCircle2,Clock3,LoaderCircle,Search,ShieldCheck,XCircle } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { OverlayPanel } from "@/components/ui/overlay-panel";
import { decideApproval,readApproval,readRuntimeCapabilities } from "@/lib/api/client";
export function ApprovalWorkbench({initialApprovalId=""}:{initialApprovalId?:string}){
 const [inputId,setInputId]=useState(initialApprovalId),[approvalId,setApprovalId]=useState(initialApprovalId),[reason,setReason]=useState(""),[detailOpen,setDetailOpen]=useState(Boolean(initialApprovalId));
 const capabilities=useQuery({queryKey:["runtime-capabilities"],queryFn:readRuntimeCapabilities});
 const approvalsEnabled=capabilities.data?.features.approvals===true;
 const approval=useQuery({queryKey:["approval",approvalId],queryFn:()=>readApproval(approvalId),enabled:Boolean(approvalId)&&approvalsEnabled});
 const decision=useMutation({mutationFn:(value:"APPROVE"|"DENY")=>decideApproval(approvalId,{decision:value,reason:reason.trim()||undefined}),onSuccess:(value)=>approval.refetch().then(()=>value)});
 const terminal=approval.data?approval.data.state!=="PENDING":true;
 function read(){setApprovalId(inputId.trim());setDetailOpen(true)}
 return <div><header className="page-topbar"><div><p className="mb-1 text-[10px] text-[#858995]">受控执行</p><h1 className="page-title">审批中心</h1></div><Badge className="bg-[#faeaea] text-[#9b4040]"><ShieldCheck className="mr-1 size-3"/>高风险操作需人工确认</Badge></header>
 <div className="page-content"><div><p className="eyebrow">Approval center</p><h2 className="heading-xl">高风险能力审批</h2><p className="mt-2 max-w-2xl text-xs leading-6 text-[#858995]">审批绑定具体主体、能力、目标和规范化参数摘要；过期、换参或重放都会被拒绝。</p></div>
 {!capabilities.isLoading&&!approvalsEnabled?<div className="mt-6 rounded-xl bg-[#fbf2df] p-4 text-xs leading-6 text-[#8a5a17]">当前持久化运行时尚未启用审批工作流。页面不会展示或提交演示审批。</div>:null}
 <div className="mt-7 grid grid-cols-4 gap-4 max-[900px]:grid-cols-2">{["等待处理","今日批准","今日拒绝","已过期"].map(label=><div className="panel p-5" key={label}><p className="text-[10px] text-[#858995]">{label}</p><strong className="mt-3 block text-2xl text-[#20212a]">—</strong><small className="text-[10px] text-[#a0a3ab]">列表接口待接入</small></div>)}</div>
 <section className="panel mt-6"><div className="panel-head"><div><h3 className="panel-title">审批请求</h3><p className="mt-1 text-[10px] text-[#858995]">运行时启用审批能力后才允许读取和决策。</p></div><div className="flex gap-2"><div className="flex h-9 items-center gap-2 rounded-[9px] border border-[#deded9] px-3"><Search className="size-3.5 text-[#858995]"/><input aria-label="审批 ID" value={inputId} onChange={e=>setInputId(e.target.value)} disabled={!approvalsEnabled} className="w-52 border-0 bg-transparent text-[11px] outline-none" placeholder="输入 Approval ID"/></div><Button size="sm" disabled={!approvalsEnabled||!inputId.trim()} onClick={read}>读取审批</Button></div></div>
 {approval.isError?<p role="alert" className="m-5 rounded-xl bg-[#faeaea] p-4 text-xs text-[#9b4040]">{approval.error.message}</p>:<div className="empty-state"><div><ShieldCheck className="mx-auto size-9 text-[#b4b6bd]"/><p className="mt-3 text-xs text-[#656975]">审批列表接口尚未提供</p><p className="mt-2 text-[10px]">从等待审批的运行进入，或按 ID 读取。</p></div></div>}</section></div>
 <OverlayPanel open={detailOpen} onOpenChange={setDetailOpen} title="审批请求详情" description="请核对能力、目标和参数摘要后作出一次性决定。" wide footer={approval.data?<><Button variant="danger" onClick={()=>decision.mutate("DENY")} disabled={terminal||decision.isPending}><XCircle className="size-4"/>拒绝</Button><Button onClick={()=>decision.mutate("APPROVE")} disabled={terminal||decision.isPending}><CheckCircle2 className="size-4"/>批准</Button></>:undefined}>
  {approval.isLoading?<p className="flex items-center gap-2 text-xs text-[#858995]"><LoaderCircle className="size-4 animate-spin"/>正在读取审批…</p>:null}
  {approval.data?<div><div className="flex items-center justify-between"><Badge className={approval.data.state==="PENDING"?"bg-[#fbf2df] text-[#8a5a17]":"bg-[#e8f5ee] text-[#287552]"}>{approval.data.state}</Badge><span className="flex items-center gap-1 text-[10px] text-[#858995]"><Clock3 className="size-3"/>有效期至 {new Date(approval.data.expiresAt).toLocaleString("zh-CN")}</span></div>
   <dl className="mt-6 grid grid-cols-2 gap-5 text-xs"><div><dt className="text-[#858995]">能力</dt><dd className="mt-2 font-mono text-[11px] text-[#20212a]">{approval.data.capability}</dd></div><div><dt className="text-[#858995]">目标</dt><dd className="mt-2 text-[#20212a]">{approval.data.targetSummary}</dd></div><div className="col-span-2"><dt className="text-[#858995]">规范化参数摘要</dt><dd className="mt-2 overflow-auto rounded-xl bg-[#f7f7f4] p-4 font-mono text-[10px] leading-5 text-[#484b56]"><pre>{JSON.stringify(approval.data.parameterSummary,null,2)}</pre></dd></div><div className="col-span-2"><dt className="text-[#858995]">关联 ID</dt><dd className="mt-2 break-all font-mono text-[10px]">{approval.data.correlationId}</dd></div></dl>
   <label className="mt-5 grid gap-2 text-xs font-semibold text-[#535761]">决定原因（可选）<textarea value={reason} onChange={e=>setReason(e.target.value)} className="min-h-20 resize-y rounded-[9px] border border-[#deded9] p-3 text-xs font-normal outline-none"/></label>
   {terminal?<p className="mt-4 rounded-xl bg-[#f0f0ec] p-3 text-xs text-[#656975]">该审批已进入终态，不能重复决定。</p>:null}{decision.error?<p role="alert" className="mt-4 rounded-xl bg-[#faeaea] p-3 text-xs text-[#9b4040]">{decision.error.message}</p>:null}
  </div>:null}
 </OverlayPanel></div>;
}
