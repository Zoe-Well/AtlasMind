# Tasks: 企业级 Agentic RAG 知识平台

**Input**: Design documents from `specs/001-enterprise-agentic-rag/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Tests**: 权限、数据隔离、高风险工具、写入/迁移、复杂状态、重要回归和 RAG 质量测试由宪法
强制要求。每个用户故事先写测试并确认失败，再实现功能。

**Organization**: 任务按用户故事分组；Setup 和 Foundational 是共享前置，之后每个故事形成可独立
验收的增量。任务路径遵循 `plan.md` 中的模块化单体结构。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可在同一阶段与其他标记任务并行，文件不同且无未完成依赖。
- **[Story]**: 用户故事标签；Setup、Foundational 和 Final 阶段不使用。
- 所有任务均包含明确文件路径。

## Phase 1: Setup

**Purpose**: 建立 Python 3.14 可验证开发环境、包结构和本地基础设施。

- [X] T001 在 `pyproject.toml` 配置 Python 3.14 运行依赖、开发依赖组和可锁定版本范围，并验证 FastAPI、LangGraph、SQLAlchemy、pgvector、Neo4j、OpenTelemetry、DeepEval 与文档解析依赖兼容性
- [X] T002 创建模块化包入口 `src/atlasmind/__init__.py`、`src/atlasmind/api/__init__.py`、`src/atlasmind/domain/__init__.py`、`src/atlasmind/application/__init__.py`、`src/atlasmind/infrastructure/__init__.py` 和 `src/atlasmind/workers/__init__.py`
- [X] T003 实现类型化环境配置、秘密引用和进程角色校验 `src/atlasmind/settings.py`
- [X] T004 [P] 配置 PostgreSQL/pgvector、MinIO、Neo4j 和 OpenTelemetry Collector 本地服务 `compose.yaml`
- [X] T005 [P] 提供无真实秘密的配置字段示例 `.env.example`
- [X] T006 [P] 配置 pytest、mypy、ruff、覆盖率和测试 markers `pyproject.toml`
- [X] T007 配置依赖安装、静态检查、单元/契约测试和 YAML 校验流水线 `.github/workflows/ci.yml`
- [X] T008 编写 Python 3.14 关键依赖安装、导入和最小启动 smoke test `tests/contract/test_runtime_compatibility.py`
- [X] T009 更新本地安装、服务启动和验证入口 `README.md`

**Checkpoint**: `uv sync --all-groups`、关键依赖 smoke test 和空测试套件能够执行，基础服务可启动。

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 建立所有用户故事共同依赖的身份、授权、持久化、异步事件、观测和受控能力边界。

**⚠️ CRITICAL**: 本阶段完成前不得开始用户故事实现。

- [X] T010 实现不可枚举 ID、UTC 时间、稳定 reason code 和领域异常基类 `src/atlasmind/domain/common.py`
- [X] T011 实现异步数据库 engine、session、Unit of Work 和事务边界 `src/atlasmind/infrastructure/database.py`
- [X] T012 初始化 Alembic 环境、命名约定和 pgvector extension `migrations/env.py` 与 `migrations/versions/0001_enable_pgvector.py`
- [X] T013 [P] 实现 Principal、Role、KnowledgeScope、RoleAssignment 和 ScopeGrant 领域模型 `src/atlasmind/identity/models.py`
- [X] T014 创建身份、角色、范围、授权及 revision 约束迁移 `migrations/versions/0002_identity_authorization.py`
- [X] T015 [P] 实现企业 OIDC issuer allowlist、JWT 验签和 subject 映射 `src/atlasmind/identity/oidc.py`
- [X] T016 实现不可由请求体覆盖的 AuthContext 构造与 correlation ID 中间件 `src/atlasmind/api/middleware/auth_context.py`
- [X] T017 实现 deny-by-default 动作/范围授权、authz revision 和缓存键策略 `src/atlasmind/identity/authorization.py`
- [X] T018 [P] 编写伪造身份、过期令牌、角色切换、scope 撤销和 fail-closed 契约测试 `tests/security/test_auth_context_and_authorization.py`
- [X] T019 [P] 定义 ObjectStore port 并实现 MinIO/S3 adapter 的不可变对象写入、摘要验证和受控读取 `src/atlasmind/infrastructure/object_store.py`
- [X] T020 [P] 定义 ModelGateway、EmbeddingProvider 和 Reranker typed ports 及确定性测试 adapter `src/atlasmind/infrastructure/ai_ports.py`
- [X] T021 实现持久 Job、lease、attempt 和 idempotency 领域基类 `src/atlasmind/domain/jobs.py`
- [X] T022 创建通用 job、lease、delivery record 和 idempotency 表迁移 `migrations/versions/0003_jobs_delivery.py`
- [X] T023 实现版本化 EventEnvelope、transactional outbox repository 和 payload classification 校验 `src/atlasmind/infrastructure/outbox.py`
- [X] T024 实现 `SKIP LOCKED` worker 领取、续租、重试、退避和 dead-letter 基础循环 `src/atlasmind/workers/base.py`
- [X] T025 [P] 实现 W3C Trace Context、correlation/run/step 属性和 OTel exporter 初始化 `src/atlasmind/observability/telemetry.py`
- [X] T026 [P] 实现日志/trace/exporter 字段 allowlist、摘要和秘密 marker 脱敏 `src/atlasmind/observability/redaction.py`
- [X] T027 实现 AuditEvent 领域模型、防篡改 hash chain 和最小必要 payload `src/atlasmind/observability/audit.py`
- [X] T028 创建审计事件、完整性链和受控访问索引迁移 `migrations/versions/0004_audit_events.py`
- [X] T029 [P] 实现 RFC 9457 Problem Details、稳定公共错误和不可见资源防枚举映射 `src/atlasmind/api/problem_details.py`
- [X] T030 [P] 实现 CapabilityDescriptor、CapabilityRequest、CapabilityResult 和 EvidenceEnvelope schema `src/atlasmind/tools/contracts.py`
- [X] T031 实现 Capability Registry 和“验证→授权→预算→执行→规范化→复核→审计”基础网关 `src/atlasmind/tools/execution_gateway.py`

**Checkpoint**: 可信 AuthContext、范围授权、事务/outbox、worker lease、审计、OTel 和 Capability
执行边界通过契约与安全测试；未知或过期权限一律拒绝。

---

## Phase 3: User Story 1 — 获取可信且有权限的企业知识答案 (Priority: P1) 🎯 MVP

**Goal**: 员工能够在授权企业知识中提问，获得有可定位引用的答案；无证据、冲突和越权场景
安全处理。

**Independent Test**: 使用预置公开、受限、冲突和无答案文档，以两个不同 scope 员工查询；验证
答案、引用、证据不足和所有输出面的零权限泄露，无需依赖导入 UI、Agent 工具或 GraphRAG。

### Tests for User Story 1

- [X] T032 [P] [US1] 按 `contracts/openapi.yaml` 编写创建/读取/取消 AgentRun 的 API 契约测试 `tests/contract/test_agent_runs_api.py`
- [X] T033 [P] [US1] 编写文档候选、prompt、答案、引用、错误和 trace 的权限矩阵测试 `tests/security/test_knowledge_permission_matrix.py`
- [X] T034 [P] [US1] 编写 claim-to-citation-to-source-locator 支持性契约测试 `tests/contract/test_citation_contract.py`
- [X] T035 [P] [US1] 创建基础问答、冲突、无答案和 forbidden marker 回归 fixture `tests/fixtures/evaluation/golden_basic.jsonl`

### Implementation for User Story 1

- [X] T036 [US1] 创建 KnowledgeDocument、DocumentVersion、KnowledgeChunk、RetrievalPolicy、AgentRun、EvidenceRecord 和 Citation 表迁移 `migrations/versions/0005_core_rag_models.py`
- [X] T037 [P] [US1] 实现不可变文档版本、Chunk、Evidence 和 Citation 领域模型及验证 `src/atlasmind/domain/knowledge.py`
- [X] T038 [P] [US1] 实现 RetrievalPolicy 和简单查询预算领域模型 `src/atlasmind/retrieval/policy.py`
- [X] T039 [US1] 实现文档、Chunk、运行、证据和引用 PostgreSQL repository `src/atlasmind/infrastructure/repositories/knowledge.py`
- [X] T040 [P] [US1] 实现 pgvector VectorStore adapter、scope/active-version 前置过滤和后端无关 score 输出 `src/atlasmind/retrieval/vector_pg.py`
- [X] T041 [P] [US1] 实现 LexicalRetriever port、PostgreSQL 首期 adapter 和中英文 tokenizer 接口 `src/atlasmind/retrieval/lexical_pg.py`
- [X] T042 [US1] 实现向量/关键词候选去重、RRF 融合和可配置 top-k `src/atlasmind/retrieval/hybrid.py`
- [X] T043 [P] [US1] 实现 Reranker adapter、结果上限和超时降级 `src/atlasmind/retrieval/reranker.py`
- [X] T044 [US1] 实现查询前 scope/lifecycle/generation 过滤及返回前 authz revision 批量复核 `src/atlasmind/retrieval/authorization.py`
- [X] T045 [US1] 实现基础 Retrieval Pipeline 和版本化策略选择 `src/atlasmind/retrieval/pipeline.py`
- [X] T046 [P] [US1] 实现证据充分性、冲突、陈旧来源和 locator 有效性检查 `src/atlasmind/retrieval/evidence_verifier.py`
- [X] T047 [US1] 实现只消费已授权 EvidenceEnvelope 的答案综合和事实/推断/未知区分 `src/atlasmind/application/answer_composer.py`
- [X] T048 [US1] 实现简单问答 AgentRun 用例、预算、状态和输出前权限复核 `src/atlasmind/application/query_knowledge.py`
- [X] T049 [US1] 实现 AgentRun 创建、读取和取消 REST 路由 `src/atlasmind/api/routes/agent_runs.py`
- [X] T050 [US1] 实现可授权打开的引用定位和不可见来源防枚举 `src/atlasmind/application/citations.py`
- [X] T051 [P] [US1] 实现 Recall@k、MRR/nDCG、证据不足和引用准确性确定性指标 `src/atlasmind/evaluation/basic_metrics.py`
- [X] T052 [US1] 实现仅用于测试的预置知识 fixture loader `tests/fixtures/load_basic_knowledge.py`
- [X] T053 [US1] 完成授权问答、无答案、冲突、撤权竞态和引用端到端测试 `tests/integration/test_authorized_knowledge_answer.py`

**Checkpoint**: US1 可独立演示；SC-001、SC-002、SC-006 与相关 SC-008 场景达到阈值。

---

## Phase 4: User Story 2 — 导入和治理企业知识 (Priority: P2)

**Goal**: 知识管理员能够上传、治理、版本化、重试和撤销知识，只有完整且授权的版本可检索。

**Independent Test**: 上传正常、重复、空、加密和无法解析文件，验证元数据、状态、重试、
generation 切换、撤销和十分钟内可检索目标；不依赖多步骤 Agent、外部工具或图问答。

### Tests for User Story 2

- [X] T054 [P] [US2] 按 OpenAPI 编写文档上传、版本、撤销、job 状态和重试契约测试 `tests/contract/test_knowledge_ingestion_api.py`
- [X] T055 [P] [US2] 编写正常/空/加密/超限/重复文件和元数据确认生命周期测试 `tests/integration/test_ingestion_lifecycle.py`
- [X] T056 [P] [US2] 编写重复 idempotency key、并发重试、旧 generation 和撤销竞态测试 `tests/integration/test_ingestion_idempotency.py`

### Implementation for User Story 2

- [X] T057 [US2] 创建 DocumentMetadata、Projection、IngestionJob、版本 scope 和 projection generation 迁移 `migrations/versions/0006_ingestion_projection.py`
- [X] T058 [P] [US2] 实现元数据来源/审核、Projection 和 IngestionJob 状态机 `src/atlasmind/ingestion/models.py`
- [X] T059 [P] [US2] 实现文件类型、大小、空内容、加密状态、摘要和对象键验证 `src/atlasmind/ingestion/file_validation.py`
- [X] T060 [P] [US2] 定义 Parser port 并实现文本、Markdown、HTML、PDF 和 DOCX adapter `src/atlasmind/ingestion/parsers.py`
- [X] T061 [US2] 实现可复现 Chunking、source locator、语言识别和内容摘要 `src/atlasmind/ingestion/chunking.py`
- [X] T062 [P] [US2] 实现用户/文件/业务/规则/模型元数据合并、schema 校验和关键字段审核 `src/atlasmind/ingestion/metadata.py`
- [X] T063 [US2] 实现 content hash 与 source key 重复检测、不可变版本和 supersedes 规则 `src/atlasmind/application/document_versions.py`
- [X] T064 [US2] 实现上传、job 创建、对象写入意图和 outbox 同事务用例 `src/atlasmind/application/ingest_document.py`
- [X] T065 [US2] 实现 VALIDATING→PARSING→CHUNKING→METADATA→INDEXING 持久 worker `src/atlasmind/workers/ingestion.py`
- [X] T066 [P] [US2] 实现 lexical 和 pgvector projection builder、幂等 generation 写入和记录计数 `src/atlasmind/ingestion/projections.py`
- [X] T067 [US2] 实现必需投影 READY 后 active version/SEARCHABLE 原子切换及旧 generation 退休 `src/atlasmind/ingestion/activation.py`
- [X] T068 [P] [US2] 实现失败重试、lease 恢复、projection reconciliation 和孤立记录清理 `src/atlasmind/ingestion/reconciliation.py`
- [X] T069 [US2] 实现文档上传、版本创建、读取和撤销 REST 路由 `src/atlasmind/api/routes/documents.py`
- [X] T070 [US2] 实现 ingestion job 读取和重试 REST 路由 `src/atlasmind/api/routes/ingestion_jobs.py`
- [X] T071 [US2] 实现元数据审核/修正授权用例与管理路由，并同步契约 `src/atlasmind/api/routes/metadata_review.py` 和 `specs/001-enterprise-agentic-rag/contracts/openapi.yaml`
- [X] T072 [US2] 完成导入、版本切换、撤销即时隐藏、reconciliation 与十分钟目标端到端测试 `tests/integration/test_managed_knowledge_ingestion.py`

**Checkpoint**: US2 可独立管理知识生命周期；失败内容不进入检索，撤销同步生效，SC-003 达标。

---

## Phase 5: User Story 3 — 跨数据源完成多步骤分析 (Priority: P3)

**Goal**: Agent 能够在预算内组合授权文档、结构化数据和外部能力，安全降级，并对高风险副作用
强制人工审批。

**Independent Test**: 使用退款失败率分析 fixture 结合只读指标、技术文档和变更记录；验证能力
选择、步骤追踪、部分失败、预算、审批防绕过和提示注入，不依赖 GraphRAG。

### Tests for User Story 3

- [X] T073 [P] [US3] 编写多来源正常、部分失败、超时和预算耗尽集成测试 `tests/integration/test_multi_source_agent.py`
- [X] T074 [P] [US3] 按 Capability Contract 编写 schema、scope、结果上限和未知工具契约测试 `tests/contract/test_capability_gateway.py`
- [X] T075 [P] [US3] 编写无审批、过期、重放、换参和跨用户 Approval Grant 安全测试 `tests/security/test_tool_approval.py`
- [X] T076 [P] [US3] 编写直接/间接提示注入、工具输出注入和 capability allowlist 回归测试 `tests/security/test_prompt_injection_boundaries.py`

### Implementation for User Story 3

- [X] T077 [US3] 创建 CapabilityDefinition、RunStep、ToolInvocation 和 ApprovalRequest 迁移 `migrations/versions/0007_agent_tools_approvals.py`
- [X] T078 [P] [US3] 实现 AgentRun/RunStep 状态、CapabilityDefinition、ToolInvocation 和 ApprovalRequest 领域模型 `src/atlasmind/agent/models.py`
- [X] T079 [P] [US3] 实现注册数据集、指标、维度、过滤、行列权限和查询预算 schema `src/atlasmind/tools/structured_registry.py`
- [X] T080 [US3] 实现类型化语义请求到参数化只读 SQL 的编译、行数/时间限制和来源摘要 `src/atlasmind/tools/sql_query.py`
- [X] T081 [P] [US3] 实现受控 External API adapter、目标 allowlist、超时、结果限量和幂等 key `src/atlasmind/tools/external_api.py`
- [X] T082 [US3] 实现参数摘要/目标/run 绑定、限时 nonce、审批决定和一次消费服务 `src/atlasmind/tools/approvals.py`
- [X] T083 [US3] 实现 ApprovalRequest 读取和决定 REST 路由 `src/atlasmind/api/routes/approvals.py`
- [X] T084 [P] [US3] 定义 LangGraph 有界 AgentState、步骤预算和 checkpoint schema `src/atlasmind/agent/state.py`
- [X] T085 [US3] 实现意图分类、是否检索、任务分解和确定性 policy 校验节点 `src/atlasmind/agent/planning.py`
- [X] T086 [US3] 实现只发出类型化 CapabilityRequest 的检索/工具节点 `src/atlasmind/agent/capability_nodes.py`
- [X] T087 [US3] 实现证据综合、事实/推断/未知标注和输出前复核节点 `src/atlasmind/agent/composition.py`
- [X] T088 [P] [US3] 实现 LangGraph checkpoint 与 AgentRun/RunStep PostgreSQL repository `src/atlasmind/infrastructure/repositories/agent_runs.py`
- [X] T089 [US3] 实现队列领取、WAITING_APPROVAL 暂停/恢复、取消和超时的 Agent worker `src/atlasmind/workers/agent.py`
- [X] T090 [P] [US3] 实现最大步骤、时间、token、工具次数、结果大小和循环检测 `src/atlasmind/agent/budgets.py`
- [X] T091 [US3] 实现不可用来源隔离、部分结论、阻塞来源影响和失败 reason code `src/atlasmind/agent/degradation.py`
- [X] T092 [US3] 扩展 AgentRun REST 用例支持 AUTO/MULTI_SOURCE、异步状态和 pending approval `src/atlasmind/application/run_agent.py`
- [X] T093 [P] [US3] 实现工具请求、审批、拒绝、执行、失败和结果访问 AuditEvent `src/atlasmind/tools/audit_events.py`
- [X] T094 [US3] 实现不可信文档/工具输出结构化隔离、内容指令忽略和输出敏感复核 `src/atlasmind/agent/untrusted_content.py`
- [X] T095 [P] [US3] 创建多来源、失败降级、审批和注入版本化评估 fixture `tests/fixtures/evaluation/multi_source_and_tools.jsonl`
- [X] T096 [US3] 完成多来源分析、部分失败、预算、审批暂停/恢复和零越权端到端测试 `tests/integration/test_controlled_agent_workflow.py`

**Checkpoint**: US3 在 60 秒预算内完成或准确降级；未审批副作用为 0，SC-004 与相关 SC-008 达标。

---

## Phase 6: User Story 4 — 通过关系知识回答多跳问题 (Priority: P4)

**Goal**: 从授权企业知识建立可追溯图投影，并返回路径上每个节点、边和来源都获授权的多跳答案。

**Independent Test**: 使用含已知关系链、重名、冲突和受限节点的文档，验证实体治理、图 generation、
路径授权、无路径处理和原始引用；不依赖 Advanced RAG 策略。

### Tests for User Story 4

- [X] T097 [P] [US4] 编写 Entity/Relation/RelationEvidence 来源、版本和纠错契约测试 `tests/contract/test_graph_provenance.py`
- [X] T098 [P] [US4] 编写路径级 scope、撤权、计数/错误侧信道和无权限遍历测试 `tests/security/test_graph_path_authorization.py`
- [X] T099 [P] [US4] 创建单跳、多跳、无路径、别名、冲突和 forbidden relation 评估 fixture `tests/fixtures/evaluation/graph_multihop.jsonl`

### Implementation for User Story 4

- [X] T100 [US4] 创建 GraphEntity、EntityMention、GraphRelation、RelationEvidence 和 GRAPH projection 迁移 `migrations/versions/0008_graph_provenance.py`
- [X] T101 [P] [US4] 实现图实体、mention、关系、证据和冲突状态领域模型及 repository `src/atlasmind/graph/models.py`
- [X] T102 [P] [US4] 定义实体/关系抽取 port、来源定位和 extraction version 契约 `src/atlasmind/graph/extraction.py`
- [X] T103 [US4] 实现别名归一、重名候选、合并审核和禁止静默合并规则 `src/atlasmind/graph/entity_resolution.py`
- [X] T104 [US4] 实现关系抽取、置信度、有效期、冲突和 RelationEvidence 绑定 `src/atlasmind/graph/relations.py`
- [X] T105 [P] [US4] 实现不泄露框架内部 ID 的 LightRAG adapter `src/atlasmind/infrastructure/lightrag_adapter.py`
- [X] T106 [US4] 实现带 canonical ID、scope、version、provenance 和 generation 的 Neo4j 投影 `src/atlasmind/infrastructure/neo4j_projection.py`
- [X] T107 [US4] 将 GRAPH projection 构建、重试、退休和 reconciliation 接入导入 worker `src/atlasmind/workers/graph_projection.py`
- [X] T108 [P] [US4] 定义 GraphRetrievalRequest、GraphPath 和路径证据 envelope `src/atlasmind/retrieval/graph_contracts.py`
- [X] T109 [US4] 实现查询阶段路径全组成授权、跳数/节点预算和返回前复核 `src/atlasmind/retrieval/graph_neo4j.py`
- [X] T110 [US4] 实现独立 GraphRetrievalBackend 并注册到 Capability Registry `src/atlasmind/retrieval/graph_backend.py`
- [X] T111 [US4] 扩展 RetrievalPolicy 与 Agent planning，只为适用任务选择 Graph Backend `src/atlasmind/agent/graph_planning.py`
- [X] T112 [US4] 实现关系路径到 claim/citation 的绑定、冲突和无路径回答 `src/atlasmind/application/graph_answers.py`
- [X] T113 [US4] 实现实体/关系确认、拒绝和纠错管理用例及路由 `src/atlasmind/api/routes/graph_governance.py`
- [X] T114 [US4] 完成授权多跳、撤权、重名冲突、虚构关系和路径引用端到端测试 `tests/integration/test_authorized_graphrag.py`

**Checkpoint**: US4 可独立演示；路径一致率、虚构关系和权限泄露满足 SC-002、SC-005 与 SC-006。

---

## Phase 7: User Story 5 — 评估和追踪知识代理质量 (Priority: P5)

**Goal**: 授权运营人员能够关联查看运行，执行可重复评估并以确定性安全门禁和语义质量指标
判断发布状态。

**Independent Test**: 执行成功、拒绝、失败、超时、审批、导入和图任务；验证 correlation 链、
审计访问、敏感数据零泄露、评估可重复性和 spec 全部阈值。

### Tests for User Story 5

- [X] T115 [P] [US5] 按 OpenAPI 编写 EvaluationRun 创建/读取和授权错误契约测试 `tests/contract/test_evaluation_api.py`
- [X] T116 [P] [US5] 编写普通员工跨用户 AgentRun、trace、AuditEvent 和评估记录访问测试 `tests/security/test_operational_record_access.py`
- [X] T117 [P] [US5] 编写 query/chunk/prompt/tool secret marker 在 log、trace、event 和评估产物中的零泄露测试 `tests/security/test_sensitive_telemetry.py`
- [X] T118 [P] [US5] 编写固定配置重复运行、版本 manifest 和安全失败不可平均抵消测试 `tests/evaluation/test_reproducible_gates.py`

### Implementation for User Story 5

- [X] T119 [US5] 创建 EvaluationDataset、EvaluationCase、EvaluationRun、EvaluationResult 和受控运行记录访问迁移 `migrations/versions/0009_evaluation_models.py`
- [X] T120 [P] [US5] 实现评估数据集、case、知识快照、运行和指标结果领域模型 `src/atlasmind/evaluation/models.py`
- [X] T121 [US5] 实现 APPROVED/隐藏数据集 repository、不可变版本和访问控制 `src/atlasmind/evaluation/datasets.py`
- [X] T122 [P] [US5] 实现文档 hash、index generation、policy、model、prompt 和 evaluator 版本 manifest `src/atlasmind/evaluation/snapshots.py`
- [X] T123 [P] [US5] 实现 Recall@k、MRR、nDCG、forbidden marker、审批绕过和状态重建确定性指标 `src/atlasmind/evaluation/deterministic.py`
- [X] T124 [US5] 实现固定 judge 配置、重复采样和置信区间的 DeepEval adapter `src/atlasmind/evaluation/deepeval_adapter.py`
- [X] T125 [P] [US5] 实现 claim→citation→source span 程序校验与专家抽样队列 `src/atlasmind/evaluation/citation_accuracy.py`
- [X] T126 [US5] 实现数据集执行、逐 case 隔离、指标聚合和 INVALID 判定的 evaluation worker `src/atlasmind/workers/evaluation.py`
- [X] T127 [US5] 实现 spec SC-001 至 SC-009、安全零容忍和相对基线退化发布门禁 `src/atlasmind/evaluation/quality_gate.py`
- [X] T128 [P] [US5] 为 API、Agent step、Retrieval、Tool、Ingestion 和 Evaluation 添加统一 span/metric `src/atlasmind/observability/instrumentation.py`
- [X] T129 [US5] 实现 AuditEvent 完整性验证、受控查询和访问自身审计 `src/atlasmind/observability/audit_repository.py`
- [X] T130 [US5] 实现授权 AgentRun 步骤、来源/工具活动、耗时和最终状态查看用例 `src/atlasmind/application/inspect_runs.py`
- [X] T131 [US5] 实现 EvaluationRun 创建/读取和运营门禁 REST 路由 `src/atlasmind/api/routes/evaluations.py`
- [X] T132 [P] [US5] 实现默认禁用、字段 allowlist 和 correlation 映射的可选 LangSmith adapter `src/atlasmind/observability/langsmith_adapter.py`
- [X] T133 [US5] 在日志、OTel exporter、评估 writer 和错误处理接入双层敏感数据过滤 `src/atlasmind/observability/export_policy.py`
- [X] T134 [P] [US5] 创建 golden、权限、注入、失败、Graph 和性能数据集 manifest `tests/fixtures/evaluation/datasets.yaml`
- [X] T135 [US5] 完成 API→outbox→worker→Agent/Tool→Evaluation→Audit correlation 端到端测试 `tests/integration/test_observability_correlation.py`
- [X] T136 [US5] 完成全部质量阈值、审计可追踪率和敏感数据治理集成测试 `tests/evaluation/test_release_quality_gates.py`

**Checkpoint**: US5 提供可重复质量报告；SC-007、SC-009 及全量安全/质量门禁通过。

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: 完成依赖、性能、恢复、安全加固和项目级验证，不增加新的业务范围。

- [ ] T137 生成并审查正式依赖锁、许可证与供应链清单 `uv.lock` 和 `docs/dependency-policy.md`
- [ ] T138 [P] 配置 OpenAPI 3.1 lint、生成契约快照和 breaking-change 检查 `scripts/validate_openapi.sh`
- [ ] T139 [P] 建立中英文关键词、向量、融合与重排相关性基准 `tests/evaluation/test_hybrid_retrieval_benchmark.py`
- [ ] T140 [P] 建立 10 秒问答、10 分钟导入、60 秒多源任务和 100 并发运行负载测试 `tests/performance/test_service_targets.py`
- [ ] T141 [P] 验证 PostgreSQL/对象恢复、outbox 重放、projection 全量重建和 RPO/RTO `tests/integration/test_disaster_recovery.py`
- [ ] T142 根据容量、p95、相关性和维护窗口实测记录 pgvector→Qdrant 触发结论 `docs/vector-store-decision.md`
- [ ] T143 [P] 加固非 root 容器、只读文件系统、网络最小权限和健康检查 `Dockerfile`
- [ ] T144 把企业保留/脱敏/导出/删除和 LangSmith 外发决策变成生产启动门禁 `src/atlasmind/settings.py`
- [ ] T145 创建一键执行类型检查、单元、契约、集成、安全和评估门禁的脚本 `scripts/quality_gate.sh`
- [ ] T146 按 `specs/001-enterprise-agentic-rag/quickstart.md` 执行完整验收并更新真实运行命令 `README.md`
- [X] T147 [US1-US5] 在 `frontend/` 创建 Next.js App Router + React + TypeScript strict 前端，使用 Tailwind CSS、shadcn/ui、TanStack Query、React Hook Form + Zod 和少量 Zustand，实现企业 OIDC/BFF 服务端会话、OpenAPI 类型化客户端、SSE AgentRun 进度、四种问答模式、引用与运行详情、知识导入和版本治理、工具审批、Graph 冲突治理、评估门禁及登录/无权限页面，并补充 Vitest/RTL、MSW 与 Playwright 测试；token 不得写入 `localStorage`，前端不得提交 principal/role/scope 或记录 query/证据正文等敏感 telemetry

**Checkpoint**: 所有实际执行结果均被记录；没有通过删除、隐藏或弱化失败检查获得通过状态。

---

## Phase 9: Real-data local MVP

**Purpose**: 移除运行时演示数据路径，把已有领域和适配器模块装配为可从真实上传文件完成持久导入、图抽取和有引用问答的本地 MVP。

- [ ] T148 编写真实 MVP 配置、模型协议、持久化导入和端到端回归测试 `tests/unit/test_openai_compatible.py` 与 `tests/integration/test_real_mvp_flow.py`
- [ ] T149 实现仅非生产可用的 local 身份、可启动 FastAPI 应用与运行时依赖装配 `src/atlasmind/api/app.py` 与 `src/atlasmind/runtime.py`
- [ ] T150 实现 PostgreSQL + MinIO 持久化上传、任务领取、解析、Chunk、词法索引和 pgvector 投影 `src/atlasmind/application/real_mvp.py`
- [ ] T151 实现 OpenAI 兼容 Embedding/生成/结构化图抽取适配器 `src/atlasmind/infrastructure/openai_compatible.py`
- [ ] T152 实现带规范 ID、版本、scope 和 locator 的 Neo4j 真实投影及有界图检索 `src/atlasmind/infrastructure/neo4j_runtime.py`
- [ ] T153 实现真实混合检索、Graph 增强、LLM 证据问答、持久 AgentRun 和引用 `src/atlasmind/application/real_mvp.py`
- [ ] T154 移除前端 demo 路由分支，新增 local 开发会话并统一代理到真实 FastAPI `frontend/src/lib/auth/` 与 `frontend/src/app/api/`
- [ ] T155 将 API/worker 加入 Compose，更新无秘密配置和真实 MVP 运行、验收说明 `compose.yaml` 、`.env.example` 与 `README.md`
- [ ] T156 执行迁移、Python/前端检查、真实 PostgreSQL/MinIO/Neo4j 端到端验收，记录未配置外部模型时的明确启动门禁

### Phase 10: Neo4j GraphRAG framework integration

- [X] T157 将 Neo4j GraphRAG for Python 纳入真实运行依赖并验证 Python 3.14 兼容性
- [X] T158 使用官方实体关系抽取组件替换生产自定义图抽取，同时保留可重复测试边界
- [X] T159 使用官方 `Neo4jGraph`/`KGWriter` 契约、向量索引助手和 `VectorCypherRetriever` 实现增量图投影与检索
- [X] T160 在 Retriever 前执行 scope、有效文档版本和撤销状态授权过滤，并增加自动化安全回归
- [X] T161 更新真实 MVP 运行说明并执行后端、真实存储与容器回归

**Checkpoint**: 重启后上传文档仍可检索；Graph 关系来自真实 Chunk 并可回溯；问答仅使用当前授权证据且返回可定位引用；运行时不得回退到演示数据。

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: 无依赖，可立即开始。
- **Phase 2 Foundational**: 依赖 Phase 1，阻塞所有用户故事。
- **US1 (Phase 3)**: 依赖 Foundational；建议作为 MVP 首先交付。
- **US2 (Phase 4)**: 依赖 Foundational，可与 US1 的后半段并行，但最终检索验收复用 US1 契约。
- **US3 (Phase 5)**: 依赖 US1 的 Evidence/Citation Pipeline 和 US2 的可治理知识。
- **US4 (Phase 6)**: 依赖 US1 的证据/引用和 US2 的导入/projection generation；不依赖 US3 工具。
- **US5 (Phase 7)**: 基础观测依赖 Foundational；完整验收依赖 US1–US4 产生全部运行类型。
- **Phase 8 Polish**: 依赖计划交付的所有目标用户故事。

### User Story Dependency Graph

```text
Setup → Foundational ─┬→ US1 ─┬→ US3 ─┐
                     │       └→ US4 ─┼→ US5 → Polish
                     └→ US2 ─┬→ US3 ─┘
                             └→ US4
