# Data Model: 企业级 Agentic RAG 知识平台

## Modeling Rules

- PostgreSQL 是身份映射、授权、文档生命周期、运行状态、审批、评估和审计索引的规范事实源。
- `DocumentVersion` 不可变；向量、关键词和图索引是带 generation 的可重建投影。
- 所有用户可见证据都必须携带规范 ID、来源版本、定位信息和知识范围。
- 外部身份、模型、对象存储、向量和图数据库的内部 ID 不得成为公共 API 标识。
- 所有主键使用不可枚举 ID；所有时间使用 UTC；状态变化记录版本和操作者。
- 软删除只控制业务可见性；物理删除遵循企业数据治理和审计保留政策。

## Identity and Authorization

### Principal

企业身份在平台中的稳定映射，不保存可由请求方自行声明的权限。

| Field | Description | Validation |
|-------|-------------|------------|
| `id` | 平台主体 ID | 不可枚举、不可变 |
| `issuer` | 可信身份发行方 | 必须位于批准列表 |
| `subject` | 发行方内唯一 subject | 与 issuer 联合唯一 |
| `display_name` | 用于授权界面的显示名称 | 不得作为鉴权依据 |
| `status` | ACTIVE、SUSPENDED、REVOKED | 非 ACTIVE 必须拒绝访问 |
| `authz_revision` | 权限版本 | 每次角色/范围变化递增 |
| `created_at` / `updated_at` | 生命周期时间 | UTC |

### Role

企业职责集合，例如员工、知识管理员、运营人员或审计人员。

| Field | Description | Validation |
|-------|-------------|------------|
| `id` | 角色 ID | 不可变 |
| `code` | 稳定角色代码 | 唯一、不可由用户请求创建 |
| `name` | 角色名称 | 必填 |
| `status` | ACTIVE、RETIRED | RETIRED 不产生授权 |

### KnowledgeScope

知识可发现、检索、引用、治理和审计的边界，可代表部门、项目、业务域或保密级别。

| Field | Description | Validation |
|-------|-------------|------------|
| `id` | 范围 ID | 不可变 |
| `code` | 企业稳定代码 | 唯一 |
| `name` | 范围名称 | 必填 |
| `parent_id` | 可选父范围 | 不允许循环 |
| `classification` | 企业数据分级 | 必须来自批准枚举 |
| `status` | ACTIVE、REVOKED | REVOKED 立即不可见 |
| `policy_revision` | 范围策略版本 | 策略变化递增 |

### RoleAssignment

把 Principal 关联到 Role，可设置生效和失效时间。

| Field | Description | Validation |
|-------|-------------|------------|
| `principal_id` | 主体 | 必须 ACTIVE |
| `role_id` | 角色 | 必须 ACTIVE |
| `valid_from` / `valid_until` | 有效窗口 | 结束必须晚于开始 |
| `source` | IAM 同步或授权工单 | 必须可审计 |

### ScopeGrant

角色或主体对 KnowledgeScope 的具体动作授权。

| Field | Description | Validation |
|-------|-------------|------------|
| `subject_type` / `subject_id` | ROLE 或 PRINCIPAL | 引用对象必须有效 |
| `scope_id` | 知识范围 | 必须 ACTIVE |
| `actions` | DISCOVER、READ、CITE、MANAGE、AUDIT | 最小权限集合 |
| `valid_from` / `valid_until` | 有效窗口 | 每次请求按当前时间检查 |
| `revision` | 授权修订号 | 变化使相关缓存失效 |

`AuthContext` 是每次请求生成的不可变值对象，包含 principal、角色、可执行动作、scope、
authz/policy revision 与 correlation ID；它不由公共请求体提供，也不作为长期权限事实源。

## Knowledge and Ingestion

### KnowledgeDocument

逻辑知识对象，聚合多个不可变版本。

| Field | Description | Validation |
|-------|-------------|------------|
| `id` | 文档 ID | 不可枚举 |
| `source_key` | 企业来源系统中的稳定业务键 | 同一来源内唯一 |
| `title` | 展示标题 | 必填 |
| `owner_principal_id` | 知识负责人 | 必须存在 |
| `status` | ACTIVE、REVOKED、DELETED | 非 ACTIVE 不可检索 |
| `active_version_id` | 当前可检索版本 | 只能指向 SEARCHABLE 版本 |
| `created_at` / `updated_at` | 生命周期时间 | UTC |

