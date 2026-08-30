# AtlasMind 项目实现状态

本文只记录能够由当前代码、测试或实际运行验证的事实。设计稿、规格和任务勾选不单独作为完成证据。

## 文档信息

| 项目 | 当前值 |
|---|---|
| 最后更新 | 2026-08-28 |
| 基线分支 | `001-enterprise-agentic-rag` |
| 基线提交 | `b9cb757`（本文变更尚未提交） |
| 当前阶段 | 真实业务链路型 MVP；尚未生产就绪 |
| 公开仓库 | <https://github.com/Zoe-Well/AtlasMind> |
| 配套规划 | [NEXT_STEPS.md](NEXT_STEPS.md) |

## 当前结论

AtlasMind 已闭合单企业知识库的核心真实链路：本地超级管理员登录后，可以接入和查看真实文档，通过 LangGraph Agentic RAG 执行真实问答，并查看授权引用、历史运行与真实执行步骤。PostgreSQL/pgvector、MinIO、Neo4j、DeepSeek 兼容接口和本地 Embedding 兼容接口均已进入实际业务路径。

当前版本仍不应描述为生产就绪。企业 OIDC、规模性能、灾难恢复、供应链治理、数据生命周期和生产运维门禁仍未验收；SQL 数据接入仍是占位能力。Advanced RAG 策略配置和后端 Retrieval Workflow 已实现，前端完整验证尚待执行。

## 已验证能力

### 身份与权限

- development/local 模式提供固定的“本地超级管理员”身份，登录后即可使用当前全部 `Action`。
- 本地身份包含 `local-super-admin`、`knowledge-admin`、`tool-approver`、`auditor`、`employee` 角色。
- production 环境仍禁止 local auth；企业 OIDC 尚未联调。

### 真实知识链路

- 文档上传、版本创建、导入任务、状态查询和文档撤销均使用持久化数据。
- 原文件写入 MinIO；版本、分块、向量、引用、运行、trace 和审计写入 PostgreSQL；实体关系投影至 Neo4j。
- 支持运行时重建后的检索和问答。
- 引用返回真实文档标题、定位信息和经过授权的内容摘要。
- 查询兼容 PostgreSQL 中历史遗留的不同维度向量，不会因维度不一致中断检索。
- 相同内容可以被多个文档版本安全复用；Neo4j 关系按文档版本和分块保留独立来源，撤销一个版本不会停用另一个版本的图谱证据。
- 新导入文档只保留策略允许的系统、产品、服务、接口、错误码、组织、数据库、队列和技术组件等业务实体；实体 confidence 不再固定为 1。实体解析按管理员别名、规范化精确匹配、pg_trgm/向量候选和安全 margin 依次处理，歧义候选不会静默合并。
- 每条关系证据保存 source document、document version、source chunk、locator、confidence、抽取版本、策略版本、eligibility decision 和生命周期；LLM 抽取是候选观察，不直接作为最终回答事实。
- Graph 检索能力使用名称/别名与向量 Seed，在当前授权、实体/关系白名单、置信度和节点预算内执行最多两跳扩展；它由 `knowledge_search` 内部的 Retrieval Planner 在已启用策略中选择，不作为独立 Agent Tool。Graph 只扩大原始 Chunk 召回，随后与关键词/向量候选统一进入 Fusion/Rerank，最终回答及引用只读取原始 Chunk。
- Neo4j GraphRAG 的通用 OpenAI-compatible 适配器不再虚假声明 Pydantic Structured Output；DeepSeek 返回不符合 Graph Schema 的单个 Chunk 时，官方容错 JSON 路径将其降级为空 Graph 投影，不再阻断该文档的 Lexical/Vector 索引和发布。导入任务会在昂贵操作前持久化真实阶段，失败日志关联 job/version ID，并保存不含原文的异常类型引用。
- `GET/PUT /v1/graph/policy` 支持查看和版本化配置实体/关系白名单、最低置信度、Seed、跳数、节点、路径和 Chunk 预算；响应同时返回可选实体类型和当前身份是否可管理。文档换版/撤销会退役旧 mention/provenance 并对账 Neo4j 可重建投影。
- 上传、问答开始/完成/失败和撤销均写入持久化审计事件；AgentRun 保存真实 trace ID。

### Knowledge Graph Explorer

