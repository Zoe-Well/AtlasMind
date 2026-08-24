import { z } from "zod";

import type { components } from "./schema";

export type AgentRun = components["schemas"]["AgentRun"];
export type Citation = components["schemas"]["Citation"];
export type AgentMode = components["schemas"]["CreateAgentRunRequest"]["mode"];
export type Document = components["schemas"]["Document"];
export type DocumentUploadResult = components["schemas"]["DocumentUploadResult"];
export type IngestionJob = components["schemas"]["IngestionJob"];
export type MetadataReviewResult = components["schemas"]["MetadataReviewResult"];
export type ApprovalRequest = components["schemas"]["ApprovalRequest"];
export type EvaluationRun = components["schemas"]["EvaluationRun"];
export type GraphConflictList = components["schemas"]["GraphConflictList"];
export type GraphEntityMergeResult = components["schemas"]["GraphEntityMergeResult"];

const modeSchema = z.enum(["AUTO", "SIMPLE", "MULTI_SOURCE", "GRAPH"]);
const createRunInputSchema = z
  .object({
    query: z.string().trim().min(1).max(16_000),
    mode: modeSchema.optional(),
  })
  .strict();

export interface PlatformProblem {
  code?: string;
  title?: string;
  detail?: string;
}

export class PlatformApiError extends Error {
  constructor(message: string, readonly status: number, readonly code?: string) {
    super(message);
  }
}

export function buildAgentRunPayload(input: { query: string; mode?: AgentMode }) {
  const value = createRunInputSchema.parse(input);
  return { query: value.query, mode: value.mode ?? ("AUTO" as const) };
}

async function platformRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/platform/${path.replace(/^\/+/, "")}`, {
    ...init,
    cache: "no-store",
  });
  if (!response.ok) {
    const problem = (await response.json().catch(() => ({}))) as PlatformProblem;
    const messages: Record<number, string> = {
      401: "登录状态已失效，请重新登录。",
      403: "当前身份没有执行此操作的权限。",
      404: "对象不存在或当前身份不可见。",
      409: "对象状态已变化，请刷新后重试。",
      422: "提交内容未通过校验，请检查必填项。",
      503: "当前功能依赖的服务尚未配置或暂不可用。",
    };
    throw new PlatformApiError(
      problem.detail ?? problem.title ?? messages[response.status] ?? "请求失败，请稍后重试。",
      response.status,
      problem.code,
    );
  }
  return (await response.json()) as T;
}

export async function createAgentRun(query: string, mode: AgentMode = "AUTO"): Promise<AgentRun> {
  const response = await fetch("/api/agent-runs", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(buildAgentRunPayload({ query, mode })),
  });
  if (!response.ok) {
    const problem = (await response.json().catch(() => ({}))) as PlatformProblem;
    throw new PlatformApiError(
      problem.detail ?? problem.title ?? "无法创建运行，请稍后重试。",
      response.status,
      problem.code,
    );
  }
  return (await response.json()) as AgentRun;
}

export async function readAgentRun(runId: string): Promise<AgentRun> {
  const response = await fetch(`/api/agent-runs/${encodeURIComponent(runId)}`, {
    cache: "no-store",
  });
  if (!response.ok) throw new PlatformApiError("无法读取运行状态。", response.status);
  return (await response.json()) as AgentRun;
}

export function uploadDocument(formData: FormData): Promise<DocumentUploadResult> {
  return platformRequest("documents", { method: "POST", body: formData });
}

export function readDocument(documentId: string): Promise<Document> {
  return platformRequest(`documents/${encodeURIComponent(documentId)}`);
}

export function revokeDocument(documentId: string): Promise<Document> {
  return platformRequest(`documents/${encodeURIComponent(documentId)}`, { method: "DELETE" });
}

export function uploadDocumentVersion(
  documentId: string,
  formData: FormData,
): Promise<DocumentUploadResult> {
  return platformRequest(`documents/${encodeURIComponent(documentId)}/versions`, {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: formData,
  });
}

export function readIngestionJob(jobId: string): Promise<IngestionJob> {
  return platformRequest(`ingestion-jobs/${encodeURIComponent(jobId)}`);
}

export function retryIngestionJob(jobId: string): Promise<IngestionJob> {
  return platformRequest(`ingestion-jobs/${encodeURIComponent(jobId)}/retry`, {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
}

export function reviewMetadata(
  versionId: string,
  input: { approved: boolean; corrections: Record<string, unknown> },
): Promise<MetadataReviewResult> {
  return platformRequest(`document-versions/${encodeURIComponent(versionId)}/metadata-review`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function readApproval(approvalId: string): Promise<ApprovalRequest> {
  return platformRequest(`approval-requests/${encodeURIComponent(approvalId)}`);
}

export function decideApproval(
  approvalId: string,
  input: { decision: "APPROVE" | "DENY"; reason?: string },
): Promise<ApprovalRequest> {
  return platformRequest(`approval-requests/${encodeURIComponent(approvalId)}/decision`, {
    method: "POST",
    headers: { "content-type": "application/json", "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify(input),
  });
}

export function createEvaluationRun(input: {
  datasetId: string;
  datasetVersion: string;
  retrievalPolicyVersion?: string;
}): Promise<EvaluationRun> {
  return platformRequest("evaluation-runs", {
    method: "POST",
    headers: { "content-type": "application/json", "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify(input),
  });
}

export function readEvaluationRun(runId: string): Promise<EvaluationRun> {
  return platformRequest(`evaluation-runs/${encodeURIComponent(runId)}`);
}

export function readGraphConflicts(): Promise<GraphConflictList> {
  return platformRequest("graph/conflicts");
}

export function mergeGraphEntity(
  entityId: string,
  targetEntityId: string,
  approved: boolean,
): Promise<GraphEntityMergeResult> {
  return platformRequest(`graph/entities/${encodeURIComponent(entityId)}/merge`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ targetEntityId, approved }),
  });
}
