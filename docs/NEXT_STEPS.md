# AtlasMind 下一步建议

本文只管理尚未完成工作的优先级、原因和验收出口。已实现事实见 [PROJECT_STATUS.md](PROJECT_STATUS.md)。

## 文档信息

| 项目 | 当前值 |
|---|---|
| 最后更新 | 2026-10-15 |
| 规划基线 | Advanced RAG 编排、AG-UI SSE 和详细 Retrieval Activity 已进入代码，全量前端、断线恢复和真实基础设施复验待完成 |
| 推荐节奏 | 先完成 Advanced RAG 与 SSE 发布验证，再持续化真实链路门禁和任务恢复能力 |

## 当前优先结论

**文档解析升级的真实语料验收**：Markdown/TXT、DOCX 表格及文字 PDF 的结构提取和有界分块已落地，事实见 PROJECT_STATUS。旧文档保留原解析结果；需要升级的资料通过原文档“上传新版本”处理。验收出口：用户用实际规则资料检查条件与例外、Word 表格金额/时限、PDF 页码及引用定位，换版成功后旧来源失效。OCR、复杂多栏/跨页合并表格、图片与文本框识别仍待真实样本触发后单独选型；本轮不宣称这些能力已实现。

**P2 AtlasMind 会话上下文增强**：记录保存与恢复已验收，模型尚未利用历史轮次。若推进语义续问，先确认范围并复用现有 Context 方案；验收出口为“上一条/它”等指代能够利用有界历史完成检索，历史模型回答不能替代来源证据，跨用户/撤权内容不可进入 Context，并有 token 预算与回归评测。此项不阻塞已完成的对话记录功能。

**易富路客服标准检索后续评测**：固定混合检索与50项定向回归已完成，事实见PROJECT_STATUS；当前真实样本检索约1.3秒，但业务端仍42～45秒。下一验收出口：基于易富路80个场景基线逐题审阅命中完整性、引用支撑和拒答质量，补充并发/分位耗时；单独定位Agent/PHP往返延迟，再决定是否扩大top数量或引入多跳。未完成语义基线前，不启用FAQ自动发布或将历史模型答案作为权威缓存。

**P1 两项目页面联调验收**：提交前定向回归结果已记录在PROJECT_STATUS，后续仍需用户验证真实页面操作。验收出口：商家顶部打开多个功能后可用标签返回及关闭，侧栏展开动画与箭头方向一致；联系总部和总部AI对话回车发送正常，智能客服引用在旁边窗口定位并黄色高亮，关闭后可继续原咨询。浏览器断线恢复、多商户并发及生产部署继续按既有验收范围完成。

**P1 商户使用手册页面验收**：完整正文、原文结构、精确选段及权限接口已通过定向验证，事实见PROJECT_STATUS。验收出口：刷新商家后台，在“服务 → 使用手册”阅读完整规则；在智能接待状态重新提问首次上架问题，点击新回答的“引用段落”，检查链接旁窗口、避让位置、全文上下文及黄色选段，窗口内滚动后可重新定位；旧回答仅显示灰色“参考范围”。页面不跳转，关闭后保留原咨询及草稿，旧版本/撤下来源应提示失效。页面效果由用户验收；继续评测其他规则问题、模型摘录格式异常和范围不匹配，有限实测不代表全量引用语义质量。

2026-10-12易富路8份知识正文已导入并可检索，6份公开资料与2份总部内部资料保持隔离；商户经营助手也已接入公开scope030。问候门槛、plan类型、初始化租约、恢复期限与知识上下文预算修复及有限真实链路结果见PROJECT_STATUS。**下一验收出口**：用户在两个商户页面重放已通过的问候、首次上架及会员统计问题，检查实时答案与引用；旧咨询若已转人工，须明确恢复智能接待。继续完成资料包其余样例、换版/撤销、页面断线恢复和多商户并发验收，不把有限HTTP测试视为UI或规模质量通过。

商户自动客服恢复与 AtlasMind 客服同源接入的可验证结果已迁入 PROJECT_STATUS。**当前人工验收出口**：刷新商家“联系总部”与总部“商户客服协同”，有依据问题直接出现AI回复和引用；无依据或服务失败进入待接待队列，总部管理员/平台-客服领取后回复；恢复智能接待须明确操作，人工领取后不出现迟到AI；普通简历仍只用于总部普通知识。还需在实际页面检查知识换版、撤下和来源失效提示。

**P1 稳定性与语义复验**：已定位并修复的plan类型、初始化续租、截止时间、上下文预算及问候发布问题见PROJECT_STATUS；有限HTTP通过不证明长期稳定。验收出口：继续覆盖多轮、并发、模型格式异常、无依据、显式恢复与人工抢占；依据run/op/code/site定位失败，保留预算，不泛化为资料不足。对收费/合同等回答评审不受资料支持的全范围断言与能力承诺，确保不能把“可核对合同”理解为系统已有合同查询工具，不记录凭据或私有文档原文。