- `/graph` 已由固定 SVG 环形图替换为 Sigma.js WebGL、Graphology `MultiDirectedGraph` Scene 和 ForceAtlas2 Web Worker 布局。
- 全局 Scene 先按 Louvain 社区生成稳定初始位置，再执行 ForceAtlas2；Local Graph 以选中实体为中心，按 1～3 hop 生成由内向外的稳定径向初始位置。ForceAtlas2 稳定后使用 MIT `graphology-layout-noverlap` 消除节点绘制区域重叠，并重新聚焦局部根实体。该布局不改变后端查询、授权或 GraphRAG 检索链路。
- 当前 Scene 不等于数据库全图：支持授权 Global Top-N、实体搜索进入 Local Graph、1～3 hop 局部加载，以及双击或 Inspector 按需增量展开；增量合并按 Entity/Relation ID 去重。
- 图交互支持 Zoom、Pan、Fit、节点拖动、Hover 一跳高亮、节点/关系选择和 Edge Label 按需显示；节点按 Entity Type 着色，并按当前 Scene degree 与来源文档数映射大小。
- Entity Inspector 展示规范名、类型、Alias、授权 degree、来源文档、mention locator 和 confidence；Relation Inspector 展示 source/target、类型、confidence 和当前身份可见的 document/version/chunk/locator provenance。
- 后端新增授权实体搜索、实体详情、1～3 hop 邻居和关系证据查询；Entity Type、Relation Type、Confidence 和名称过滤均在 PostgreSQL 查询层执行，不采用“全量返回后前端隐藏”。
- PostgreSQL 继续作为规范事实源，Neo4j/GraphRAG 检索链路未改变；本阶段没有新增数据库迁移，也没有让浏览器直连图数据库。

### LangGraph Agentic RAG