```

### Within Each User Story

1. 先完成该故事的契约、安全、集成或评估测试，并确认测试因缺少行为而失败。
2. 执行 schema/migration 与领域模型任务。
3. 执行 repository、adapter 和 application service 任务。
4. 执行 API/worker/Agent 集成任务。
5. 运行独立验收并达到对应 checkpoint 后，才进入依赖该故事的阶段。

## Parallel Opportunities

### Setup and Foundational

- T004、T005、T006 可并行；T013/T015、T019/T020、T025/T026/T029/T030 修改不同模块可并行。
- 数据库迁移按编号串行合并；授权模型和 OIDC adapter 可以先并行实现，再接入 AuthContext。

### User Story 1

- 测试 T032–T035 可并行编写。
- T037/T038、T040/T041/T043、T046/T051 修改独立模块，可在 schema 与契约确定后并行。

### User Story 2

- 测试 T054–T056 可并行编写。
- 文件验证 T059、解析 T060、元数据 T062 和 reconciliation T068 可并行，再由 worker T065 集成。

### User Story 3

- 测试 T073–T076 可并行编写。
- 结构化查询 T079、外部 API T081、Agent state T084、repository T088、预算 T090 和审计 T093 可并行。

### User Story 4

- 测试 T097–T099 可并行编写。
- 抽取契约 T102、LightRAG adapter T105 和 Graph DTO T108 可并行，再接入 projection 与查询。

### User Story 5

- 测试 T115–T118 可并行编写。
- 模型 T120、snapshot T122、确定性指标 T123、引用校验 T125、instrumentation T128、LangSmith adapter T132 和数据集 T134 可并行。

## Parallel Execution Examples

### US1

```text
并行组 A: T032 API contract | T033 permission matrix | T034 citation contract | T035 fixtures
并行组 B: T040 pgvector | T041 lexical | T043 reranker | T046 evidence verifier | T051 metrics
```

### US2

```text
并行组 A: T054 API contract | T055 lifecycle | T056 idempotency
并行组 B: T059 validation | T060 parsers | T062 metadata | T068 reconciliation
```

### US3

```text
并行组 A: T073 multi-source | T074 capability contract | T075 approval | T076 injection
并行组 B: T079 SQL registry | T081 external API | T084 Agent state | T088 repository | T090 budgets
```

### US4

```text
并行组 A: T097 provenance | T098 path authorization | T099 graph fixtures
并行组 B: T102 extraction port | T105 LightRAG adapter | T108 graph contracts
```

### US5

```text
并行组 A: T115 evaluation API | T116 record access | T117 telemetry leakage | T118 repeatability
并行组 B: T120 models | T122 snapshots | T123 metrics | T125 citations | T128 OTel | T132 LangSmith
```

## Implementation Strategy

### MVP First

1. 完成 Phase 1 Setup。
2. 完成 Phase 2 Foundational，建立不可绕过的身份、授权、审计和执行边界。
3. 完成 Phase 3 US1，使用预置 fixture 验收授权问答、证据不足、冲突和引用。
4. 达到 US1 checkpoint 后停止并演示 MVP，再决定是否进入知识导入完整实现。

### Incremental Delivery

1. **MVP**: US1 可信授权问答。
2. **Knowledge Operations**: US2 导入、版本、治理、撤销与 reconciliation。
3. **Agentic Analysis**: US3 多来源 Agent、工具、预算、审批和降级。
4. **Graph Retrieval**: US4 可追溯且路径级授权的 GraphRAG。
5. **Quality Operations**: US5 可观测、审计、评估和发布门禁。
6. **Hardening**: Phase 8 性能、恢复、供应链和完整 quickstart 验证。

每次增量都必须保留此前权限、证据、审批、审计和质量门禁；后续能力不得降低前序验收结果。
