# AtlasMind 下一步建议

本文只管理尚未完成工作的优先级、原因和验收出口。已实现事实见 [PROJECT_STATUS.md](PROJECT_STATUS.md)。

## 文档信息

| 项目 | 当前值 |
|---|---|
| 最后更新 | 2026-08-28 |
| 规划基线 | Advanced RAG 编排、AG-UI SSE 和详细 Retrieval Activity 已进入代码，全量前端、断线恢复和真实基础设施复验待完成 |
| 推荐节奏 | 先完成 Advanced RAG 与 SSE 发布验证，再持续化真实链路门禁和任务恢复能力 |

## 当前优先结论

Advanced RAG 编排和 SSE 功能已收尾：外层 Agent 只暴露 `knowledge_search`，内部 Retrieval Planner 只产出 Plan，固定 LangGraph/Runtime 负责校验和执行；AG-UI 兼容事件支持持久化、按序回放，并以可审计摘要展示内部 Retrieval Workflow。当前最优先事项是由用户执行尚未完成的全量前端、断线恢复与真实基础设施验收；验收前不将该增量视为完整发布基线。身份按当前决策继续使用 development/local 的本地超级管理员，企业 OIDC 暂不进入当前开发范围。

## P1：持续化真实链路门禁

### 0. 完成 Knowledge Graph Explorer 发布验收

**原因**：第一阶段 Explorer、授权局部查询、ForceAtlas2 Worker、窗口内 Inspector、客户端 PageRank/Louvain、Local Graph 径向预布局、Noverlap 防重叠、节点数量分档布局、标签 LOD 和相机聚焦已进入代码；ForceAtlas2 的 killed Worker 复用竞态和 40/80/120/200 档位选择已完成回归测试，但 Top 120/200 的防重叠视觉尚未完成真实浏览器人工验收，当前沙箱内的 Next.js 生产构建也未完成。

**验收出口**：

- 在标准 Linux/容器构建环境完成 `pnpm build`，且不出现 Sigma Worker、WebGL 或 Next.js 动态加载错误；
- 用真实浏览器验证 Zoom、缩放百分比输入、Pan、Fit、全屏、Drag、Hover、Node/Edge Click、Double Click Expand 和 1～3 hop Local Graph；
- 用 20/40/80/120/200 节点 Scene 验证 ForceAtlas2 后不存在可见节点重叠，局部图根节点保持居中且一跳、二跳关系层次可辨；
- 用两个互斥 scope 验证搜索结果、节点、degree、邻居关系和 provenance 均不产生跨 scope 信息泄露；
- 验证“查看原文”能够从 document/chunk/locator 精确定位到原始内容，而不只进入文档列表；
- 记录 1k、5k、10k Scene 的 FPS、布局稳定时间、内存、客户端 PageRank/Louvain 开销和截断行为，再决定是否改为服务端社区聚合、服务端中心性或分层加载。

### 1. 完成 Advanced RAG 与 SSE 发布验证

**原因**：后端 mypy 与常规测试已在 GraphRAG 导入修复后通过，真实 PDF 也已验证一次 `knowledge_search` 能返回原始 Chunk 引用；全量 Ruff 仍被既有中文标点正则阻塞。OpenAPI 前端生成类型、前端完整检查、SSE 断线恢复，以及内部 Graph Strategy 选择和 graphPaths 仍尚未完整验证。

**验收出口**：

