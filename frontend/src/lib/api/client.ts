import { z } from "zod";

import type { components } from "./schema";

export type AgentRun = components["schemas"]["AgentRun"];
export type RunStepSummary = components["schemas"]["RunStepSummary"];
export type Citation = components["schemas"]["Citation"];
export type AgentMode = components["schemas"]["CreateAgentRunRequest"]["mode"];
export type Document = components["schemas"]["Document"];
export type DocumentUploadResult = components["schemas"]["DocumentUploadResult"];
export type IngestionJob = components["schemas"]["IngestionJob"];
export type MetadataReviewResult = components["schemas"]["MetadataReviewResult"];
export type ApprovalRequest = components["schemas"]["ApprovalRequest"];
export type EvaluationRun = components["schemas"]["EvaluationRun"];
export type GraphConflictList = components["schemas"]["GraphConflictList"];
export type GraphSnapshot = components["schemas"]["GraphSnapshot"];
export type GraphNode = components["schemas"]["GraphNode"];
export type GraphEdge = components["schemas"]["GraphEdge"];
export type GraphEntityDetail = components["schemas"]["GraphEntityDetail"];
export type GraphEntitySearchResult = components["schemas"]["GraphEntitySearchResult"];
export type GraphPolicy = components["schemas"]["GraphPolicy"];
export type GraphPolicyUpdate = components["schemas"]["GraphPolicyUpdate"];
export type GraphPath = components["schemas"]["GraphPath"];
export type GraphEntityMergeResult = components["schemas"]["GraphEntityMergeResult"];
export type AgentRunList = components["schemas"]["AgentRunList"];
export type ConversationList = components["schemas"]["ConversationList"];
export type ConversationDetail = components["schemas"]["ConversationDetail"];
export type DocumentList = components["schemas"]["DocumentList"];
export type DocumentVersion = components["schemas"]["DocumentVersion"];
export type DocumentVersionList = components["schemas"]["DocumentVersionList"];
export type RuntimeCapabilities = components["schemas"]["RuntimeCapabilities"];
export type RagPolicy = components["schemas"]["RagPolicy"];
export type RagPolicyUpdate = components["schemas"]["RagPolicyUpdate"];
export type RagStrategyCatalog = components["schemas"]["RagStrategyCatalog"];

const modeSchema = z.enum(["AUTO", "SIMPLE", "MULTI_SOURCE", "GRAPH"]);
const createRunInputSchema = z
  .object({
    query: z.string().trim().min(1).max(16_000),
    mode: modeSchema.optional(),
    conversationId: z.string().uuid().optional(),
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

export function buildAgentRunPayload(input: { query: string; mode?: AgentMode; conversationId?: string }) {
  const value = createRunInputSchema.parse(input);
  return { query: value.query, mode: value.mode ?? ("AUTO" as const),
    ...(value.conversationId ? { conversationId: value.conversationId } : {}) };
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

export function readRuntimeCapabilities(): Promise<RuntimeCapabilities> {
  return platformRequest("capabilities");
}

export async function createAgentRun(query: string, mode: AgentMode = "AUTO", conversationId?: string): Promise<AgentRun> {
  const response = await fetch("/api/agent-runs", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(buildAgentRunPayload({ query, mode, conversationId })),
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

export function listAgentRuns(limit = 50): Promise<AgentRunList> {
  return platformRequest(`agent-runs?limit=${encodeURIComponent(String(limit))}`);
}

export function listConversations(offset = 0): Promise<ConversationList> {
  return platformRequest(`conversations?limit=20&offset=${offset}`);
}

export function readConversation(id: string, before?: number): Promise<ConversationDetail> {
  return platformRequest(`conversations/${encodeURIComponent(id)}?limit=50${before ? `&before=${before}` : ""}`);
}

export function uploadDocument(formData: FormData): Promise<DocumentUploadResult> {
  return platformRequest("documents", { method: "POST", body: formData });
}

export function listDocuments(limit = 100): Promise<DocumentList> {
  return platformRequest(`documents?limit=${encodeURIComponent(String(limit))}`);
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

export function listDocumentVersions(documentId: string): Promise<DocumentVersionList> {
  return platformRequest(`documents/${encodeURIComponent(documentId)}/versions`);
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

export interface GraphQuery {
  query?: string;
  entityTypes?: string[];
  relationTypes?: string[];
  minimumConfidence?: number;
  limit?: number;
}

function graphSearchParams(input: GraphQuery = {}) {
  const parameters = new URLSearchParams();
  parameters.set("limit", String(input.limit ?? 200));
  if (input.query?.trim()) parameters.set("query", input.query.trim());
  for (const value of input.entityTypes ?? []) parameters.append("entityType", value);
  for (const value of input.relationTypes ?? []) parameters.append("relationType", value);
  if (input.minimumConfidence !== undefined) {
    parameters.set("minimumConfidence", String(input.minimumConfidence));
  }
  return parameters;
}

export function readGraphSnapshot(input: number | GraphQuery = 200): Promise<GraphSnapshot> {
  const parameters = graphSearchParams(typeof input === "number" ? { limit: input } : input);
  return platformRequest(`graph?${parameters.toString()}`);
}

export function searchGraphEntities(
  query: string,
  entityTypes: string[] = [],
  limit = 20,
): Promise<GraphEntitySearchResult> {
  const parameters = graphSearchParams({ query, entityTypes, limit });
  return platformRequest(`graph/entities?${parameters.toString()}`);
}

export function readGraphEntity(entityId: string): Promise<GraphEntityDetail> {
  return platformRequest(`graph/entities/${encodeURIComponent(entityId)}`);
}

export function readGraphNeighbors(
  entityId: string,
  input: GraphQuery & { depth?: 1 | 2 | 3 } = {},
): Promise<GraphSnapshot> {
  const parameters = graphSearchParams({ ...input, limit: input.limit ?? 80 });
  parameters.set("depth", String(input.depth ?? 1));
  return platformRequest(
    `graph/entities/${encodeURIComponent(entityId)}/neighbors?${parameters.toString()}`,
  );
}

export function readGraphRelation(relationId: string): Promise<GraphEdge> {
  return platformRequest(`graph/relations/${encodeURIComponent(relationId)}`);
}

export function readGraphPolicy(): Promise<GraphPolicy> {
  return platformRequest("graph/policy");
}

export function updateGraphPolicy(input: GraphPolicyUpdate): Promise<GraphPolicy> {
  return platformRequest("graph/policy", {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function readRagStrategies(): Promise<RagStrategyCatalog> {
  return platformRequest("rag/strategies");
}

export function readRagPolicy(): Promise<RagPolicy> {
  return platformRequest("rag/policy");
}

export function updateRagPolicy(input: RagPolicyUpdate): Promise<RagPolicy> {
  return platformRequest("rag/policy", {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(input),
  });
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
