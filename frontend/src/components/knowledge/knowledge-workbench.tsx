"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Check, ChevronRight, CircleAlert, Database, File, FileClock, FileUp, LoaderCircle, Plus, RefreshCw, Search, Server, UploadCloud } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { OverlayPanel } from "@/components/ui/overlay-panel";
import { readDocument, readIngestionJob, retryIngestionJob, reviewMetadata, uploadDocument, type Document, type DocumentUploadResult } from "@/lib/api/client";

const schema=z.object({title:z.string().trim().min(1,"请输入文档标题").max(500),sourceKey:z.string().trim().min(1,"请输入稳定来源键").max(300),scope:z.string().trim().min(1,"请输入知识范围"),businessOwner:z.string().trim().optional(),classification:z.enum(["PUBLIC","INTERNAL","CONFIDENTIAL"])});
type Values=z.infer<typeof schema>;
const stages=["VALIDATING","PARSING","CHUNKING","METADATA","LEXICAL_INDEX","VECTOR_INDEX","GRAPH_INDEX","ACTIVATING"];
function Field({label,children,hint}:{label:string;children:React.ReactNode;hint?:string}){return <label className="grid gap-2 text-xs font-semibold text-[#535761]">{label}{children}{hint?<span className="text-[10px] font-normal leading-4 text-[#858995]">{hint}</span>:null}</label>}

