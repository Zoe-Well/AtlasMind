import type { AgentRun, Document, IngestionJob, RunStepSummary } from "@/lib/api/client";

export const ingestionStages: ReadonlyArray<{
  id: IngestionJob["currentStage"];
  label: string;
  description: string;
}> = [
  { id: "VALIDATING", label: "检查文件", description: "检查格式、大小和基本信息" },
  { id: "PARSING", label: "读取内容", description: "提取文字、段落和原文位置" },
  { id: "CHUNKING", label: "整理段落", description: "拆分为适合检索的知识片段" },
  { id: "METADATA", label: "确认文档信息", description: "处理负责部门和信息分级" },
  { id: "LEXICAL_INDEX", label: "建立关键词索引", description: "支持名称、编号和准确词语检索" },
  { id: "VECTOR_INDEX", label: "建立语义索引", description: "支持意思相近的问题检索" },
  { id: "GRAPH_INDEX", label: "构建知识关系", description: "提取实体、概念及其关系" },
  { id: "ACTIVATING", label: "发布到知识库", description: "完成后即可用于智能问答" },
];

const runTypeLabels: Record<NonNullable<AgentRun["taskType"]>, string> = {
  SIMPLE: "基础知识问答",
  MULTI_SOURCE: "多来源综合",
  GRAPH: "知识关系问答",
};

const runTypeDescriptions: Record<NonNullable<AgentRun["taskType"]>, string> = {
  SIMPLE: "从相关文档中检索并回答",
  MULTI_SOURCE: "综合多份文档形成结论",
  GRAPH: "结合文档与知识关系回答",
};

const runStateLabels: Record<AgentRun["state"], string> = {
  QUEUED: "等待处理",
  RUNNING: "正在检索与生成回答",
  WAITING_APPROVAL: "等待人工审批",
  COMPLETED: "已完成",
  PARTIAL: "部分完成",
  FAILED: "处理失败",
  TIMED_OUT: "处理超时",
  CANCELLED: "已取消",
};

const runStepStateLabels: Record<RunStepSummary["state"], string> = {
  PENDING: "等待执行",
  RUNNING: "正在执行",
  WAITING_APPROVAL: "等待人工审批",
  SUCCEEDED: "已完成",
  FAILED: "执行失败",
  SKIPPED: "已跳过",
};

const capabilityLabels: Record<NonNullable<RunStepSummary["capabilityName"]>, string> = {
  knowledge_search: "检索企业知识",
  search_knowledge: "搜索企业文档（历史）",
  search_graph: "查询知识关系（历史）",
  query_structured_data: "查询业务数据",
};

const versionStateLabels: Record<string, string> = {
  UPLOADED: "等待处理",
  VALIDATING: "正在检查文件",
  PARSING: "正在读取内容",
  CHUNKING: "正在整理段落",
  METADATA_REVIEW: "等待确认文档信息",
  INDEXING: "正在建立索引",
  ACTIVATING: "正在发布",
  SEARCHABLE: "已可用于问答",
  FAILED: "处理失败",
  REVOKED: "已撤销",
};

const jobStateLabels: Record<IngestionJob["state"], string> = {
  QUEUED: "等待处理",
  RUNNING: "正在处理",
  WAITING_METADATA_REVIEW: "等待确认文档信息",
  SEARCHABLE: "已可用于问答",
  FAILED: "处理失败",
  CANCELLED: "已取消",
};

const documentStatusLabels: Record<Document["status"], string> = {
  ACTIVE: "已启用",
  REVOKED: "已撤销",
  DELETED: "已删除",
};

export function runTypeLabel(type?: AgentRun["taskType"]): string {
  return type ? runTypeLabels[type] : "基础知识问答";
}

export function runTypeDescription(type?: AgentRun["taskType"]): string {
  return type ? runTypeDescriptions[type] : runTypeDescriptions.SIMPLE;
}

export function runStateLabel(state: AgentRun["state"]): string {
  return runStateLabels[state];
}

export function runStepLabel(step: RunStepSummary): string {
  if (step.capabilityName) return capabilityLabels[step.capabilityName];
  if (step.kind === "PLAN") return "分析问题并选择能力";
  if (step.kind === "COMPOSE") return "根据证据生成回答";
  if (step.kind === "VERIFY") return "校验回答引用";
  return step.kind === "RETRIEVAL" ? "检索知识" : "执行受控能力";
}

export function runStepDescription(step: RunStepSummary): string {
  if (step.capabilityName === "knowledge_search") {
    return "按策略计划执行 Query Processing、召回、融合和重排";
  }
  if (step.capabilityName === "search_knowledge") {
    return "历史运行：同时进行关键词和语义检索，并对候选证据排序";
  }
  if (step.capabilityName === "search_graph") {
    return "按需查找实体关系和多跳知识路径";
  }
  if (step.capabilityName === "query_structured_data") {
    return "通过白名单指标执行只读业务数据查询";
  }
  if (step.kind === "PLAN") return "Agent 根据问题和已有证据决定下一步";
  if (step.kind === "COMPOSE") return "只使用已授权证据组织答案";
  if (step.kind === "VERIFY") return "确认每条引用都来自本次有效证据";
  return runStepStateLabels[step.state];
}

export function runStepStateLabel(state: RunStepSummary["state"]): string {
  return runStepStateLabels[state];
}

export function jobStateLabel(state: IngestionJob["state"]): string {
  return jobStateLabels[state];
}

export function documentStatusLabel(status: Document["status"]): string {
  return documentStatusLabels[status];
}

export function versionStateLabel(state: string, searchable: boolean): string {
  if (searchable) return "已可用于问答";
  return versionStateLabels[state] ?? "处理中";
}

export function humanVersionLabel(value: string): string {
  const match = /^v(\d+)$/i.exec(value.trim());
  return match ? `第 ${match[1]} 版` : value;
}

export function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(value < 10 * 1024 ? 1 : 0)} KB`;
  return `${(value / 1024 ** 2).toFixed(value < 10 * 1024 ** 2 ? 1 : 0)} MB`;
}

export function shortIdentifier(value: string): string {
  return value.slice(0, 8);
}

export function runDisplayTitle(run: AgentRun): string {
  const text = run.answer?.text.replace(/\s+/g, " ").trim();
  if (!text) return `${runTypeLabel(run.taskType)} · ${runStateLabel(run.state)}`;
  return text.length > 42 ? `${text.slice(0, 42)}…` : text;
}