- 主问答链路使用 LangGraph `StateGraph`，执行 `Plan/Route → Capability → Observe → Replan/Answer → Verify` 有界循环。
- DeepSeek 兼容模型只产生结构化 `CALL_TOOL` 或 `ANSWER` 决策；不持久化隐藏推理过程，只记录动作、能力名称和安全 reason code。
- 生产 Agent Tool Catalog 只暴露高层 `knowledge_search`；存在真实白名单 Dataset 时才额外暴露 `query_structured_data`。`Query Rewrite`、`Multi-Query`、`HyDE`、`Self-Query`、`GraphRAG`、`Fusion`、`Rerank` 均为 Retrieval Workflow 内部 Strategy，不注册为 Tool。
- `knowledge_search` 内部使用独立 LangGraph，固定执行 `Retrieval Planner → Plan Validation → Query Processing → Retrieval → Fusion → Rerank（按需）→ Evidence`。Planner 只输出声明式 `RetrievalPlan`，不执行 Strategy，也不能改变阶段顺序。
- Strategy Registry 统一注册 Query Rewrite、Multi-Query、HyDE、Self-Query、Vector、BM25（当前实现实际为 PostgreSQL FTS）、Graph、Fusion 和 Rerank；用户策略配置只决定 Planner 当前可以选择哪些 Strategy。Vector、关键词、Graph 可在 Retrieval 阶段并行，统一进入 Fusion/Rerank。
- 确定性 Runtime 拒绝禁用、重复、阶段错位和冲突 Strategy；Multi-Query 与 HyDE 互斥，HyDE 依赖 Vector，多路召回强制 Fusion，空候选跳过 Rerank。Runtime 同时限制超时、重试、LLM/Embedding/检索调用次数、Query Variant 和候选数量，Planner 不能形成无约束循环。
- Self-Query 只产生白名单、已审核 metadata 的等值过滤；GraphRAG 执行实体链接、有界遍历并回溯原始 Chunk，图关系本身不直接成为回答证据。
- 当前默认关闭 Query Rewrite、Multi-Query、HyDE、Self-Query，默认开启 Vector、BM25、Graph、Fusion、Rerank；缺少 Planner 结构化模型能力时使用确定性安全回退计划。
- 2026-08-28 对运行中策略接口的只读核对确认：Graph、Vector、BM25（实际为 PostgreSQL FTS）、Fusion、Rerank 当前均启用，Query Rewrite、Multi-Query、HyDE、Self-Query 当前均关闭。`AUTO` 模式下 Graph 只是 Planner 可选择的内部 Strategy，并非每次问答强制执行；显式 Graph 模式的确定性安全回退计划会包含 Graph。
- 当前 GraphRAG 实际链路为：用户问题进入 Retrieval Planner，经 Plan Validation 后，对规范化问题生成 Embedding，以名称/Alias 与向量相似度寻找最多 8 个 Seed Entity；随后在当前身份 scope、活动文档版本、实体/关系白名单及关系置信度不低于 0.70 的约束下执行局部图扩展，最多保留 40 个节点、24 条路径，并通过 relation provenance 回溯最多 24 个仍活动、可搜索且已授权的 PostgreSQL 原始 Chunk。Graph Chunk 与 Vector、PostgreSQL FTS 候选统一进入 RRF Fusion 和按需 Rerank，最终 Evidence、LLM 回答与引用仍以原始 Chunk 为准，图关系不能单独作为回答事实。
- GraphRAG 检索当前硬限制为 1～2 hop：运行中 Graph Policy 为 `maxHops=2`，API 模型允许范围也是 1～2，Neo4j Cypher 使用 `RELATED*1..2` 并再次按 `max_hops` 限制，因此不会检索三跳路径，也不保证每次必须走满二跳。Graph Explorer 的 1～3 hop 是独立的授权可视化探索能力，不代表 GraphRAG 检索支持三跳。
- 当前名为 `BM25` 的 Retriever 已能召回活动且可搜索、属于当前授权范围的原始 Chunk，但底层使用 PostgreSQL Full Text Search：导入时以 `to_tsvector('simple', content)` 生成 `search_vector`，查询时通过 `websearch_to_tsquery('simple', query)` 匹配并以 `ts_rank_cd` 排序。它不是 Okapi BM25；当前迁移也未为 `search_vector` 建立 GIN/GiST 全文索引，中文仅使用基础查询预处理，因此不应把当前能力描述为“真正 BM25 已接入”。
- Rerank 阶段、候选预算、超时、结果 ID 校验及失败后回退 Fusion 顺序均已实现；当前生产适配器把有限候选交给配置的 DeepSeek Chat 模型执行 listwise 排序。项目尚未接入 Cross-Encoder、`bge-reranker` 或独立 Reranker 服务，因此不应把当前能力描述为“Cross-Encoder Rerank 已实现”。
- 代码调用链核查确认，当前文档检索不是只返回 ID：Vector 与名为 `BM25` 的 PostgreSQL FTS Strategy 都直接查询 `knowledge_chunks`，返回包含 `chunk_id`、`document_version_id`、原始 `content`、`locator`、scope 和 score 的 `RetrievalCandidate(KnowledgeChunk)`；Fusion/Rerank 继续复用同一个 Chunk 对象，构建 Evidence 时不再重复查询文档。当前所谓 Hybrid 是多路 Strategy 结果的 RRF Fusion，不是独立 Hybrid Retriever；`PersistentKnowledgeService._retrieve()` 中旧的单 SQL 混合评分函数当前没有调用者。
- Graph Retriever 先从 Neo4j 返回 Entity、Relation、Direction 以及关系对应的 `chunk_id`/`locator` Path。Neo4j 关系保存 `source_document_id`、`document_version_id`、`chunk_id`、locator、scope、generation、confidence 和抽取/策略版本；随后 Workflow 依据 Path provenance 从 PostgreSQL 回查仍为活动、可搜索且已授权的原始 Chunk，把它们作为 `method="graph"` 的文档候选参与统一 Fusion/Rerank。Graph 因此已是辅助召回，最终引用仍绑定原始 Chunk；但当前没有把 Graph 命中的实体作为新 Query 再触发 Vector/PostgreSQL FTS 扩展检索。
- `query_structured_data` handler 已实现白名单 Dataset、指标、维度和 filter 到参数化只读 SQL 的编译与真实 `session.execute()`，返回的不是自然语言答案，而是一条 `STRUCTURED` Evidence，其中 `facts` 是查询 rows/aggregation 的 JSON。当前默认 Runtime 没有注入任何 `StructuredDataset`，因此 Tool 不会注册到生产 Agent Catalog；这条真实 SQL 执行代码目前仅在显式注入 Dataset 的运行时/测试中可达，不能描述为默认业务数据检索已接通。
- Agent State 已充当基础 Evidence Pool：每次高层 Tool 返回的 `EvidenceEnvelope` 按 `evidence_id` 累积，重复文档 Evidence 会合并 facts 与 `graphPaths` metadata。因此在配置 Structured Dataset 后，Agent 可以串行调用 `knowledge_search` 和 `query_structured_data`，把文档 Chunk 与 SQL rows 放进同一次回答；外层 Tool 当前不并行执行，也没有确定性的跨源依赖图、字段映射或中间实体传递，`SQL → 实体 → Hybrid Search` 与 `Graph → 实体 → 文档扩展检索` 均未实现。
- 最终 Compose 目前不是完整 Context Builder：它只把每条有效 Evidence 的 `facts` 连接为 `source_id → text` 后交给模型。文档 Evidence 的 facts 是真实 Chunk 原文，Structured Evidence 的 facts 是 JSON rows；Graph Path 仅保存在 Evidence metadata 和运行详情中，不进入最终模型 Context，source type、version、locator、retrieval method 和 score 也不进入 Prompt。回答后只允许引用当前 Evidence ID；持久化层能把文档引用回溯到 Chunk/版本/locator/标题，把结构化引用回溯到 Dataset/version/metric，但结构化引用尚无行级主键、实际查询快照或更细数据库 provenance，Graph Path 也不是独立可引用 Evidence。
- 所有 Tool 必须经过 `ExecutionGateway`；身份、scope、Action、活动版本、预算、超时、结果范围和 Citation allowlist 均由确定性 Runtime 校验，模型参数不能注入 principal、role 或 scope。
- 单次运行最多 6 次规划循环、4 次 Tool 调用，并受总步骤、60 秒超时、结果数量和结果字节预算限制；重复 Tool 参数签名不会再次执行。
- RunStep、ToolInvocation、Evidence 快照、Citation、Agent usage 和审计事件写入 PostgreSQL；Evidence 快照支持文档与结构化来源的历史详情重建。