### DocumentVersion

一次不可变内容版本，是引用、去重、索引和审计的基础。

| Field | Description | Validation |
|-------|-------------|------------|
| `id` | 版本 ID | 不可变 |
| `document_id` | 逻辑文档 | 必填 |
| `version_label` | 来源版本或平台版本 | 同一文档内唯一 |
| `content_hash` | 原始内容摘要 | 必填，不以文件名去重 |
| `object_key` | 对象存储定位 | 必须绑定 content hash |
| `media_type` / `size_bytes` | 文件类型和大小 | 必须在支持范围内 |
| `metadata_schema_version` | 元数据 schema 版本 | 必填 |
| `lifecycle_state` | 见状态机 | 只有 SEARCHABLE 可激活 |
| `created_by` / `created_at` | 创建者与时间 | 可审计 |
| `supersedes_version_id` | 被替代版本 | 不允许形成循环 |

DocumentVersion 与 KnowledgeScope 为多对多关系，每项关联记录来源、授予者和策略修订号。

迁移0017增加可更新的`build_profile JSONB`，记录可重建投影的parser/chunker/lexical版本、模型身份/维度和构建指标；不改变原始内容版本的不可变约束。只重算旧投影时保留原文与引用，未知解析版本明确记为`legacy-unknown`。

### DocumentMetadata

经 schema 管理的业务元数据值。

| Field | Description | Validation |
|-------|-------------|------------|
| `document_version_id` | 所属版本 | 必填 |
| `key` | 元数据字段 | 必须出现在当前 schema |
| `value` | 类型化值 | 通过字段类型和允许值校验 |
| `source` | USER、FILE、BUSINESS、RULE、MODEL | 必填 |
| `confidence` | 自动提取置信度 | 0 到 1；人工输入可为空 |
| `review_status` | PENDING、CONFIRMED、REJECTED | 关键字段必须 CONFIRMED |
| `evidence_locator` | 自动提取依据 | 自动来源时必填 |

### KnowledgeChunk

可检索内容单元，始终绑定不可变版本和原文位置。

| Field | Description | Validation |
|-------|-------------|------------|
| `id` | 规范 Chunk ID | 不可变 |
| `document_version_id` | 来源版本 | 必须存在 |
| `ordinal` | 版本内顺序 | 与版本联合唯一 |
| `source_locator` | 页码、段落、字符范围等 | 必须可定位引用 |
| `content` | 规范化文本 | 不得为空 |
| `content_hash` | 片段摘要 | 必填 |
| `token_count` | 预算估算 | 非负 |
| `language` | 语言标记 | 支持中英文基准分组 |
| `status` | ACTIVE、REVOKED | 非 ACTIVE 不进入候选 |

Chunk 继承版本的全部 KnowledgeScope，不允许投影扩大范围。

迁移0017为`knowledge_chunks`增加可空`embedding_profile`、`lexical_version`和`section_key`。生产向量检索同时匹配模型身份及维度；空身份旧块须重算。`section_key`来自新解析器章节/来源，不推断旧块章节。活动块`search_vector`有GIN索引；Jieba分词文本用于索引，引用仍绑定规范正文。

`knowledge_embedding_cache`以`(profile,scope_key,content_digest)`为复合主键，保存dimension、embedding和created_at；scope_key是完整实际scope集合的摘要，不用请求者更大的授权范围代替。仅复用完全相同输入的模型向量，不保存正文、不输出为证据、不绕过文档生命周期；当前无自动淘汰。查询向量另用有界进程内缓存，每次检索仍查询活动/授权状态。

### Projection

向量、关键词、对象解析产物或图索引的可重建状态。