总部普通知识问答已接入并通过原简历问题的真实模型/HTTP/SSE验证，最新事实见 PROJECT_STATUS。**人工验收出口**：易富路总部AI对话刷新一次后，新提问“介绍陈文帝的简历”，过程、答案和PDF来源直接出现；后续提问不需要刷新才能看到记录。UI和真实浏览器断网恢复尚未验收。商品/订单等业务问题仍使用原总部模型，需在该账号模型设置更新供应商认可的密钥并测试连接；不能用知识路径通过替代业务模型验证。

本机三阶段 MVP 的代码与真实链路已落地，已验证事实已迁入 PROJECT_STATUS。下一步由用户验收：在 AtlasMind 上传时选择“商户通用客服知识”，在易富路 AI助手客服设置进入同一工作台，验证自动回复及总部建议显式采用，并验证新版本及撤下后的提示。**验收出口**：实际页面可完成上述流程，普通资料不进入商户客服，旧来源不能继续采用；不得将未执行的 UI 验收视为通过。

试点扩展前继续完善真实业务代表语料与质量评估，尤其无依据问题、政策冲突、中文召回及峰值超时。已有三条FAQ及新增8份手册规则资料；历史15问与本次有限抽查不代表规模质量。**验收出口**：核准语料上的回答/引用评审和耗时报告，外部检索模型调用成本按日志单独核算；自动回复仅使用已授权商户通用客服scope，不继续扩大普通文档、业务写入或消费者渠道权限。

完善干净环境的可复现部署：SQLAlchemy asyncio extra 与 lock 已补齐，但本机仍用此前派生镜像；独立服务 Compose 当前引用本机镜像与现有业务网络。**验收出口**：新环境按锁依赖构建，迁移、API/worker、受限服务和回归通过，并明确本地 MinIO 构建来源。SSO、生产多账号管理、任务授权、CAS、SQL 数据源与 durable Agent worker 继续后置，不属于本机 MVP 已完成能力。

本机原定 MinIO 镜像在 Docker Hub/Quay 返回授权错误，官方历史二进制返回 410。应记录可复现、固定来源的构建或受信分发方式，不以不明镜像替代；本次固定版本源码构建结果见接入方案执行记录。Windows 旧 uv 获取的 CPython 3.14.0a6 启动 pytest 崩溃；后续开发需稳定 Python 3.14 或标准 Linux 容器，不能将该环境视为通过的测试基线。

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

本次已验证认证 SSE 代理入口、组件连接生命周期、HTTP 的 `after`/`Last-Event-ID` 回放和原简历问题的两次完整问答；后续继续验证真实浏览器断网/恢复、重启后的模型预热与并发，不重复将这些局部通过视为完整 SSE 发布验收。**增量验收出口**：重启恢复按手册先完成 BGE-M3 预热，原问题仍命中简历；浏览器网络中断后能按游标补齐且无重复回答；模型不可用时显示可重试检索失败，不能误报文档不存在。

同日复核发现开发前端仍提供旧脚本，现已重新加载进程并验证实际页面资源与新提问的 SSE。**部署验收出口**：刷新旧页面一次后，提问与运行详情均实时显示回答和终态，不再需要每次刷新取得记录；后续源码更新要检查实际下载脚本，若开发进程继续提供旧资源，按恢复手册仅刷新前端。易富路总部查询 Worker 与共享事件服务已恢复，需手动验收两个页面；具体文件监听根因与真实浏览器恢复仍未验证。

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

### 有质量证据后评估真正 BM25 与专用 reranker

**当前基础与优先级**：第一、第二阶段已经提供共享中文分词、长度归一化、GIN索引、构建身份、批量/向量缓存及分段观测。策略id `bm25`仍使用PostgreSQL FTS。当前30问中混合指定来源Hit@5为27/30，模型listwise重排30/30降级，客服默认关闭该额外调用；企业/HQ策略保持原配置。下一步先人工判定未命中样本与重复来源、扩充否定问法/编号/长文跨段数据集，再比较专用reranker或严格BM25，不能因名称或成熟度直接增加部署组件。

**邻块与缓存验收**：旧语料章节未知，先选择真实长文通过原版本上传入口重解析，核对引用和跨段回答，再评估开启`ATLASMIND_RETRIEVAL_EXPAND_NEIGHBORS`。持久Embedding缓存当前无自动淘汰；随容量增长补充保留/清理策略与缓存量监测。查询向量缓存没有证据缓存的撤权风险，但仍需实际并发/内存/模型修订演练。验收须比较当前基线的检索质量、引用有效性、用户端时延和费用，不能用30题本地检索中位数代替端到端P95。

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

回答阶段重名规则已更新至 `grounded-identity-v2`，通过原始简历问题的两次真实链路与六条合成场景的 JSON/流式评测，已实现事实与前次验证更正见 PROJECT_STATUS。后续增加未参与 Prompt 调整的独立保留集，覆盖新姓名、身份冲突、明确身份限定和来源注入，并在模型或 Prompt 升级时复跑；当前六条调试场景的通过不能替代泛化评估。将本轮原问题的 PostgreSQL FTS 零候选纳入中文召回评估，明确向量服务失效时关键词检索的实际覆盖。

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