### Agent SSE 实时事件

- 问答提交后由 API 进程内后台任务继续执行，前端通过 AG-UI 兼容的统一 SSE 事件流实时接收运行开始、公开步骤摘要、Tool 调用与结果、回答增量、引用、状态快照和终态异常。
- `agent_run_events` 按运行持久化 PUBLIC 事件并分配单调递增序号；事件读取执行运行所有者鉴权，不持久化或公开原始问题、AuthContext/scope、Prompt、隐藏推理及 Evidence 正文。
- `knowledge_search` 内部 Retrieval Workflow 使用 `ACTIVITY_SNAPSHOT` 和 `activityType=atlasmind.retrieval` 发布可审计检索活动，覆盖计划、查询处理、Vector/BM25/Graph 并行召回、Fusion、Rerank 和 Evidence 生成，并展示候选数、Evidence 数、耗时、选中策略与降级状态。
- 检索活动使用稳定 ID 并通过 `parentMessageId` 关联外层 Tool Call；后端和前端均按白名单发布/解析字段，不展示原始或改写 Query、HyDE 文本、Filter 值、相似度分数、模型原始 reason、scope 或 Evidence 正文。
- `GET /v1/agent-runs/{run_id}/events` 支持 `after` 与 `Last-Event-ID`，可在浏览器断线后按序回放遗漏事件；heartbeat 保持长连接，终态事件或终态运行追平最新序号后关闭连接。
- 最终 `STATE_SNAPSHOT` 以确定性持久化结果覆盖临时增量输出；引用校验失败或运行失败时不会把未校验的临时答案保留为最终结果。运行详情实时展示公开步骤摘要、Tool 状态、证据数量和异常信息。
- 取消和异常终态采用条件更新，迟到的后台结果或异常不能覆盖已经完成的取消/关机终态；API 优雅关机将仍活跃的进程内运行标记为 `AGENT_SHUTDOWN` 并写入公开错误事件。
- 当前恢复能力仅覆盖 SSE 事件重连与回放。Agent 执行任务仍在 API 进程内，进程崩溃后不会从中断节点继续执行；尚未接入 LangGraph Checkpointer 或独立 Agent Worker。

### 真实 API

- `GET /v1/capabilities`
- `GET /v1/documents`
- `GET /v1/documents/{id}/versions`
- `POST /v1/documents/{id}/versions`
- `GET /v1/agent-runs`
- `GET /v1/graph`
- `GET /v1/graph/policy`
- `PUT /v1/graph/policy`
- `GET /v1/rag/strategies`
- `GET /v1/rag/policy`
- `PUT /v1/rag/policy`
- 既有上传、撤销、问答、运行详情、图谱冲突、审批和评估接口继续保留。
- OpenAPI 源契约与前端 API client 已加入 RAG 策略接口；生成的 `schema.d.ts` 尚待重新生成。
- AgentRun 详情返回真实 `PLAN`、`RETRIEVAL`/`TOOL`、`COMPOSE` 和 `VERIFY` 步骤。