| Field | Description | Validation |
|-------|-------------|------------|
| `id` | 投影记录 ID | 不可变 |
| `document_version_id` | 来源版本 | 必填 |
| `type` | OBJECT、LEXICAL、VECTOR、GRAPH | 枚举 |
| `generation` | 构建代次 | 同一版本/type 唯一 |
| `adapter_version` | 适配器/模型版本 | 必填 |
| `state` | PENDING、BUILDING、READY、FAILED、RETIRED | 见状态机 |
| `record_count` | 派生记录数 | 非负 |
| `error_code` / `error_detail_ref` | 失败诊断 | FAILED 时必填 |

### IngestionJob

持久、可重试的导入工作流实例。

| Field | Description | Validation |
|-------|-------------|------------|
| `id` | Job ID | 不可枚举 |
| `document_version_id` | 处理版本 | 必填 |
| `state` | 见状态机 | 必填 |
| `current_stage` | 当前处理阶段 | 与 state 一致 |
| `attempt` / `max_attempts` | 重试信息 | attempt 不得超过上限 |
| `idempotency_key` | 去重键 | 同一版本和流程唯一 |
| `lease_owner` / `lease_until` | worker 租约 | 过期后可重新领取 |
| `failure_code` / `failure_detail_ref` | 失败诊断 | FAILED 时必填 |
| `created_at` / `started_at` / `finished_at` | 时间 | UTC 且顺序有效 |

## Retrieval, Graph, and Policy

### RetrievalPolicy

决定后端、融合、重排和增强策略的版本化配置。

| Field | Description | Validation |
|-------|-------------|------------|
| `id` / `version` | 策略与版本 | 组合唯一、发布后不可变 |
| `status` | DRAFT、ACTIVE、RETIRED | 同一用途仅一个 ACTIVE |
| `task_types` | 适用任务类型 | 必须来自批准枚举 |
| `enabled_backends` | 允许的 Retrieval Backend | 必须已注册 |
| `enabled_strategies` | Rewrite、Self Query、HyDE、Compression 等 | 必须符合阶段开关 |
| `budgets` | 候选、延迟、token、成本上限 | 均为正数 |
| `fusion` / `rerank` | 融合和重排配置 | 不暴露数据库特定 score |
| `created_by` / `approved_by` | 创建和批准者 | ACTIVE 前必须批准 |

### GraphEntity

从企业知识中规范化的实体。

| Field | Description | Validation |
|-------|-------------|------------|
| `id` | 规范实体 ID | 不使用 Neo4j 内部 ID |
| `entity_type` | 业务类型 | 受 schema 管理 |
| `canonical_name` | 规范名称 | 必填 |
| `aliases` | 别名集合 | 规范化且可审查 |
| `status` | ACTIVE、MERGED、REVOKED | MERGED 必须指向目标实体 |
| `extraction_version` | 抽取规则/模型版本 | 必填 |

### EntityMention

实体与来源 Chunk 的证据关联。

| Field | Description | Validation |
|-------|-------------|------------|
| `entity_id` / `chunk_id` | 实体与片段 | 必须有效 |
| `source_locator` | 片段内位置 | 必须可定位 |
| `confidence` | 抽取置信度 | 0 到 1 |
| `review_status` | AUTO、CONFIRMED、REJECTED | REJECTED 不参与结论 |
| `scope_ids` | 继承范围 | 不得宽于来源 Chunk |

### GraphRelation

两个实体间有证据支持的有向关系。

| Field | Description | Validation |
|-------|-------------|------------|
| `id` | 规范关系 ID | 不使用图数据库内部 ID |
| `source_entity_id` / `target_entity_id` | 关系端点 | 不得相同，除非类型允许自环 |
| `relation_type` | 关系类型 | 受 schema 管理 |
| `valid_from` / `valid_until` | 业务有效期 | 时间顺序有效 |
| `confidence` | 关系置信度 | 0 到 1 |
| `status` | ACTIVE、CONFLICTED、REVOKED | CONFLICTED 不得呈现为单一事实 |
| `extraction_version` | 抽取版本 | 必填 |

### RelationEvidence

GraphRelation 与一个或多个 Chunk 的来源关联；每条可披露路径上的 Relation 必须至少有一条当前
授权且有效的 RelationEvidence。

## Capabilities, Runs, and Approvals

### CapabilityDefinition

