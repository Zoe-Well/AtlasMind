# Capability Contract

## Purpose

本契约定义 Agent 决策层与 Retrieval/Tool 执行层之间的唯一调用边界。Agent 只能提交已注册、
类型化的 Capability Request；执行层拥有授权、风险、审批、预算、执行和结果规范化职责。

## Trusted Auth Context

`AuthContext` 由 API 或受信 worker 在验证企业身份后创建，不得来自公共请求体、模型输出、会话
历史或工具参数。

```json
{
  "principal_id": "opaque-id",
  "role_codes": ["employee"],
  "scope_ids": ["opaque-scope-id"],
  "allowed_actions": ["knowledge:read", "knowledge:cite"],
  "authz_revision": 42,
  "policy_revision": 9,
  "correlation_id": "uuid",
  "issued_at": "2026-08-22T10:00:00Z",
  "expires_at": "2026-08-22T10:05:00Z"
}
```

执行前必须验证上下文签名或受信传递方式、有效期、主体状态和 revision。任何缺失、伪造、过期
或无法加载当前授权的情况都返回 deny，不得退化成无范围查询。

## Capability Descriptor

每个注册能力必须提供不可变版本描述：

| Field | Required behavior |
|-------|-------------------|
| `name` / `version` | 稳定且唯一；公共流程不得使用底层实现名称 |
| `kind` | RETRIEVAL、STRUCTURED_QUERY 或 EXTERNAL_TOOL |
| `input_schema` / `output_schema` | 严格 schema；禁止未声明字段 |
| `required_actions` | 执行所需授权动作 |
| `supported_scope_types` | 能力能安全过滤的范围类型 |
| `risk_level` | LOW、MEDIUM、HIGH |
| `side_effect` | 是否会改变企业或外部系统状态 |
| `timeout_ms` | 硬超时 |
| `max_result_bytes` / `max_items` | 结果上限 |
| `retry_policy` | 是否可重试及最大次数 |
| `idempotency_required` | side-effect 必须为 true |
| `telemetry_policy` | 可记录字段 allowlist 与脱敏规则 |

未知、停用或版本不匹配的 capability 必须拒绝。

## Capability Request

```json
{
  "request_id": "uuid",
  "run_id": "uuid",
  "step_id": "uuid",
  "capability": {"name": "knowledge.search", "version": "1"},
  "auth_context_ref": "server-owned-reference",
  "input": {},
  "budget": {
    "timeout_ms": 5000,
    "max_items": 20,
    "max_result_bytes": 65536
  },
  "idempotency_key": null,
  "approval_grant_ref": null
}
```

- `input` 不得包含 subject、role、scope 或“跳过权限”等控制字段。
- 请求预算不得高于 Capability Descriptor 或 AgentRun 的剩余预算。
- side-effect capability 必须提供 idempotency key，并在执行前取得有效 Approval Grant。

## Execution Order

1. 验证请求和 capability schema。
2. 从受信引用加载当前 AuthContext，并检查有效期和 revision。
3. 计算 capability 所需动作与当前 scope 的交集；deny by default。
4. 检查风险、预算、速率、并发和审批。
5. 使用授权范围在存储查询阶段过滤并执行。
6. 规范化并限量结果；拒绝不符合输出 schema 的数据。
7. 对返回的来源、版本和 scope 进行当前权限复核。
8. 写入最小必要 telemetry 和独立审计事件。
9. 返回 Capability Result；失败或未验证结果不得进入证据集合。

## Evidence Envelope

所有能支持用户可见结论的 Retrieval/Tool 结果必须转换为 Evidence Envelope。

```json
{
  "evidence_id": "uuid",
  "source": {
    "type": "DOCUMENT",
    "canonical_id": "opaque-id",
    "version": "opaque-version",
    "locator": "page=4;paragraph=2"
  },
  "scope_ids": ["opaque-scope-id"],
  "content_ref": "server-owned-reference",
  "content_digest": "sha256:...",
  "facts": [],
  "relevance": {
    "signals": {},
    "retrieval_method": "hybrid"
  },
  "validity": "VALID",
  "authz_revision": 42,
  "verified_at": "2026-08-22T10:00:01Z"
}
```

- `source`、`version`、`locator` 和 `scope_ids` 必填。
- score 只作为相关性信号，不得作为权限或跨后端稳定语义。
- `CONFLICTED` 证据可以披露冲突，不能独自支持确定结论。
- `STALE`、`REJECTED` 或无法定位来源的结果不能进入最终答案。

## Capability Result

成功结果包含 `status=SUCCEEDED`、Evidence Envelope 列表、用量和非敏感警告。失败结果包含稳定
reason code、retryable 和受控诊断引用，不返回受限资源存在性、原始异常或秘密。

稳定 reason code 至少包括：

- `INVALID_REQUEST`
- `AUTH_CONTEXT_INVALID`
- `ACTION_NOT_ALLOWED`
- `APPROVAL_REQUIRED`
- `APPROVAL_INVALID`
- `BUDGET_EXCEEDED`
- `SOURCE_UNAVAILABLE`
- `RESULT_INVALID`
- `TIMED_OUT`
- `INTERNAL_ERROR`

## Structured Query Rules

- 模型只能选择注册数据集、指标、维度、过滤和参数，不能提交任意 SQL。
- 执行层把类型化语义请求编译为参数化只读查询。
- 数据集声明行级/列级权限、最大时间、最大行数和允许聚合。
- 查询计划或结果超限时拒绝，不自动放宽过滤。
- 返回事实必须携带数据集版本、查询摘要和可披露来源定位。

## Approval Challenge and Grant

Approval Challenge 必须绑定：请求主体、capability 与版本、规范化参数摘要、目标资源、run/correlation
ID、过期时间和一次性 nonce。Approval Grant 由受信审批服务签发，执行层必须验证：

- 审批者具有批准该动作和目标的权限；
- Grant 与当前主体、capability、参数、目标和 correlation 完全匹配；
- Grant 未过期、未消费且 nonce 未重放；
- AuthContext 和工具版本在审批后未发生不兼容变化。

任一字段变化都必须创建新挑战。消费与 side-effect 的幂等记录必须在可恢复边界内完成。

## Contract Tests

- 缺失、伪造、过期 AuthContext 和权限 revision 变化全部 fail closed。
- scope 降级后旧缓存、旧 Evidence Envelope 和旧引用不可使用。
- backend 不得返回授权范围之外的候选、计数、图路径或错误细节。
- 非法字段、超长输入、结果超限、超时和不符合 schema 的结果被隔离。
- side-effect 工具在无审批、审批过期、重放、换参或跨用户时全部拒绝。
- 所有成功 Evidence Envelope 均含来源、版本、locator、scope 和当前 authz revision。