### 前端

- 前端 Docker 开发与生产构建阶段会按 `pnpm-lock.yaml` 校准依赖链接，并对 Tailwind CSS 与 AG-UI 核心包执行完整性检查；依赖缺失时镜像构建直接失败，避免以不完整 `node_modules` 启动容器。
- `/chat` 使用真实问答、真实引用和真实历史运行。
- `/knowledge` 使用真实文档、统计、版本、导入任务与撤销数据。
- `/runs` 使用真实运行、状态、证据数和详情数据。
- `/graph` 首屏以固定高度窗口展示当前授权范围内的真实实体和关系；“全局图谱”明确标记为重要实体子集，用户可在 20/40/80/120/200 档位中设置当前 Scene 的 Top 实体数量，达到查询上限时会提示仍有实体未展示并支持加载下一档。Sigma 画布在非全屏状态下具有明确可绘制尺寸，全屏仍是可选操作。缩小、缩放百分比输入、放大、定位和全屏集中在画布右上角横向工具栏，百分比会随相机状态更新并支持直接输入。实体搜索图标位于输入框右侧。实体/关系 Inspector 与 provenance 位于同一探索窗口右栏且可收起，并保留窄屏纵向布局。客户端通过 MIT 许可的 `graphology-metrics` PageRank 综合 degree/来源文档数映射节点重要度，通过 `graphology-communities-louvain` 计算社区并优化全局 Scene 初始分布；标签按缩放级别和重要度降噪，选中实体时相机平滑聚焦。页面下方继续展示实体保留策略、策略版本、只读状态和关系冲突，具备 `MANAGE` 权限的用户可以勾选实体类型并保存新策略版本。
- `/rag` 展示固定 Retrieval 阶段、Strategy Catalog、启用状态和预算；具备 `MANAGE` 权限的用户可以保存版本化策略。界面明确区分 Planner 产出 Plan 与 Runtime 执行 Plan，并在编辑时约束 Retriever/Fusion 和 Multi-Query/HyDE 冲突。
- `/approvals`、`/evaluations` 会读取运行时能力；能力未启用时禁用入口，不提交演示请求。
- 登录和侧边栏展示“本地超级管理员”及“本地真实数据”。
- 文档上传选择文件后会从文件名自动填写可编辑标题；保存位置固定展示为“企业知识库”，技术性的来源键和知识范围由系统生成；信息分级使用“公开、内部、机密”中文选项，负责部门收纳在高级设置中。
- 文档导入任务使用中文步骤、总进度和失败位置展示；发布成功后自动刷新文档、版本和当前活动版本，无需用户手动刷新确认。
- 文档列表和版本详情使用“已启用、已撤销、第 N 版、当前使用、已可用于问答”等业务语言；文件大小使用 KB/MB，完整文档与版本编号默认收纳在技术信息中。
- 运行中心以答案摘要、短运行编号和中文问答类型展示记录，不在列表暴露关联编号；运行详情展示服务端持久化的 Agent 决策、能力调用、回答生成和引用校验步骤，完整运行、关联和追踪编号收纳在可复制的技术信息中。
- 聊天页默认仅展示简洁 Agent 状态，用户可展开查看详细检索过程；运行详情中完整展示同一检索时间线，包括已完成运行的 SSE 回放。

### Windows 本地运行恢复

- Docker Desktop 已配置 Windows 登录后自动启动。
- 本地 Embedding 当前没有计划任务或启动项，Windows 重启后需要手动恢复。
- PostgreSQL、MinIO、Neo4j 和 OTel Collector 当前容器重启策略为 `no`，Windows/Docker 重启后应统一执行 `docker compose up -d`。
- API、ingestion worker 和 frontend 使用 `unless-stopped`，但仍依赖上述基础设施，因此不单独作为完整恢复依据。
- 具体命令和验证出口见 [WINDOWS_RESTART_RUNBOOK.md](WINDOWS_RESTART_RUNBOOK.md)。

## 最近验证结果

Knowledge Graph Explorer 增量验证（2026-08-27）：