受控 Retrieval 或 Tool 的注册描述。

| Field | Description | Validation |
|-------|-------------|------------|
| `id` / `version` | 稳定名称与版本 | 组合唯一 |
| `kind` | RETRIEVAL、SQL、EXTERNAL | 枚举 |
| `input_schema` / `output_schema` | 类型化契约引用 | 必须可验证 |
| `required_actions` | 所需动作 | 与 ScopeGrant 兼容 |
| `risk_level` | LOW、MEDIUM、HIGH | side-effect 必须 HIGH |
| `side_effect` | 是否改变外部状态 | HIGH 时必须审批 |
| `timeout_ms` / `max_result_bytes` | 执行预算 | 正数且有全局上限 |
| `status` | ACTIVE、DISABLED、RETIRED | 非 ACTIVE 不可调用 |

### Conversation（2026-10-13 已实现增量）

`conversations` 保存 `id`、可信 `principal_id`、首问派生标题、`created_at` 和 `updated_at`。
`agent_runs` 增量保存 `conversation_id`、`turn_index` 与 `query_text`；用户消息来自 `query_text`，
助手消息继续读取原 `answer` 和 Citation，运行失败/取消也保留所属轮次。问题是数据库中的受控文本，
不能宣称已经加密；保留/删除仍需遵循企业数据政策。

- 创建运行与分配会话/轮次在同一事务完成；行锁保证同一会话只有一轮在途，轮次组合唯一。
- `(conversation_id, principal_id)` 外键与所有读写路径的身份检查共同约束归属。
- `0016` 将每条旧运行独立映射到同 ID 会话，`query_text=NULL` 明确表示缺失，不重建原文或推测旧轮次。
- 详情返回最新一页并按轮次正序展示，以 `before` 轮次游标读取更早记录；会话列表支持 `limit/offset`。
- `conversationId` 仅用于记录归属；本次不把保存的历史消息自动送入 Agent Context。

### AgentRun

一次用户请求的完整可追踪状态。

| Field | Description | Validation |
|-------|-------------|------------|
| `id` / `correlation_id` | 运行和关联 ID | 唯一 |
| `principal_id` | 发起者 | 必填 |
| `authz_revision` | 发起时权限版本 | 输出前重新检查当前版本 |
| `query_ref` | 加密或受控问题内容引用 | 遵循数据政策 |
| `task_type` | SIMPLE、MULTI_SOURCE、GRAPH | 必填 |
| `policy_id` / `policy_version` | 检索策略 | 必填 |
| `state` | 见状态机 | 必填 |
| `budgets` / `usage` | 步骤、时间、token、工具和结果预算 | usage 不得超过上限 |
| `final_answer_ref` | 受控答案引用 | 完成时可用 |
| `failure_code` / `degradation_reason` | 失败或降级 | 状态匹配 |
| `created_at` / `finished_at` | 时间 | UTC |

### RunStep

AgentRun 中可审计的计划、检索、工具或综合步骤。

| Field | Description | Validation |
|-------|-------------|------------|
| `id` / `run_id` / `ordinal` | 步骤标识 | run 内 ordinal 唯一 |
| `kind` | PLAN、RETRIEVAL、TOOL、COMPOSE、VERIFY | 枚举 |
| `capability_id` / `version` | 可选能力 | RETRIEVAL/TOOL 时必填 |
| `state` | PENDING、RUNNING、WAITING_APPROVAL、SUCCEEDED、FAILED、SKIPPED | 见状态机 |
| `input_digest` / `result_ref` | 最小必要记录 | 不保存隐藏思维链 |
| `started_at` / `finished_at` | 时间 | UTC |

### EvidenceRecord

被运行接收并允许进入答案综合的证据包。

| Field | Description | Validation |
|-------|-------------|------------|
| `id` / `run_id` / `step_id` | 归属 | 必填 |
| `source_type` / `source_id` | DOCUMENT、STRUCTURED、GRAPH、EXTERNAL | 必填 |
| `source_version` / `source_locator` | 版本与位置 | 用户可见 claim 时必填 |
| `scope_ids` | 证据范围 | 必须为 AuthContext 子集 |
| `content_ref` / `content_digest` | 受控内容引用与摘要 | 必填 |
| `relevance_signals` | 后端无关相关性信号 | 不作为权限依据 |
| `validity` | VALID、CONFLICTED、STALE、REJECTED | 仅 VALID/CONFLICTED 可披露 |
| `verified_at` / `authz_revision` | 最后复核 | 输出前必须为当前版本 |

