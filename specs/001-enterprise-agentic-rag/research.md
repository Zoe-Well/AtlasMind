# Phase 0 Research: 企业级 Agentic RAG 知识平台

## 1. 应用形态与代码组织

**Decision**: 采用单仓库、模块化单体的 Python Web Service。FastAPI 作为 HTTP 接入层，
按身份与权限、知识导入、检索、Agent、工具、图检索、可观测与评估划分模块。长耗时导入、
Agent 运行和评估由同一代码库的独立 worker 进程执行，首期不拆分微服务。

**Rationale**: 当前仓库只有最小脚手架。模块化单体能以最低分布式复杂度建立明确边界，
同时允许后续把导入、图检索或工具执行独立部署。

**Alternatives considered**: 首期微服务会过早引入服务发现、分布式事务和部署负担；单文件
实现会让 Agent、权限和数据访问互相穿透；Serverless 不适合长任务和连续审计链路。

## 2. Python 与依赖兼容性

**Decision**: 保持仓库当前 Python 3.14 基线。实现开始前必须对 FastAPI、LangGraph、
数据库驱动、Neo4j GraphRAG、DeepEval 和文档解析依赖执行安装、导入和最小运行验证；只采用正式
支持该运行时的稳定版本并生成依赖锁。

**Rationale**: `.python-version` 与 `pyproject.toml` 已明确 Python 3.14，规划不得擅自降级；
AI/RAG 生态对新运行时的支持可能滞后，因此兼容性验证是首个实现门禁。

**Alternatives considered**: 未经批准改用 Python 3.12/3.13 会改变现有技术约束；预发行依赖
不适合作为企业默认基线；延迟验证会把风险推到核心集成阶段。

## 3. Agent 编排与执行边界

**Decision**: LangGraph 只承担显式 Agent 状态机：意图判断、检索判断、任务分解、能力选择、
证据综合和降级。节点只能发出类型化 Capability Request；数据库、检索和外部调用均由受控
执行网关完成。Agent 状态只保存授权上下文引用、运行预算、步骤、证据引用和结构化结果，
不得持有底层客户端或任意函数调用能力。

**Rationale**: 可暂停、可恢复的状态图适合多步骤任务，但概率性规划不能成为权限或执行
边界。类型化请求使步骤可审计、可测试并可限制预算。

**Alternatives considered**: 自由 ReAct 循环难以约束终止与工具选择；把业务执行写入图节点会
绕过执行层；完全自研编排会增加 Phase 2 的恢复和状态管理成本。

## 4. Capability Registry 与工具审批

**Decision**: 所有 Retrieval Backend 和 Tool 必须注册版本化描述，声明输入输出、所需角色与
知识范围、风险级、超时、结果上限、幂等性、来源格式和审计规则。执行固定经过输入验证、
当前授权、风险与审批检查、有界执行、结果规范化、来源绑定和审计。任何外部副作用生成
参数绑定、限时、一次性的 Approval Challenge；换参、过期、重放或跨用户批准全部拒绝。

**Rationale**: 统一网关是 Agent 决策和真实权限之间的强制边界，也使 FR-026 可被确定性测试。

**Alternatives considered**: 直接暴露函数给 Agent、由工具自行决定审批、或仅显示确认弹窗，
都会产生规则不一致、参数替换和重放风险。

## 5. 检索 Pipeline 与 Advanced RAG Policy

**Decision**: 检索按授权与输入安全检查、可选查询改写/自查询/HyDE、混合候选检索、重排、
可选上下文压缩、证据充分性与冲突检查组成版本化 pipeline。确定性 Retrieval Policy 根据
任务类型、查询特征、延迟/成本预算、权限和阶段开关选择模块；模型只能提出建议，不能绕过
策略。公共 Evidence Envelope 携带来源、定位、版本、范围、有效状态和相关性信号。

**Rationale**: 该结构满足按需启用增强策略的要求，并允许独立评估、灰度、回退和后端替换。

**Alternatives considered**: 固定执行全部策略会放大成本和延迟；完全由 Agent 自由选择缺少
可重复性；为每个策略复制端到端链路会重复权限和观测逻辑。

## 6. 规范数据、向量和关键词检索

**Decision**: Phase 1 使用 PostgreSQL 作为规范事实源，并以 pgvector 承载首期向量检索。
关键词检索通过独立 Lexical Retriever 接口实现，与向量候选以可配置融合策略组合；中文与
英文分词、排序必须用目标语料基准验证。Qdrant 保留在统一 Vector Store 接口之后，仅在容量、
并发、延迟或相关性压测证明单库方案不能达标时启用。