- 重新生成 `frontend/src/lib/api/schema.d.ts`，确认包含 `/v1/rag/strategies`、`/v1/rag/policy` 及三个 operationId；
- 通过前端 TypeScript、RAG 组件测试、全量 Vitest、ESLint 和生产构建；
- 在真实 PostgreSQL/MinIO/Neo4j/模型环境验证 Agent 只调用一次 `knowledge_search`，GraphRAG 在内部 Retrieval 阶段执行并回溯原始 Chunk；
- 覆盖 Planner 选择禁用 Strategy、阶段错位、Multi-Query/HyDE 冲突、HyDE 无 Vector、多路召回无 Fusion、空候选 Rerank 和预算超限的失败关闭行为；
- 记录延迟、LLM/Embedding/检索调用次数、候选数量、降级 warning 和最终引用，确认与当前策略版本可关联。
- 验证 AG-UI 事件 Schema、单调 sequence、事件所有者鉴权、heartbeat、终态关闭，以及 `after`/`Last-Event-ID` 从断点按序补齐且不重复渲染；
- 验证回答增量、公开步骤摘要、`knowledge_search`/结构化 Tool 状态、证据数量、引用、最终快照和异常状态均能实时展示，且事件中不出现原始问题、scope、Prompt、隐藏推理或 Evidence 正文；
- 覆盖取消与后台完成/异常竞态、优雅关机、模型流缺少 `[DONE]`、非法引用及终态后重连，确认最终状态和终态事件唯一且一致。

### 2. 将真实烟雾测试接入可控门禁

**原因**：普通 CI 无法证明本地模型和持久化基础设施可用；真实测试又不应依赖开发者的长期共享数据库。

**验收出口**：

- 提供隔离的测试数据库、对象桶和 Neo4j 测试空间；
- 测试结束后不在开发知识列表残留测试记录；
- 在具备模型凭据和基础设施的受控 runner 中按需执行；
- 失败产物不包含密钥、原始敏感文档或未脱敏模型响应。

### 3. 建立 Agent 路由、Retrieval Plan 与恢复门禁

**原因**：当前已实现有界 LangGraph 循环、确定性 Retrieval Plan 校验与 SSE 事件恢复，但 Agent 后台任务仍运行在 API 进程内。事件恢复不等于任务恢复；模型升级、Prompt 调整和长请求仍可能改变 Agent Tool 选择、内部 Strategy 选择，进程崩溃后也无法从中断节点续跑。

**验收出口**：

- 建立版本化 Agent 路由与 Retrieval Plan 数据集，覆盖无需检索、一次 `knowledge_search`、结构化数据、Vector/BM25/Graph 单路与多路、Query Transformation、无证据、Strategy 失败和恶意 Evidence；
- 分别记录 `knowledge_search` 选择准确率、RetrievalPlan 合法率、Strategy 选择准确率、平均步骤数、预算终止率、降级率和 Citation 校验失败率；
- 评估 LangGraph Checkpointer 与独立 Agent Worker，持久化运行输入、节点状态和幂等 Tool 执行边界，完成进程崩溃后的恢复测试后再启用可续跑长任务；
- 任何恢复方案都不得绕过最新 authz revision、活动版本和 Tool Runtime 校验。

### 4. 配置首个真实结构化 Dataset

**原因**：受控 `query_structured_data` Runtime 已实现，但没有真实 Dataset 配置时不会向 Agent 暴露，当前不能宣称业务数据问答已可用。

**验收出口**：

- 选择一个只读业务数据源，明确 Dataset 版本、scope 列、指标、维度、过滤字段和最大行数；
- 验证 Agent 只能提交语义参数，不能提交 SQL、表名、列名、principal 或 scope；
- 验证数据库事务只读、查询参数化、结果行数/字节预算和审计记录；
- 前端至少能展示 STRUCTURED Evidence 的数据集名称、指标、摘要和限制说明。

### 5. 闭合受控多源 Evidence 编排与 Context Builder

**原因**：当前 Vector、PostgreSQL FTS 与 Graph 回溯 Chunk 已能统一进入 Fusion/Rerank，Agent State 也能累积文档和 Structured Evidence；但 Structured Dataset 默认未配置，Graph Path 不进入最终模型 Context，外层 Tool 只能由模型串行重规划，且 SQL/Graph 的输出不能通过类型化依赖传给后续 Hybrid Retrieval。现状属于“统一 Evidence 容器已存在”，尚不是完整的多源 Evidence Workflow。

**最小改造方案**：