- OpenAPI 类型重新生成，Graph Explorer 前端 TypeScript 检查和相关 ESLint 通过。
- Graphology Scene 增量去重/替换测试及治理页面交互测试共 6 项通过；FastAPI 契约测试 6 项通过。
- 内嵌图谱窗口增量通过前端 TypeScript、相关文件 ESLint，以及 Graph Scene/治理页面 6 项测试；真实浏览器 WebGL 布局和交互仍归入发布验收，不在本条中宣称通过。
- 图谱视觉、Top 数量选择与社区分析增量通过前端 TypeScript、相关文件 ESLint，以及 Graph Camera/Scene/治理页面 9 项测试；PageRank/Louvain 仅分析当前已授权 Scene，不扩大后端返回范围。真实浏览器 WebGL 视觉和大图性能仍归入发布验收。
- 图谱防重叠布局增量（2026-08-28）通过前端 TypeScript、4 个相关文件 ESLint 和 Graph Scene 5 项局部测试，覆盖 Local Graph 跳数径向位置稳定性及 Noverlap 节点分离；真实浏览器视觉效果仍归入发布验收。
- ForceAtlas2 Worker 生命周期修复（2026-08-28）不再通过 React Hook 复用可能已被清理的 Supervisor，而是在每次 Scene revision 布局时创建独立官方 Worker，并在清理阶段销毁。前端 TypeScript、相关 ESLint 及 Worker 生命周期/Graph Scene 共 6 项测试通过，覆盖旧 Worker 销毁后新 Worker独立启动；Top 120 的真实浏览器复验仍归入发布验收。
- 图谱布局参数已集中为按 Scene 节点数选择的 40/80/120/200 四档配置：节点越多，ForceAtlas2 斥力、Noverlap ratio/margin/迭代预算逐级增加，Sigma 标签密度逐级降低。该增量通过前端 TypeScript、4 个相关文件 ESLint，以及 Layout/Scene/Camera 共 9 项测试；真实浏览器的最终间距仍归入发布验收。
- 对当前真实 PostgreSQL 数据执行只读验证：Global 10 节点/18 关系；选定实体授权 degree 为 10；2-hop Local Graph 在 30 节点限制下返回 42 条关系；关系 evidence 回溯成功。
- Next.js Turbopack 生产构建在当前 Codex 沙箱中因辅助进程无法绑定本地端口而阻塞；webpack 构建又被既有 Next/TypeScript `--showConfig` 解析问题阻塞，因此本次不得报告生产构建通过。

验证日期：2026-08-27。Advanced RAG 后端、GraphRAG 导入修复和真实文档问答已复验；详细 Retrieval SSE 已完成针对性单元/组件验证，但按用户要求未执行本轮全量前端与容器验收。

| 检查项 | 结果 | 说明 |
|---|---|---|
| Ruff | 局部通过，全量阻塞 | 本次修改的两个源文件和回归测试通过；全量检查被既有 `openai_compatible.py:272` 中文标点正则的 RUF001 阻塞，本次未修改该无关代码 |
| mypy | 通过 | 123 个后端源文件无类型错误 |
| 后端常规测试 | 通过 | 132 passed，1 skipped；跳过项是需要显式开启真实基础设施的隔离用例 |
| GraphRAG 导入专项测试 | 通过 | 13 项 Neo4j GraphRAG adapter/runtime 与真实 API 契约测试通过；新增非法 Graph JSON 降级回归 |
| 两份真实 PDF 重试 | 通过 | `Rag答案` 生成 10 个活动 Chunk，`6 RAG深度` 生成 9 个；两者 Lexical/Vector/Graph 投影均为 READY 并进入 SEARCHABLE |
| 修复后真实问答 | 通过 | 外层仅调用一次 `knowledge_search`，返回 6 条 Evidence；最终 Citation 定位到 `Rag答案` 原始 Chunk，evidenceStatus 为 SUFFICIENT |
| 真实基础设施集成测试 | 通过 | 1 passed；覆盖 LangGraph 文档检索后按需切换 GraphRAG、Evidence 合并、业务实体过滤、跨文档别名对齐、两跳路径、关系 provenance、Graph/关键词/向量融合、原始 Chunk 引用、对象复用、异维向量、重启检索、trace、审计和撤销隔离 |
| 详细 Retrieval SSE 针对性验证 | 通过 | 相关后端 12 项测试、事件 Reducer 4 项测试及聊天组件 2 项测试已通过；时间线组件已增加独立测试 |
| Advanced RAG 与 SSE 全量前端/容器验收 | 未执行 | 按用户要求未继续执行全量 Vitest、生产构建、新镜像替换和浏览器验收；不得宣称本增量已完成发布验收 |
| 前端容器依赖修复 | 通过 | 无缓存重建并全新创建容器后，`tailwindcss` 与 `@ag-ui/core` 均可解析；`/login` 返回 HTTP 200，frontend 容器状态为 healthy |
| Playwright 核心旅程 | 通过 | 系统 Edge 实测本地登录、真实知识列表、真实运行列表 |
| 自动截图 | 通过 | 已生成知识库、运行中心、新版上传弹窗、友好版本详情和运行详情截图至前端测试产物目录 |
| 一键真实烟雾测试 | 通过 | 验证 MinIO、PostgreSQL、Neo4j、真实 DeepSeek/Embedding、引用、trace、审计、重启和撤销；恢复本地 Embedding 服务后已完整复验通过 |