export function KnowledgeWorkbench(){
  const [uploadOpen,setUploadOpen]=useState(false),[sqlOpen,setSqlOpen]=useState(false),[documentOpen,setDocumentOpen]=useState(false),[jobOpen,setJobOpen]=useState(false),[metadataOpen,setMetadataOpen]=useState(false);
  const [file,setFile]=useState<File|null>(null),[result,setResult]=useState<DocumentUploadResult|null>(null),[document,setDocument]=useState<Document|null>(null),[lookupId,setLookupId]=useState("");
  const form=useForm<Values>({resolver:zodResolver(schema),defaultValues:{title:"",sourceKey:"",scope:"scope-public",businessOwner:"",classification:"INTERNAL"}});
  const upload=useMutation({mutationFn:async(values:Values)=>{if(!file)throw new Error("请选择需要导入的文件");const data=new FormData();data.set("file",file);data.set("title",values.title);data.set("sourceKey",values.sourceKey);data.append("knowledgeScopeCodes",values.scope);data.set("metadata",JSON.stringify({businessOwner:values.businessOwner||undefined,classification:values.classification}));return uploadDocument(data)},onSuccess:(value)=>{setResult(value);setDocument(value.document);setUploadOpen(false);setJobOpen(true)}});
  const lookup=useMutation({mutationFn:()=>readDocument(lookupId.trim()),onSuccess:(value)=>{setDocument(value);setDocumentOpen(true)}});
  const job=useQuery({queryKey:["ingestion-job",result?.ingestionJob.id],queryFn:()=>readIngestionJob(result!.ingestionJob.id),initialData:result?.ingestionJob,enabled:Boolean(result),refetchInterval:(query)=>{const state=query.state.data?.state;return state&&["SEARCHABLE","FAILED","CANCELLED","WAITING_METADATA_REVIEW"].includes(state)?false:1500}});
  const retry=useMutation({mutationFn:()=>retryIngestionJob(result!.ingestionJob.id),onSuccess:()=>job.refetch()});
  const review=useMutation({mutationFn:()=>reviewMetadata(result!.versionId,{approved:true,corrections:{businessOwner:form.getValues("businessOwner")||"Knowledge Operations",classification:form.getValues("classification")}}),onSuccess:()=>{setMetadataOpen(false);job.refetch()}});
  const currentJob=job.data;
  const stageIndex=currentJob?Math.max(stages.indexOf(currentJob.currentStage),0):-1;

  return <div>
    <header className="page-topbar"><div><p className="mb-1 text-[10px] text-[#858995]">企业知识库</p><h1 className="page-title">数据接入</h1></div><div className="flex gap-2"><Button variant="secondary" onClick={()=>setSqlOpen(true)}><Database className="size-4"/>连接 SQL</Button><Button onClick={()=>setUploadOpen(true)}><Plus className="size-4"/>上传文档</Button></div></header>
    <div className="page-content">
      <div className="flex flex-wrap items-end justify-between gap-5"><div><p className="eyebrow">Data sources</p><h2 className="heading-xl">管理知识来源</h2><p className="mt-2 max-w-2xl text-xs leading-6 text-[#858995]">接入文档和结构化数据，跟踪解析、索引、元数据及生命周期状态。</p></div><div className="flex gap-2"><Badge className="bg-[#e8f5ee] text-[#287552]">单一企业知识库</Badge><Badge>列表接口待接入</Badge></div></div>
      <div className="mt-7 grid grid-cols-3 gap-4 max-[900px]:grid-cols-1">
        <button onClick={()=>setUploadOpen(true)} className="panel flex min-h-[118px] items-center gap-4 p-5 text-left transition hover:border-[#bfc1d6] hover:shadow-sm"><span className="grid size-11 place-items-center rounded-xl bg-[#f0f1ff] text-[#4d55ca]"><UploadCloud className="size-5"/></span><span><strong className="block text-sm text-[#20212a]">上传企业文档</strong><small className="mt-1 block text-[10px] leading-5 text-[#858995]">PDF、DOCX、Markdown、HTML 与文本</small></span><ChevronRight className="ml-auto size-4 text-[#a0a3ab]"/></button>
        <button onClick={()=>setSqlOpen(true)} className="panel flex min-h-[118px] items-center gap-4 p-5 text-left transition hover:border-[#bfc1d6] hover:shadow-sm"><span className="grid size-11 place-items-center rounded-xl bg-[#f0f1ff] text-[#4d55ca]"><Server className="size-5"/></span><span><strong className="block text-sm text-[#20212a]">连接 SQL 数据源</strong><small className="mt-1 block text-[10px] leading-5 text-[#858995]">受控数据集、指标和只读查询</small></span><ChevronRight className="ml-auto size-4 text-[#a0a3ab]"/></button>
        <div className="panel flex min-h-[118px] items-center gap-4 p-5"><span className="grid size-11 place-items-center rounded-xl bg-[#e8f5ee] text-[#287552]"><Check className="size-5"/></span><span><strong className="block text-sm text-[#20212a]">{document?"1 个当前对象":"知识服务正常"}</strong><small className="mt-1 block text-[10px] leading-5 text-[#858995]">上传与单对象读取已连接真实 API</small></span></div>
      </div>
      <section className="mt-6 panel">
        <div className="panel-head"><div><h3 className="panel-title">文档与数据源</h3><p className="mt-1 text-[10px] text-[#858995]">当前接口暂不支持完整列表，成功上传或按 ID 读取的对象会显示在这里。</p></div><div className="flex gap-2"><div className="flex h-9 items-center gap-2 rounded-[9px] border border-[#deded9] bg-white px-3"><Search className="size-3.5 text-[#858995]"/><input value={lookupId} onChange={(e)=>setLookupId(e.target.value)} placeholder="输入文档 ID" className="w-44 border-0 bg-transparent text-[11px] outline-none"/></div><Button size="sm" variant="secondary" disabled={!lookupId.trim()||lookup.isPending} onClick={()=>lookup.mutate()}>{lookup.isPending?<LoaderCircle className="size-3 animate-spin"/>:"读取"}</Button></div></div>
        {lookup.error?<p role="alert" className="mx-5 mt-4 rounded-lg bg-[#faeaea] p-3 text-xs text-[#9b4040]">{lookup.error.message}</p>:null}
        <div className="table-shell m-4 mt-0 border-0">
          <table className="data-table"><thead><tr><th>名称</th><th>类型</th><th>来源键</th><th>状态</th><th>活动版本</th><th></th></tr></thead><tbody>
            {document?<tr><td><button onClick={()=>setDocumentOpen(true)} className="flex items-center gap-3 text-left"><span className="grid size-9 place-items-center rounded-lg bg-[#f0f1ff] text-[#4d55ca]"><File className="size-4"/></span><span><strong className="block text-[#20212a]">{document.title}</strong><small className="mt-1 block text-[10px] text-[#858995]">{document.id}</small></span></button></td><td>企业文档</td><td>{document.sourceKey}</td><td><Badge className={document.status==="ACTIVE"?"bg-[#e8f5ee] text-[#287552]":""}>{document.status}</Badge></td><td className="font-mono text-[10px]">{document.activeVersionId??"尚未激活"}</td><td><Button size="sm" variant="ghost" onClick={()=>setDocumentOpen(true)}>详情</Button>{result?<Button size="sm" variant="ghost" onClick={()=>setJobOpen(true)}>任务</Button>:null}</td></tr>:null}
          </tbody></table>
          {!document?<div className="empty-state"><div><FileClock className="mx-auto size-9 text-[#b4b6bd]"/><p className="mt-3 text-xs text-[#656975]">暂无可展示的文档</p><p className="mt-2 text-[10px] leading-5">上传文档，或使用右上方文档 ID 读取真实对象。<br/>文档列表接口尚未提供。</p><Button className="mt-4" size="sm" onClick={()=>setUploadOpen(true)}><FileUp className="size-3.5"/>上传第一份文档</Button></div></div>:null}
        </div>
      </section>
    </div>

    <OverlayPanel open={uploadOpen} onOpenChange={setUploadOpen} title="上传企业文档" description="原始文件会进入受控对象存储；知识范围和关键元数据由服务端校验。" footer={<><Button variant="secondary" onClick={()=>setUploadOpen(false)}>取消</Button><Button onClick={form.handleSubmit((v)=>upload.mutate(v))} disabled={upload.isPending}>{upload.isPending?<LoaderCircle className="size-4 animate-spin"/>:<UploadCloud className="size-4"/>}开始导入</Button></>}>
      <form className="grid grid-cols-2 gap-5 max-[620px]:grid-cols-1" onSubmit={form.handleSubmit((v)=>upload.mutate(v))}>
        <div className="col-span-2 max-[620px]:col-span-1"><label className="grid min-h-32 cursor-pointer place-items-center rounded-xl border border-dashed border-[#c9cad1] bg-[#fafaf8] text-center text-[#858995]"><span><UploadCloud className="mx-auto size-6"/><strong className="mt-2 block text-xs text-[#20212a]">{file?.name??"点击选择需要上传的文件"}</strong><small className="mt-1 block text-[10px]">单文件上传，大小与类型由服务端再次校验</small></span><input type="file" className="sr-only" onChange={(e)=>setFile(e.target.files?.[0]??null)}/></label></div>
        <Field label="文档标题"><input className="field" {...form.register("title")}/></Field><Field label="稳定来源键" hint="例如 policy/refund/2026"><input className="field" {...form.register("sourceKey")}/></Field>
        <Field label="知识范围"><input className="field" {...form.register("scope")}/></Field><Field label="业务负责人"><input className="field" {...form.register("businessOwner")}/></Field>
        <Field label="信息分级"><select className="field" {...form.register("classification")}><option>PUBLIC</option><option>INTERNAL</option><option>CONFIDENTIAL</option></select></Field>
        {(upload.error||Object.keys(form.formState.errors).length)?<p role="alert" className="col-span-2 rounded-lg bg-[#faeaea] p-3 text-xs text-[#9b4040]">{upload.error?.message??Object.values(form.formState.errors)[0]?.message}</p>:null}
      </form>
    </OverlayPanel>

    <OverlayPanel open={sqlOpen} onOpenChange={setSqlOpen} title="连接 SQL 数据源" description="仅允许登记经过治理的只读数据集，模型不会直接执行任意 SQL。" footer={<><Button variant="secondary" onClick={()=>setSqlOpen(false)}>取消</Button><Button disabled>保存连接</Button></>}>
      <div className="rounded-xl bg-[#fbf2df] p-4 text-xs leading-6 text-[#8a5a17]"><strong className="flex items-center gap-2"><CircleAlert className="size-4"/>接口待接入</strong><p>当前后端尚未提供数据源登记契约，本页面先保留字段与安全说明，不会保存连接凭据。</p></div>
      <div className="mt-5 grid grid-cols-2 gap-5"><Field label="连接名称"><input className="field" placeholder="例如：退款指标库"/></Field><Field label="数据库类型"><select className="field"><option>PostgreSQL</option><option>MySQL</option></select></Field><div className="col-span-2"><Field label="服务器地址"><input className="field" placeholder="由服务端密钥管理连接，不在浏览器保存密码"/></Field></div></div>
    </OverlayPanel>

    <OverlayPanel open={documentOpen} onOpenChange={setDocumentOpen} title={document?.title??"文档详情"} description="逻辑文档、当前活动版本与生命周期" mode="drawer">
      {document?<><div className="flex items-center justify-between"><Badge className="bg-[#e8f5ee] text-[#287552]">{document.status}</Badge><span className="text-[10px] text-[#858995]">企业文档</span></div><dl className="mt-6 grid gap-5 text-xs"><div><dt className="text-[#858995]">文档 ID</dt><dd className="mt-1 break-all font-mono text-[11px] text-[#20212a]">{document.id}</dd></div><div><dt className="text-[#858995]">来源键</dt><dd className="mt-1 text-[#20212a]">{document.sourceKey}</dd></div><div><dt className="text-[#858995]">活动版本</dt><dd className="mt-1 break-all font-mono text-[11px] text-[#20212a]">{document.activeVersionId??"尚未激活"}</dd></div></dl><div className="mt-7 border-t border-[#deded9] pt-5"><h3 className="text-xs font-semibold text-[#20212a]">版本治理</h3><p className="mt-2 text-[10px] leading-5 text-[#858995]">完整版本列表接口尚未提供。新版本上传仍通过现有文档版本接口维护。</p></div></>:null}
    </OverlayPanel>

    <OverlayPanel open={jobOpen} onOpenChange={setJobOpen} title="导入任务详情" description={currentJob?.id??"等待任务创建"} mode="drawer">
      {currentJob?<><div className="flex items-center justify-between"><Badge className={currentJob.state==="FAILED"?"bg-[#faeaea] text-[#9b4040]":currentJob.state==="SEARCHABLE"?"bg-[#e8f5ee] text-[#287552]":"bg-[#eceeff] text-[#4d55ca]"}>{currentJob.state}</Badge><Button size="sm" variant="ghost" onClick={()=>job.refetch()}><RefreshCw className="size-3"/>刷新</Button></div><div className="mt-7 grid gap-0">{stages.map((stage,index)=><div key={stage} className="relative grid grid-cols-[24px_1fr] gap-3 pb-5 before:absolute before:bottom-0 before:left-[11px] before:top-6 before:w-px before:bg-[#deded9] last:before:hidden"><span className={`relative z-10 grid size-6 place-items-center rounded-full text-[9px] ${index<stageIndex?"bg-[#e8f5ee] text-[#287552]":index===stageIndex?"bg-[#4d55ca] text-white":"bg-[#ecece8] text-[#858995]"}`}>{index<stageIndex?<Check className="size-3"/>:index+1}</span><div><strong className="text-[11px] text-[#20212a]">{stage}</strong><p className="mt-1 text-[10px] text-[#858995]">{index===stageIndex?"当前处理阶段":index<stageIndex?"已完成":"等待执行"}</p></div></div>)}</div>{currentJob.state==="WAITING_METADATA_REVIEW"?<Button onClick={()=>setMetadataOpen(true)}>确认关键元数据</Button>:null}{currentJob.failure?<div className="mt-4 rounded-xl bg-[#faeaea] p-4 text-xs text-[#9b4040]"><strong>{currentJob.failure.code}</strong><p className="mt-1">{currentJob.failure.message}</p>{currentJob.failure.retryable?<Button className="mt-3" size="sm" variant="danger" onClick={()=>retry.mutate()}><RefreshCw className="size-3"/>重试任务</Button>:null}</div>:null}</>:<div className="empty-state">尚无导入任务</div>}
    </OverlayPanel>
    <OverlayPanel open={metadataOpen} onOpenChange={setMetadataOpen} title="确认关键元数据" description="关键字段经人工确认后，导入流程才会继续。" footer={<><Button variant="secondary" onClick={()=>setMetadataOpen(false)}>稍后处理</Button><Button onClick={()=>review.mutate()} disabled={review.isPending}>{review.isPending?<LoaderCircle className="size-4 animate-spin"/>:<Check className="size-4"/>}确认并继续</Button></>}>
      <div className="grid grid-cols-2 gap-5"><Field label="业务负责人"><input className="field" {...form.register("businessOwner")}/></Field><Field label="信息分级"><select className="field" {...form.register("classification")}><option>PUBLIC</option><option>INTERNAL</option><option>CONFIDENTIAL</option></select></Field></div>
    </OverlayPanel>
  </div>;
}