**Rationale**: PostgreSQL 同时持有版本、生命周期、范围和向量元数据，可减少双写和撤权窗口；
当前 spec 没有证明首期需要独立向量集群。接口隔离保留扩展能力。

**Alternatives considered**: 首期直接使用 Qdrant 有更强向量扩展能力，但增加双写、备份和权限
一致性风险；纯 PostgreSQL 无 pgvector 不满足语义检索；引入搜索集群会扩大运维范围。

## 7. 对象和图数据边界

**Decision**: MinIO/S3 兼容对象存储保存不可变原始文件和可选解析产物。Neo4j 保存可重建的
实体关系投影，Neo4j GraphRAG 仅作为 GraphRAG 构建/检索引擎。PostgreSQL 保存规范 ID、版本、
scope、provenance 和投影状态；图节点和边必须关联来源片段、抽取版本、置信度与有效状态。

**Rationale**: PostgreSQL 与原始对象构成恢复基线，向量和图是可重建投影。Neo4j GraphRAG
内部标识不会泄漏为公共契约，也不能成为权限事实源。

**Alternatives considered**: 仅用 PostgreSQL 存图会限制多跳扩展；把权限事实放入图存储会形成
多事实源；把原始文件放数据库会增加备份和大对象 I/O 压力。

## 8. 跨存储一致性和导入状态机

**Decision**: 采用 PostgreSQL 事务、transactional outbox 和幂等异步投影，不使用分布式事务。
Document Version 与 Chunk 元数据先提交，worker 再构建对象、向量和图 projection generation；
只有必需投影成功后才原子切换为可检索版本。撤销或权限收紧先在规范状态中立即隐藏，再异步
清理投影。首期使用 PostgreSQL 持久任务表与 `SKIP LOCKED` worker，保留替换队列的 port。

**Rationale**: 规范状态可以立即控制用户可见性，派生索引允许重试和重建。generation 切换避免
半成品知识参与查询，也避免首期新增消息基础设施。

**Alternatives considered**: 跨存储两阶段提交不可行且复杂；顺序双写会留下孤儿和漏写；同步在
HTTP 请求内完成全部处理不满足恢复与十分钟导入目标。

## 9. 端到端授权

**Decision**: 可信企业 OIDC/OAuth2 身份在入口形成不可由用户或模型覆盖的 Auth Context，包含
subject、roles、knowledge scopes、授权版本和 correlation ID。每个 Retrieval/Tool 独立 deny by
default，在存储查询前过滤，返回后再以规范记录复核当前权限。缓存键包含主体、范围与授权版本；
授权状态缺失、过期或过滤失败时拒绝请求。图路径中的每个节点、边和证据均须获授权。

**Rationale**: 前置过滤防止受限内容进入模型上下文，返回复核覆盖撤权和索引竞态，服务端上下文
防止提示或工具参数伪造权限。

**Alternatives considered**: 仅网关校验覆盖不了内部边界；仅后置过滤已经读取越权候选；让 Agent
判权不确定且可被注入；只依赖单一存储策略无法覆盖外部工具和输出。

## 10. 提示注入和不可信数据

**Decision**: 用户输入、检索文档、图内容和工具输出均视为不可信数据。控制平面持有系统策略、
能力 allowlist 和审批状态；证据以结构化 envelope 传递，不能把其中指令当控制命令。执行网关
严格校验 schema、长度、目标、超时和结果上限。检测器或模型护栏只作为附加信号，不能替代
确定性授权。运行记录保存结构化关键决策，不保存隐藏思维链。

**Rationale**: 间接提示注入的核心是把数据误当指令；控制/数据分离和能力收窄比提示文字可靠。

**Alternatives considered**: 单靠系统提示、关键词分类器或模型自律无法承担安全边界；默认暴露
全部文档和工具会放大泄露与越权面。

## 11. 可观测、审计和敏感数据

**Decision**: OpenTelemetry 是强制且供应商中立的 trace、metric、structured log 基线。LangSmith
仅作为可选 LLM/Agent 调试与实验适配器，不是审计事实源；是否启用、托管或外发由企业数据政策
决定。审计事件与可采样 telemetry 分离。默认只记录 allowlist 元数据、不可逆摘要和受控引用，
不记录凭据、整段文档、原始 token 或工具秘密；写入和 exporter 两处均执行脱敏。

**Rationale**: 运行诊断、审计完整性和 LLM 实验具有不同保留与访问要求，必须分离治理。

**Alternatives considered**: 仅 LangSmith 会产生供应商和通用观测缺口；默认全量 trace 会形成新的
敏感副本；完全不记录无法满足运行追踪与审计要求。

## 12. 质量评估