最近一次完整通过的一键烟雾结果包括：`dataMode=persistent`、`jobState=SEARCHABLE`、1 条授权引用、MinIO 原文件存在、PostgreSQL 分块存在、4 个 Neo4j 来源实体、持久化 trace、重启检索、撤销过滤和运行审计关联均通过。该结果属于 2026-08-25 的旧检索编排基线，不作为本次 Advanced RAG Workflow 的真实基础设施验收结论。

本次 GraphRAG 修复的真实基础设施增量验证通过：两篇隔离测试文档通过 `Postgres`/`PostgreSQL` 别名复用同一规范实体，图谱浏览返回关系来源，Neo4j 返回 `USES → OWNED_BY` 两跳路径，测试文档随后已撤销。

## 已知缺口与风险

1. 企业 OIDC 和生产权限矩阵未实现；当前本地超级管理员仅适用于开发环境。
2. SQL 数据接入 UI 仍是占位能力；受控结构化查询 Runtime 已实现，但尚未配置真实业务 Dataset，默认不向 Agent 暴露。
3. 10 秒问答、10 分钟导入、60 秒多源任务、100 并发以及 RPO/RTO 尚未验收。
4. SBOM、许可证审查、容器加固、数据保留/删除和 LangSmith 生产接入尚未闭环。
5. 真实链路测试会在开发库留下已撤销的测试文档记录；后续需要独立测试租户或可清理的测试环境。
6. 跨文档别名对齐在新导入时执行；修复前已形成的别名重复实体不会自动批量合并，仍需通过后续治理流程审阅处理。
7. 当前 LangGraph 循环为同步有界执行，尚未接入 Checkpointer、异步恢复或独立 Agent Worker；长任务恢复能力尚未验收。
8. Advanced RAG 的 OpenAPI 生成类型尚未刷新，前端 TypeScript、组件测试、全量 Vitest、ESLint 和生产构建尚未执行；真实问答已验证外层仅一次 `knowledge_search`，但内部 Graph Strategy 选择准确率和带 graphPaths 的新 Workflow 仍需版本化数据集复验。
9. SSE 事件持久化、回放、前端消费、详细 Retrieval Activity 和终态竞态收尾已进入代码并完成针对性验证，但全量前端、容器、断线恢复和真实浏览器验收按用户要求留待后续自行执行。
10. 当前 `BM25` Strategy 的名称与实际 PostgreSQL FTS 实现不完全一致，且全文搜索向量缺少专用索引；真实 BM25 引擎、中文分词质量及规模性能尚未实现和验收。
11. 当前 Rerank 是 DeepSeek listwise LLM 排序，不是 Cross-Encoder；`bge-reranker` 的模型选择、服务方式、批处理、超时降级、资源规格和质量收益尚未实现和验收。
12. 当前 Evidence Pool 能跨 Tool 累积证据，但没有类型化 Context Builder；Graph Path 与来源 metadata 在 Compose 前被丢弃，Prompt 又把全部来源描述为“original document sources”，与 Structured Evidence 的真实类型不一致。
13. 多源 Tool 调用依赖外层 Agent 逐步重新规划，只支持串行调用；没有确定性、预算受控的跨源 DAG，也没有 SQL/Graph 输出到后续检索输入的 typed binding，不能宣称 `SQL → Hybrid` 或 `Graph → Hybrid` 已实现。
14. 结构化引用目前只能追溯到注册 Dataset、版本和 metric，缺少行级业务键、查询快照/参数摘要及结果生成时间等细粒度 provenance；默认 Runtime 未配置 Dataset，业务 SQL 链路仍不可用。
