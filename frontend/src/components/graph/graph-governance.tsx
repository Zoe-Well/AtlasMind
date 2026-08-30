"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleAlert, LoaderCircle, RefreshCw, Settings2 } from "lucide-react";
import { useState } from "react";

import { GraphExplorer } from "@/components/graph/graph-explorer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { OverlayPanel } from "@/components/ui/overlay-panel";
import { readGraphConflicts, readGraphPolicy, updateGraphPolicy, type GraphPolicy } from "@/lib/api/client";

type EntityType = GraphPolicy["availableEntityTypes"][number];
const ENTITY_DETAILS: Record<EntityType, { label: string; description: string }> = {
  SYSTEM: { label: "系统", description: "业务系统、平台或应用" },
  PRODUCT: { label: "产品", description: "可交付的软件或业务产品" },
  SERVICE: { label: "服务", description: "业务服务或后台服务" },
  API: { label: "接口", description: "API、端点或协议接口" },
  ERROR_CODE: { label: "错误码", description: "可定位问题的错误编号" },
  ORGANIZATION: { label: "组织", description: "公司、机构或外部组织" },
  ORG_UNIT: { label: "组织单元", description: "部门、团队或业务单元" },
  DATABASE: { label: "数据库", description: "数据库或数据存储实例" },
  QUEUE: { label: "消息队列", description: "队列、主题或事件通道" },
  TECH_COMPONENT: { label: "技术组件", description: "框架、中间件或基础组件" },
};