- 保留 Agent 只调用 `knowledge_search`、`query_structured_data` 等少量高层能力，不把 Vector、BM25、Graph、Fusion 或 Rerank Tool 化；
- 在现有 Agent LangGraph 中增加声明式、有限步的 `EvidenceOrchestrationPlan` 和确定性 Runtime 校验。Planner 只选择高层证据任务及依赖，Runtime 执行串行/并行分支、类型检查、超时、并发和总预算，禁止模型直接循环调用底层 Strategy；
- 为跨源依赖增加最小 typed binding：Structured Dataset 配置显式声明可作为检索 Seed 的业务实体字段；Graph Path 显式输出有界 canonical entity seeds。Runtime 只允许白名单字段生成后续检索输入，不把任意 SQL 文本或模型生成内容直接当成查询；
- 在 Retrieval Workflow 内增加可选的有界 Expansion 子阶段，使 Graph entity seeds 能触发一次 Vector/PostgreSQL FTS 文档扩展；保持 Query Processing 在检索前、Fusion 在所有文档候选后、Rerank 在 Fusion 后的固定关系；
- 新增统一 `ContextBuilder`，按来源类型把 DOCUMENT 原文、STRUCTURED rows/aggregation 和 GRAPH Path/关系说明组织为带 source type、version、locator、provenance 和截断预算的模型 Context。Graph 事实必须关联支撑它的原始 Chunk，不得替代原文证据；
- 保留现有 `EvidenceEnvelope` 与引用白名单作为兼容边界，补充 retrieval method/score、Graph Path source chunk IDs，以及 Structured query/result provenance；不要要求 Adapter 生成自然语言答案。

**验收出口**：

- 同一运行能够执行并持久化 Document、Structured、Graph 三种来源的 Evidence；最终 Prompt 快照能证明模型收到实际选中的 Chunk 原文、SQL rows/aggregation 和已标注来源的 Graph Path，而不是只有 ID 或摘要；
- 覆盖 Vector、关键词和 Graph 并行召回，以及 `SQL → 白名单实体 Seed → Hybrid Search`、`Graph → canonical entity Seed → 文档扩展检索` 两条确定性串行链路；每条链路都有调用次数、候选数、超时、并发和总字节预算；
- Graph 命中始终根据 provenance 回查当前活动、可搜索且已授权的原始 Chunk；无授权 Chunk 的 Path 不进入 Context，Graph-only 关系不能单独支撑最终文档事实；
- Structured Evidence 保存 Dataset/version、metric、受控参数摘要、执行时间、结果摘要和可用的行级业务键；引用能够定位注册数据库来源，且不泄露原始 SQL、凭据或越权行；
- Context Builder 对不同来源使用明确标签，不再把 Structured rows 误称为原始文档；模型只能返回当前 Context 中的 Evidence ID，引用校验和持久化继续 fail closed；
- 自动化测试覆盖多源部分失败、空分支、重复 Evidence、Graph/SQL Seed 上限、恶意字段值、超时降级和权限收紧，不允许失败分支清空已经验证的其他来源 Evidence。

## P2：生产身份与权限

**当前决策**：暂缓，不阻塞本地单企业 MVP。

**后续原因**：local 超级管理员不具备生产隔离、离职回收、细粒度授权和企业审计能力。

**验收出口**：

- 使用目标企业 IdP 完成 OIDC 登录、刷新、退出和失败回调；
- 至少验证知识管理员、普通员工、审批人和审计员的权限矩阵；
- production 无法回退到 local auth；
- 越权访问、跨 scope 引用和高风险工具审批具有自动化安全测试。

## P2：质量与性能验收

### 接入真正 BM25 与 `bge-reranker`

**原因**：当前 `BM25` Strategy 实际使用 PostgreSQL FTS 的 `tsvector`、`websearch_to_tsquery` 和 `ts_rank_cd`，不是 Okapi BM25，全文搜索向量也没有专用 GIN/GiST 索引；当前 Rerank 则由 DeepSeek Chat 对有限候选执行 listwise 排序，并未接入 Cross-Encoder。两者已有的 Strategy、LangGraph 阶段关系、预算和降级边界可以复用，但底层检索与排序实现仍需替换或扩展。