### Citation

把最终答案中的 claim 与一个或多个 EvidenceRecord 绑定。

| Field | Description | Validation |
|-------|-------------|------------|
| `id` / `run_id` | 引用标识 | 必填 |
| `claim_locator` | 答案中的陈述位置 | 必填 |
| `evidence_ids` | 支持证据 | 至少一项 |
| `source_display` | 授权用户可见来源信息 | 不得泄露受限元数据 |
| `support_status` | SUPPORTED、PARTIAL、CONFLICTED | 必填 |

### ToolInvocation

执行网关中的一次工具调用。

| Field | Description | Validation |
|-------|-------------|------------|
| `id` / `run_step_id` | 调用标识 | 必填 |
| `capability_id` / `version` | 工具 | 必须 ACTIVE |
| `principal_id` / `authz_revision` | 执行身份 | 必须与 run 一致 |
| `normalized_input_digest` | 规范化参数摘要 | 审批绑定依据 |
| `state` | 见状态机 | 必填 |
| `approval_request_id` | 高风险调用审批 | side-effect 时必填 |
| `result_ref` / `error_code` | 结果或错误 | 状态匹配 |
| `idempotency_key` | 防止重复副作用 | side-effect 时必填 |

### ApprovalRequest

高风险工具调用的人工审批挑战和决定。

| Field | Description | Validation |
|-------|-------------|------------|
| `id` | 审批 ID | 不可枚举 |
| `invocation_id` | 待执行调用 | 一对一 |
| `principal_id` / `capability_id` | 发起者与工具 | 必须绑定 |
| `target_resource` | 目标资源摘要 | 必填且不可换参 |
| `input_digest` / `correlation_id` | 参数和运行绑定 | 必填 |
| `state` | PENDING、APPROVED、DENIED、EXPIRED、CONSUMED | 见状态机 |
| `expires_at` / `nonce_hash` | 时限与一次性 nonce | 必填 |
| `decided_by` / `decided_at` | 审批者与时间 | 决定后必填 |
| `decision_reason` | 审批说明 | DENIED 时必填 |

## Evaluation and Audit

### EvaluationDataset

版本化评估集合，关联不可变知识快照、策略与隐藏级别。

| Field | Description | Validation |
|-------|-------------|------------|
| `id` / `version` | 数据集与版本 | 组合唯一、发布后不可变 |
| `category` | GOLDEN、AUTHZ、INJECTION、FAILURE、GRAPH、PERFORMANCE | 枚举 |
| `knowledge_snapshot` | 文档版本/hash 清单 | 必填 |
| `visibility` | TUNING、HIDDEN_REGRESSION | 隐藏集不可用于调优 |
| `data_classification` | 数据分级 | 必填 |
| `status` | DRAFT、APPROVED、RETIRED | 仅 APPROVED 可作为门禁 |

### EvaluationCase

| Field | Description | Validation |
|-------|-------------|------------|
| `dataset_id` / `ordinal` | 所属与顺序 | 联合唯一 |
| `question` | 测试问题 | 必填 |
| `persona_fixture` / `allowed_scope_ids` | 权限 fixture | 必填 |
| `expected_evidence` | 可接受证据 | 正常题必填 |
| `forbidden_evidence` | 禁止证据 marker | 权限题必填 |
| `answer_points` | 答案要点 | 可选 |
| `expected_behavior` | ANSWER、INSUFFICIENT、CONFLICT、DENY、APPROVAL | 必填 |

### EvaluationRun and EvaluationResult

EvaluationRun 记录代码、数据集、知识快照、索引 generation、policy、model、prompt、evaluator 和随机
参数版本及状态。EvaluationResult 按 case/metric 记录原始分、阈值、通过状态、失败样本引用和专家
复核结果。安全指标为零容忍，不可被平均质量分抵消。

