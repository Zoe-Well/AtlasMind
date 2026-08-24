"use client";

import { useMutation,useQuery } from "@tanstack/react-query";
import { CircleAlert,GitMerge,LoaderCircle,Maximize2,Network,RefreshCw,Search,ShieldAlert,ZoomIn,ZoomOut } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { OverlayPanel } from "@/components/ui/overlay-panel";
import { mergeGraphEntity,readGraphConflicts } from "@/lib/api/client";

const graphNodes=[{x:330,y:270,label:"退款政策",primary:true},{x:145,y:150,label:"申请材料"},{x:535,y:135,label:"财务制度"},{x:590,y:340,label:"审批流程"},{x:155,y:395,label:"客户服务"},{x:350,y:475,label:"时效标准"}];
const lines=[[0,1],[0,2],[0,3],[0,4],[0,5],[1,4],[3,5]];

export function GraphGovernance(){
 const conflicts=useQuery({queryKey:["graph-conflicts"],queryFn:readGraphConflicts});
 const [sourceId,setSourceId]=useState(""),[targetId,setTargetId]=useState(""),[confirmed,setConfirmed]=useState(false),[entityOpen,setEntityOpen]=useState(false),[mergeOpen,setMergeOpen]=useState(false);
 const merge=useMutation({mutationFn:()=>mergeGraphEntity(sourceId.trim(),targetId.trim(),confirmed),onSuccess:()=>conflicts.refetch()});
 function chooseConflict(id:string){setSourceId(id);setTargetId("");setConfirmed(false);setMergeOpen(true)}
 return <div>
  <header className="page-topbar"><div><p className="mb-1 text-[10px] text-[#858995]">企业知识库</p><h1 className="page-title">知识图谱</h1></div><div className="flex gap-2"><Button variant="secondary" size="sm" onClick={()=>conflicts.refetch()}><RefreshCw className="size-3.5"/>刷新冲突</Button><Badge className="bg-[#e8f5ee] text-[#287552]">投影可重建</Badge></div></header>
  <div className="page-content">
   <div className="flex flex-wrap items-end justify-between gap-5"><div><p className="eyebrow">Knowledge graph</p><h2 className="heading-xl">探索实体与关系</h2><p className="mt-2 max-w-2xl text-xs leading-6 text-[#858995]">关系必须保留来源证据和知识范围；图谱浏览接口尚未接入，治理冲突使用真实 API。</p></div><div className="flex h-9 items-center gap-2 rounded-[9px] border border-[#deded9] bg-white px-3"><Search className="size-3.5 text-[#858995]"/><input className="w-48 border-0 bg-transparent text-[11px] outline-none" placeholder="搜索实体、别名或关系"/></div></div>
   <section className="panel mt-7 overflow-hidden">
    <div className="grid min-h-[620px] grid-cols-[minmax(0,1fr)_300px] max-[1000px]:grid-cols-1">
     <div className="relative min-h-[620px] bg-[radial-gradient(circle_at_center,#fff_0,#fafaf8_72%)]">
      <div className="absolute left-4 top-4 z-10 flex gap-1 rounded-[10px] border border-[#deded9] bg-white p-1"><button className="grid size-8 place-items-center rounded-lg hover:bg-[#f0f0ec]" aria-label="放大"><ZoomIn className="size-3.5"/></button><button className="grid size-8 place-items-center rounded-lg hover:bg-[#f0f0ec]" aria-label="缩小"><ZoomOut className="size-3.5"/></button><button className="grid size-8 place-items-center rounded-lg hover:bg-[#f0f0ec]" aria-label="适应画布"><Maximize2 className="size-3.5"/></button></div>
      <svg viewBox="0 0 720 620" className="h-[620px] w-full" aria-label="知识图谱预览">
       {lines.map(([a,b],i)=><line key={i} x1={graphNodes[a].x} y1={graphNodes[a].y} x2={graphNodes[b].x} y2={graphNodes[b].y} stroke="#c9cbd8" strokeWidth="1.5"/>)}
       {graphNodes.map((node,i)=><g key={node.label} onClick={()=>setEntityOpen(true)} className="cursor-pointer"><circle cx={node.x} cy={node.y} r={node.primary?45:37} fill={node.primary?"#4d55ca":"#fff"} stroke={node.primary?"#4d55ca":"#aeb2c8"} strokeWidth="2"/><text x={node.x} y={node.y+4} textAnchor="middle" fill={node.primary?"#fff":"#484b56"} fontSize="11">{node.label}</text>{i===0?<circle cx={node.x+34} cy={node.y-34} r="8" fill="#287552" stroke="#fff" strokeWidth="3"/>:null}</g>)}
      </svg>
      <p className="absolute bottom-4 left-4 rounded-lg bg-white/90 px-3 py-2 text-[10px] text-[#858995] shadow-sm">画布为界面占位 · 图谱浏览接口待接入</p>
     </div>
     <aside className="border-l border-[#deded9] bg-[#fafaf8] p-[18px] max-[1000px]:border-l-0 max-[1000px]:border-t">
      <div className="flex items-center justify-between"><h3 className="text-xs font-semibold text-[#20212a]">关系冲突</h3>{conflicts.isFetching?<LoaderCircle className="size-3.5 animate-spin text-[#4d55ca]"/>:<Badge className="bg-[#fbf2df] text-[#8a5a17]">{conflicts.data?.relations.length??0} 条</Badge>}</div>
      {conflicts.isError?<p role="alert" className="mt-4 rounded-lg bg-[#faeaea] p-3 text-[10px] leading-5 text-[#9b4040]">{conflicts.error.message}</p>:null}
      <div className="mt-4 grid gap-2">{conflicts.data?.relations.map(id=><button key={id} onClick={()=>chooseConflict(id)} className="rounded-xl border border-[#deded9] bg-white p-3 text-left hover:border-[#bfc1d6]"><span className="flex items-center justify-between text-[11px] font-semibold text-[#20212a]">关系冲突<CircleAlert className="size-3.5 text-[#8a5a17]"/></span><span className="mt-2 block break-all font-mono text-[9px] text-[#858995]">{id}</span><span className="mt-2 block text-[10px] text-[#4d55ca]">打开治理详情 →</span></button>)}</div>
      {conflicts.data&&!conflicts.data.relations.length?<div className="empty-state min-h-[240px]"><div><Network className="mx-auto size-8 text-[#b4b6bd]"/><p className="mt-3 text-[11px]">当前没有待治理冲突</p></div></div>:null}
      {!conflicts.data&&!conflicts.isFetching?<p className="mt-6 text-[10px] leading-5 text-[#858995]">冲突接口返回后会在此显示需要人工治理的关系或实体。</p>:null}
     </aside>
    </div>
   </section>
  </div>
  <OverlayPanel open={entityOpen} onOpenChange={setEntityOpen} title="退款政策" description="规范实体 · Policy" mode="drawer">
   <div className="flex items-center gap-3"><span className="grid size-12 place-items-center rounded-full bg-[#4d55ca] text-white"><Network className="size-5"/></span><div><h3 className="text-sm font-semibold text-[#20212a]">退款政策</h3><p className="mt-1 text-[10px] text-[#858995]">6 条关系 · 12 个来源片段</p></div></div>
   <div className="mt-7"><h4 className="text-xs font-semibold text-[#20212a]">实体来源</h4><div className="mt-3 rounded-xl border border-[#deded9] p-4"><p className="text-[11px] font-semibold text-[#20212a]">《企业退款管理办法》</p><p className="mt-1 text-[10px] text-[#858995]">第 2 章 · 第 3 段 · 当前版本</p><p className="mt-3 text-[11px] leading-6 text-[#656975]">该实体由受控抽取流程识别，规范来源与关系证据需由后端图谱浏览接口提供。</p></div></div>
  </OverlayPanel>
  <OverlayPanel open={mergeOpen} onOpenChange={setMergeOpen} title="合并重复实体" description="合并会改变后续图投影，原始 mention 与证据仍会保留。" footer={<><Button variant="secondary" onClick={()=>setMergeOpen(false)}>取消</Button><Button onClick={()=>merge.mutate()} disabled={!sourceId.trim()||!targetId.trim()||!confirmed||merge.isPending}>{merge.isPending?<LoaderCircle className="size-4 animate-spin"/>:<GitMerge className="size-4"/>}执行合并</Button></>}>
   <div className="grid grid-cols-2 gap-5"><label className="grid gap-2 text-xs font-semibold text-[#535761]">来源实体 ID<input className="field font-mono text-[11px]" value={sourceId} onChange={e=>setSourceId(e.target.value)}/></label><label className="grid gap-2 text-xs font-semibold text-[#535761]">目标规范实体 ID<input aria-label="目标规范实体 ID" className="field font-mono text-[11px]" value={targetId} onChange={e=>setTargetId(e.target.value)}/></label></div>
   <label className="mt-5 flex items-start gap-3 rounded-xl bg-[#fbf2df] p-4 text-xs text-[#8a5a17]"><input type="checkbox" className="mt-0.5" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/><span><strong className="flex items-center gap-2"><ShieldAlert className="size-4"/>确认治理影响</strong><span className="mt-1 block text-[10px] leading-5">我已核对两个实体及其来源，确认由目标实体承担规范身份。</span></span></label>
   {merge.data?<p className="mt-4 rounded-xl bg-[#e8f5ee] p-4 text-xs text-[#287552]">实体 {merge.data.id} 已合并至 {merge.data.mergedIntoId}。</p>:null}{merge.error?<p role="alert" className="mt-4 rounded-xl bg-[#faeaea] p-4 text-xs text-[#9b4040]">{merge.error.message}</p>:null}
  </OverlayPanel>
 </div>;
}