**实施前选型**：结合现有 PostgreSQL 架构，至少对比 PostgreSQL 原生 FTS 增强方案、ParadeDB/`pg_search` 与独立 OpenSearch/Elasticsearch 的 BM25 功能匹配度、维护活跃度、License、部署复杂度和中文检索能力；`bge-reranker` 至少对比进程内 `sentence-transformers`/FlagEmbedding、独立 TEI 等模型服务方式及可用的兼容 Rerank API。优先通过现有 Strategy Port 接入，不改变 Agent Tool Catalog 或 Retrieval Workflow 固定阶段。

**验收出口**：

- 将当前 PostgreSQL FTS 与真正 BM25 实现区分命名和配置，迁移期间保持策略配置兼容，并明确回滚路径；
- BM25 只召回当前活动版本、`active/searchable` 且属于调用者 scope 的原始 Chunk，Self-Query metadata filter 继续由确定性 Runtime 校验；
- 使用可重复的中英文关键词评估集，对比 PostgreSQL FTS、Vector 与 BM25 的 Recall@k、MRR、nDCG、p50/p95 延迟和资源占用，证明接入收益；
- 为选定 BM25 方案补齐索引、迁移、重建、健康检查、容量基线和故障降级验证，避免查询在目标数据规模退化为不可接受的扫描；
- 通过独立 Reranker Port/配置接入选定的 `bge-reranker` Cross-Encoder，模型只接收 Fusion 后的有界候选，不改变 `Query Processing → Retrieval → Fusion → Rerank` 阶段顺序；
- 验证候选上限、文本截断或分段、批处理、并发、超时、重试和资源预算；模型不可用或返回非法结果时继续安全回退到 Fusion/RRF 顺序；
- 对比无 Rerank、现有 DeepSeek listwise 与 `bge-reranker` 的 nDCG/MRR、引用命中率、延迟、吞吐和成本，达到预先确定的质量/性能阈值后才切换默认实现；
- 增加真实模型集成测试与 Strategy 单元测试，并在状态文档中只按实际执行结果记录完成情况。

### 检索与回答质量

建立版本化评估集，覆盖 Recall@k、MRR、nDCG、忠实度、上下文相关性、引用准确率，以及各 Query Transformation、Vector/BM25/Graph/Fusion/Rerank 组合的质量、成本和延迟；GraphRAG 继续覆盖跨文档实体对齐准确率、多跳路径召回率和虚构关系比例。

**验收出口**：指标阈值、评估数据版本、失败样例和回归趋势均可重复生成；GraphRAG 数据集至少覆盖同名异义、别名、一跳、两跳、无路径、低置信度关系和跨权限路径，不得只用单次人工体验判定通过。

### 性能与容量

验证问答、导入、多源任务和并发目标。

**验收出口**：形成环境规格、数据规模、p50/p95/p99、错误率、资源占用和可复现压测脚本。

### 备份与恢复

覆盖 PostgreSQL、对象存储、Neo4j 投影重建和 outbox 重放。

**验收出口**：在隔离环境演练恢复，并记录实际 RPO/RTO；不得只验证备份文件存在。

## P3：生产治理与后续能力

- SBOM、依赖许可证与漏洞门禁；
- 容器非 root、只读文件系统、最小网络权限和密钥轮换；
- 数据保留、删除、法律保留和审计归档；
- LangSmith 生产接入与遥测脱敏；
- SQL 数据接入 UI 和更多受控 Dataset。

每项必须在进入开发前补充独立验收出口。OpenAPI breaking-change 治理按当前决策继续暂缓。

## 规划维护规则

- 完成项从本文移除，并把可验证结果同步到 [PROJECT_STATUS.md](PROJECT_STATUS.md)。
- 新建议必须包含优先级、原因和验收出口。
- 外部依赖或代码变更暴露新风险时，在同一变更中更新本文。
- 每次更新同步修改“最后更新”日期。