**Decision**: DeepEval 作为离线/CI 语义评估 runner；检索同时使用 Recall@k、MRR/nDCG 等确定性
指标，引用使用 claim-to-source-span 程序校验与专家抽样，权限和审批使用零容忍确定性测试。
评估集版本化并绑定知识快照、身份/范围 fixture、允许和禁止证据、索引、策略、prompt、model 与
evaluator 版本。训练/调优集和隐藏回归集分离，优先使用合成或脱敏数据。

**Rationale**: LLM judge 有波动，不能证明安全；组合确定性指标、语义指标和专家判断才能覆盖
检索、忠实度、引用与权限质量。

**Alternatives considered**: 只看答案 exact match 忽略证据；只用 LLM judge 不确定；仅人工评估
不可持续；直接复用生产 trace 有隐私和漂移问题。

## 13. API 与异步运行

**Decision**: 提供版本化 REST API。查询、导入和评估创建有持久状态的异步运行，客户端通过运行
资源读取状态与最终结果；基础问答可在延迟预算内返回完成结果。SSE 只作为可选进度传输，不能
绕过最终答案、权限和引用复核。FastAPI 路由只负责身份上下文、验证和应用用例调用。

**Rationale**: 多步骤任务可达 60 秒，异步资源比长连接更易恢复和审计；薄路由使相同用例可被
API、worker 和测试复用。

**Alternatives considered**: 只提供同步接口不适合长任务；首期 GraphQL 增加不必要复杂度；路由
直接访问存储会让授权和业务规则分散。

## 14. 阶段化交付

**Decision**:

1. Phase 1：身份、范围、文档导入、混合检索、重排、引用、证据不足/冲突、审计和基础评估。
2. Phase 2：LangGraph 多步骤状态机、Capability Registry、受控结构化查询、外部工具和审批。
3. Phase 3：实体关系构建、来源绑定、授权多跳遍历和 GraphRAG 评估。
4. Phase 4：策略化 Query Rewrite、Self Query、HyDE、Context Compression 和持续评估。

每阶段独立验收，并重跑前序权限、引用、审批和审计回归。

**Rationale**: 先稳定可信企业检索，再增加编排、图和实验性策略，能够隔离质量变化来源。

**Alternatives considered**: 一次实现全部能力会扩大集成面；先做 Agent 或 GraphRAG 再补权限和
引用会形成不可上线的架构。

## 15. 前端应用与浏览器安全边界

**Decision**: 前端采用 Next.js App Router、React 和 TypeScript strict，独立于 Python 后端构建与
部署。组件层采用 Tailwind CSS + shadcn/ui（基于 Radix UI），服务端状态使用 TanStack Query，
表单使用 React Hook Form + Zod，Zustand 只承载无法由 URL、表单或服务端状态表达的少量本地
交互状态。客户端从 OpenAPI 生成类型定义和请求封装；AgentRun 状态更新首期采用 SSE，只有出现
真实双向低延迟需求时才评估 WebSocket。

企业 OIDC 通过 Next.js 服务端 BFF/Auth.js 或等价服务端会话实现，浏览器仅持有 `HttpOnly`、
`Secure`、`SameSite` Cookie，不把 access/refresh token 写入 `localStorage`。前端不得接受或生成
principal、role、scope 等授权事实；FastAPI 在查询、引用解析和运行记录读取时始终重新授权。
Citation 原文必须通过受控 API 获取，前端 telemetry 默认不得记录 query、证据正文、token 或秘密。

**Rationale**: Next.js 可同时提供企业问答界面和轻量 BFF，适配现有 REST/OpenAPI 与异步
AgentRun 模型；TanStack Query 和 SSE 能以较低复杂度处理轮询、缓存、取消和运行进度；shadcn/ui
保留企业 UI 定制能力而无需首期维护自建组件库。服务端会话降低浏览器 token 泄露和跨站脚本风险，
并允许统一传播 correlation ID、Problem Details 和防枚举错误语义。

**Alternatives considered**: Nuxt/Vue 3 是团队已有 Vue 经验时的可接受替代，但当前没有该约束；
纯客户端 SPA 会增加 token 生命周期和 BFF 缺失带来的安全复杂度；Redux、GraphQL、微前端和首期
WebSocket 对当前页面没有必要。前端选型已在 T147 中实现，并通过类型检查、组件测试、生产构建
和 Playwright 演示流程验证；真实企业 OIDC 和后端部署仍必须单独完成环境联调。

## Release-Blocking Dependencies

- 企业必须批准运行、审计和评估记录的保留、脱敏、导出与删除政策。
- 企业必须决定 LangSmith 禁用、自托管或允许发送的脱敏字段范围。
- Python 3.14 关键依赖兼容性必须通过实际安装和最小运行验证。
- 中文关键词检索与融合排序必须使用目标语料达到 spec 的检索和引用门禁。