export function GraphGovernance() {
  const queryClient = useQueryClient();
  const conflicts = useQuery({ queryKey: ["graph-conflicts"], queryFn: readGraphConflicts });
  const policy = useQuery({ queryKey: ["graph-policy"], queryFn: readGraphPolicy });
  const [policyOpen, setPolicyOpen] = useState(false);
  const [selectedTypes, setSelectedTypes] = useState<EntityType[]>([]);

  const savePolicy = useMutation({
    mutationFn: () => {
      if (!policy.data) throw new Error("图谱策略尚未加载完成。");
      return updateGraphPolicy({
        allowedEntityTypes: selectedTypes,
        allowedRelationTypes: policy.data.allowedRelationTypes,
        minimumEntityConfidence: policy.data.minimumEntityConfidence,
        minimumRelationConfidence: policy.data.minimumRelationConfidence,
        seedLimit: policy.data.seedLimit,
        maxHops: policy.data.maxHops,
        maxNodes: policy.data.maxNodes,
        maxPaths: policy.data.maxPaths,
        maxGraphChunks: policy.data.maxGraphChunks,
        ...(policy.data.allowedAliases ? { allowedAliases: policy.data.allowedAliases } : {}),
      });
    },
    onSuccess: (nextPolicy) => {
      queryClient.setQueryData(["graph-policy"], nextPolicy);
      void queryClient.invalidateQueries({ queryKey: ["graph-scene"] });
      setPolicyOpen(false);
    },
  });

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["graph-scene"] });
    void conflicts.refetch();
    void policy.refetch();
  };
  const openPolicy = () => {
    if (!policy.data) return;
    setSelectedTypes([...policy.data.allowedEntityTypes]);
    savePolicy.reset();
    setPolicyOpen(true);
  };
  const toggleEntityType = (entityType: EntityType) => {
    setSelectedTypes((current) => current.includes(entityType) ? current.filter((value) => value !== entityType) : [...current, entityType]);
  };
  const loading = conflicts.isFetching || policy.isFetching;
  const availableTypes = policy.data?.availableEntityTypes ?? policy.data?.allowedEntityTypes ?? [];

  return <div>
    <header className="page-topbar">
      <div><p className="mb-1 text-[10px] text-[#858995]">企业知识库</p><h1 className="page-title">知识图谱</h1></div>
      <div className="flex gap-2"><Button variant="secondary" size="sm" onClick={refresh}><RefreshCw className="size-3.5"/>刷新图谱</Button><Badge className="bg-[#e8f5ee] text-[#287552]">真实投影</Badge></div>
    </header>
    <div className="page-content">
      <div><p className="eyebrow">Knowledge graph</p><h2 className="heading-xl">跨文档实体关系</h2><p className="mt-2 max-w-2xl text-xs leading-6 text-[#858995]">搜索进入、局部探索、按需展开。图谱仅发现关联并扩大召回，最终回答与引用仍回溯原始文档。</p></div>

      {policy.data ? <GraphExplorer policy={policy.data}/> : null}

      <section className="panel mt-7">
        <div className="panel-head"><div><h3 className="panel-title">实体保留策略</h3><p className="mt-1 text-[10px] text-[#858995]">决定哪些业务实体可以进入辅助检索图谱</p></div><div className="flex items-center gap-2">{policy.data ? <Badge>策略 v{policy.data.version}</Badge> : null}{policy.data?.canManage ? <Button variant="secondary" size="sm" onClick={openPolicy}><Settings2 className="size-3.5"/>配置实体</Button> : null}</div></div>
        {policy.isLoading ? <div className="flex items-center gap-2 p-5 text-[11px] text-[#858995]"><LoaderCircle className="size-4 animate-spin"/>正在读取当前策略…</div> : null}
        {policy.isError ? <div className="p-5 text-xs text-[#9b4040]"><p>{policy.error.message}</p><Button className="mt-3" onClick={() => policy.refetch()}>重试</Button></div> : null}
        {policy.data ? <div className="p-5"><div className="flex flex-wrap gap-2">{policy.data.allowedEntityTypes.map((entityType) => <span key={entityType} className="rounded-lg bg-white px-3 py-2 text-[10px]" title={ENTITY_DETAILS[entityType].description}><span className="font-semibold">{ENTITY_DETAILS[entityType].label}</span><span className="ml-1.5 font-mono text-[#858995]">{entityType}</span></span>)}</div><p className="mt-4 text-[10px] leading-5 text-[#858995]">当前启用 {policy.data.allowedEntityTypes.length} / {availableTypes.length} 类实体。保存新策略后会立即用于图谱浏览、检索和后续文档抽取。{!policy.data.canManage ? "当前账号为只读权限。" : ""}</p></div> : null}
      </section>

      <section className="panel mt-5"><div className="panel-head"><div><h3 className="panel-title">关系冲突</h3><p className="mt-1 text-[10px] text-[#858995]">歧义关系不会被静默确认为事实</p></div><Badge className="bg-[#fbf2df] text-[#8a5a17]">{conflicts.data?.relations.length ?? 0} 条</Badge></div>{conflicts.data?.relations.length ? <div className="grid grid-cols-3 gap-3 p-5 max-[900px]:grid-cols-1">{conflicts.data.relations.map((id) => <div key={id} className="rounded-xl bg-white p-4 text-[10px]"><span className="flex items-center justify-between font-semibold text-[#20212a]">关系冲突<CircleAlert className="size-3.5 text-[#8a5a17]"/></span><span className="mt-2 block break-all font-mono text-[#858995]">{id}</span></div>)}</div> : <p className="p-5 text-[10px] text-[#858995]">当前没有待治理冲突。</p>}</section>
      {loading ? <span className="sr-only">正在刷新知识图谱</span> : null}
    </div>

    <OverlayPanel open={policyOpen} onOpenChange={setPolicyOpen} title="配置实体保留策略" description="仅勾选对业务检索有价值、需要进入知识图谱的实体类型。" footer={<><Button variant="secondary" onClick={() => setPolicyOpen(false)}>取消</Button><Button onClick={() => savePolicy.mutate()} disabled={!selectedTypes.length || savePolicy.isPending}>{savePolicy.isPending ? <LoaderCircle className="size-4 animate-spin"/> : null}保存新版本</Button></>}>
      <div className="grid grid-cols-2 gap-3 max-[700px]:grid-cols-1">{availableTypes.map((entityType) => { const checked = selectedTypes.includes(entityType); return <label key={entityType} className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition ${checked ? "border-[#777edc] bg-[#f2f2ff]" : "border-[#deded9] bg-white hover:bg-[#fafaf8]"}`}><input type="checkbox" className="mt-0.5 size-4 accent-[#4d55ca]" checked={checked} onChange={() => toggleEntityType(entityType)}/><span><span className="block text-xs font-semibold text-[#20212a]">{ENTITY_DETAILS[entityType].label}</span><span className="mt-1 block text-[10px] leading-5 text-[#858995]">{ENTITY_DETAILS[entityType].description}</span><span className="mt-1 block font-mono text-[9px] text-[#777b88]">{entityType}</span></span></label>; })}</div>
      {!selectedTypes.length ? <p className="mt-4 text-[11px] text-[#9b4040]">至少保留一种实体类型。</p> : null}
      {savePolicy.isError ? <p className="mt-4 text-[11px] text-[#9b4040]">{savePolicy.error.message}</p> : null}
      <p className="mt-5 rounded-lg bg-[#f5f5f2] p-3 text-[10px] leading-5 text-[#656975]">该操作会创建新的策略版本。已有实体和关系不会被物理删除；浏览、检索和后续文档抽取将使用新策略。</p>
    </OverlayPanel>
  </div>;
}
