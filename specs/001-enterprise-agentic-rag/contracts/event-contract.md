# Event Contract

## Purpose

本契约定义 ingestion、projection、Agent、tool、approval、evaluation 和 audit 的异步事件 envelope。
事件通过 PostgreSQL transactional outbox 产生；消费者至少一次处理并以事件 ID 和 aggregate
generation 幂等。事件不是权限事实源，处理前必须加载当前规范状态。

## Event Envelope

```json
{
  "event_id": "uuid",
  "event_type": "knowledge.document-version.created.v1",
  "schema_version": 1,
  "occurred_at": "2026-08-22T10:00:00Z",
  "producer": "atlasmind-api",
  "correlation_id": "uuid",
  "causation_id": "uuid-or-null",
  "aggregate": {
    "type": "DocumentVersion",
    "id": "opaque-id",
    "version": 1
  },
  "classification": "INTERNAL",
  "payload": {}
}
```

## Rules

- `event_id` 全局唯一；消费者以其去重。
- `event_type` 使用 `<domain>.<entity>.<action>.v<major>`，不复用已改变语义的版本。
- `aggregate.version` 单调递增；projection 事件额外携带 generation。
- payload 只包含处理所需的规范 ID、状态和受控引用，不包含凭据、原始 token、整段文档或隐藏推理。
- 事件不得携带可由消费者直接信任的 role/scope 列表；消费者加载当前授权或生命周期状态。
- classification 决定 transport、日志、访问和保留策略；未知分级拒绝发布。
- 失败重试不得修改原事件；重试元数据保存在 delivery record。

## AgentRun Public SSE

AgentRun 面向浏览器的事件流采用 AG-UI 事件名称，并额外携带 AtlasMind `metadata`：
`schemaVersion`、`eventId`、单调递增的 per-run `sequence`、`runId`、`correlationId`、可选
`traceId` 和固定的 `visibility=PUBLIC`。客户端使用 SSE `id`、`after` 或 `Last-Event-ID`
恢复遗漏事件。

`knowledge_search` 内部 Retrieval Workflow 使用 `ACTIVITY_SNAPSHOT`，其中
`activityType=atlasmind.retrieval`。同一个活动从 `RUNNING` 更新为终态时复用稳定
`messageId`；`parentMessageId` 指向外层 Tool Call/RunStep。允许公开的内容仅包括：

- 固定阶段：`PLAN`、`QUERY_PROCESSING`、`RETRIEVAL`、`FUSION`、`RERANK`、`EVIDENCE`、`WORKFLOW`；
- 服务器注册的 Strategy ID、活动状态和确定性中文摘要；
- 非负整数形式的候选数、Evidence 数、调用次数、查询表达数量和毫秒耗时；
- 通过确定性映射的降级代码。

不得发送原始或改写 query、HyDE 文本、metadata filter 值、Prompt、隐藏推理、Evidence
正文、scope/AuthContext、相似度分数或模型原始 reason。LangGraph 原生 `debug`、`tasks`、
`updates` 和完整 state 不能直接转发到 PUBLIC SSE；必须先转换为上述白名单 Activity。

## Required Event Families

### Knowledge and Projection

- `knowledge.document-version.created.v1`
- `knowledge.document-version.metadata-confirmed.v1`
- `knowledge.document-version.revoked.v1`
- `knowledge.document-version.activated.v1`
- `knowledge.projection.requested.v1`
- `knowledge.projection.ready.v1`
- `knowledge.projection.failed.v1`

`projection.requested` payload 包含 document version、projection type、generation、adapter version 和
idempotency key。worker 完成后只能提交当前 generation 的结果；过期 generation 标记 RETIRED。

### Agent and Tool

- `agent.run.queued.v1`
- `agent.run.cancel-requested.v1`
- `agent.run.completed.v1`
- `agent.run.failed.v1`
- `tool.invocation.requested.v1`
- `tool.approval.requested.v1`
- `tool.approval.decided.v1`
- `tool.invocation.completed.v1`
- `tool.invocation.failed.v1`

Tool 事件只包含 capability、规范化输入摘要和受控 input reference。Approval 决定事件包含决定、
审批者、nonce 摘要和 Grant reference，不包含可重放凭证正文。

### Evaluation

- `evaluation.run.queued.v1`
- `evaluation.run.completed.v1`
- `evaluation.run.invalid.v1`

Evaluation 事件必须引用 dataset、knowledge snapshot、policy、index、model、prompt 和 evaluator 版本。

## Audit Event

Audit Event 不得依赖可采样 telemetry，至少包含：

```json
{
  "event_id": "uuid",
  "event_type": "authorization.denied.v1",
  "occurred_at": "2026-08-22T10:00:00Z",
  "actor_principal_id": "opaque-id",
  "correlation_id": "uuid",
  "resource": {"type": "KnowledgeScope", "id": "opaque-id"},
  "decision": "DENY",
  "reason_code": "SCOPE_NOT_GRANTED",
  "payload_digest": "sha256:...",
  "previous_hash": "sha256:...",
  "classification": "CONFIDENTIAL"
}
```

- reason code 稳定但不得向非授权用户揭示受限资源细节。
- 知识变更、授权拒绝、高风险工具、审批、审计/trace/评估访问都必须产生事件。
- 防篡改存储和保留策略由企业治理决定；普通用户不得修改或读取他人事件。

## OpenTelemetry Correlation

所有 API、worker、Agent step、Retrieval、Tool 和 evaluation span 传播 W3C Trace Context，并带有：

- `atlasmind.correlation_id`
- `atlasmind.run_id`（适用时）
- `atlasmind.step_id`（适用时）
- `atlasmind.capability.name` / `version`（适用时）
- `atlasmind.policy.version`
- `atlasmind.outcome`
- `atlasmind.error.code`（失败时）

禁止默认记录 subject 明文、scope 名称、query、chunk 正文、prompt、answer、tool secret 或 Approval
Grant。需要内容调试时使用受控引用，并遵循独立授权、脱敏和保留策略。

## Consumer Semantics

1. 读取事件并检查 schema version、classification 和最大 payload 大小。
2. 以 event ID 查询 delivery record；已成功处理则确认而不重复副作用。
3. 加载 aggregate 当前状态，拒绝过期 generation 或不合法状态迁移。
4. 执行有界、幂等处理并写入结果和下游 outbox 事件。
5. 同一事务记录 delivery outcome；外部 side-effect 使用业务 idempotency key。
6. 可重试错误按有界退避重试；永久错误进入受控 dead-letter 状态和告警。

## Contract Tests

- 重复事件、乱序 generation、未知 schema、超大 payload 和未知 classification 均安全处理。
- 文档撤销先阻止读取，即使投影删除事件延迟或重复。
- worker 崩溃后租约恢复不产生重复 active projection 或外部副作用。
- correlation ID 从 API 贯穿 outbox、worker、Agent、Tool、Evaluation 和 Audit。
- telemetry 采样不会导致必要审计事件丢失。
- payload 与 exporter 中的凭据、秘密和禁止正文 marker 泄露次数为 0。