### AuditEvent

防篡改审计事件，覆盖认证、授权拒绝、知识变更、高风险工具、审批、运行记录访问和评估数据访问。

| Field | Description | Validation |
|-------|-------------|------------|
| `id` / `occurred_at` | 事件标识与时间 | 不可变、UTC |
| `event_type` | 稳定事件类型 | 版本化枚举 |
| `actor_principal_id` | 行为主体 | 系统行为使用受控 service identity |
| `correlation_id` | 关联运行 | 适用时必填 |
| `resource_type` / `resource_id` | 受影响资源 | 最小必要 |
| `decision` / `reason_code` | 允许、拒绝或变化 | 不包含敏感资源细节 |
| `payload_digest` / `previous_hash` | 完整性链 | 必填 |
| `classification` | 事件分级 | 决定访问和保留策略 |

### OutboxEvent

与规范状态同事务写入的异步事件，包含事件 ID、aggregate、类型、schema version、payload ref、
attempt、available time 和 published time。消费者以事件 ID 和 projection generation 幂等处理。

## State Transitions

### DocumentVersion

```text
UPLOADED → VALIDATING → PARSING → CHUNKING → METADATA_REVIEW
         → LEXICAL_INDEXING → VECTOR_INDEXING → SEARCHABLE

任一处理中状态 → FAILED → VALIDATING（人工修正后重试）
SEARCHABLE → SUPERSEDED | REVOKED | DELETED
```

- 关键元数据未确认时停在 `METADATA_REVIEW`。
- Phase 3 图投影独立构建，不得阻止 Phase 1 已批准的文档检索；需要图检索的策略只选择 GRAPH_READY 版本。
- `REVOKED` 同步停止所有检索，派生投影异步清理。

### Projection

```text
PENDING → BUILDING → READY → RETIRED
                 ↘ FAILED → PENDING（新 attempt）
```

只有当前 active generation 的 READY 投影可用；新 generation 完成前保留旧 generation，但授权和
文档生命周期始终以 PostgreSQL 当前状态为准。

### AgentRun

```text
QUEUED → RUNNING → COMPLETED
                 → PARTIAL
                 → WAITING_APPROVAL → RUNNING
                 → FAILED
                 → TIMED_OUT
                 → CANCELLED
```

- 达到预算上限必须进入 PARTIAL、TIMED_OUT 或 FAILED，不能继续隐式循环。
- 输出前权限变化导致证据不可见时，重新综合剩余证据或明确失败。

### ToolInvocation and ApprovalRequest

```text
ToolInvocation: PLANNED → AUTHORIZED → WAITING_APPROVAL → EXECUTING → SUCCEEDED
                            ↘ DENIED             ↘ FAILED | TIMED_OUT

ApprovalRequest: PENDING → APPROVED → CONSUMED
                        → DENIED
                        → EXPIRED
```

- Approval Grant 只能消费一次，且必须匹配 subject、tool、参数摘要、目标、correlation ID 和有效期。
- Tool 参数变化必须创建新的 ApprovalRequest。

### EvaluationRun

```text
QUEUED → RUNNING → PASSED | FAILED | INVALID
```

缺少版本信息、知识快照或授权 fixture 的运行标记 `INVALID`，不能与历史基线比较。

## Cross-Store Ownership

| Data | System of Record | Derived Projection |
|------|------------------|--------------------|
| Principal、Role、Scope、Grant | PostgreSQL / approved IAM sync | 授权缓存（版本化、短 TTL） |
| Document、Version、Chunk、Metadata | PostgreSQL | MinIO 对象、pgvector、lexical index |
| Entity、Relation、Evidence | PostgreSQL provenance records | Neo4j/LightRAG graph generation |
| AgentRun、Step、Approval、Evaluation | PostgreSQL | OTel telemetry、可选 LangSmith view |
| AuditEvent | 受控审计存储及 PostgreSQL 索引 | 只读报告视图 |

恢复以 PostgreSQL 规范状态和原始对象为基线；向量、关键词和图 projection 必须支持 reconciliation
和完全重建。
