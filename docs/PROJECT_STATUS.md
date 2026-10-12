# AtlasMind 项目实现状态

本文只记录能够由当前代码、测试或实际运行验证的事实。设计稿、规格和任务勾选不单独作为完成证据。

## 文档信息

| 项目 | 当前值 |
|---|---|
| 最后更新 | 2026-10-12 |
| 基线分支 | `001-enterprise-agentic-rag` |
| 基线提交 | `7203769ae3f7c847b5f3925d20e9ce3939565b7f`（本轮改动前的提交基线） |
| 当前阶段 | 真实业务链路型 MVP；尚未生产就绪 |
| 公开仓库 | <https://github.com/Zoe-Well/AtlasMind> |
| 配套规划 | [NEXT_STEPS.md](NEXT_STEPS.md) |

## 当前结论

### 2026-10-12 两项目提交前定向复查

AtlasMind沿用隔离数据库入口执行65项存储/服务授权/手册/API/模型适配器检查通过；总部知识、手册结构与LangGraph单元27项通过；检索失败持久化/SSE终态另在新建隔离PostgreSQL数据库重放2项通过。共94项后端检查通过，临时数据库均已删除，没有消费用户导入任务。12项按需真实模型身份评测本轮未重放，不计为通过。前端实际开发容器执行`agent-stream.test.tsx`2项及TypeScript检查通过；宿主机缺少Vitest可执行依赖的启动不计作通过。

易富路源码、测试、知识手册和运行文档已在`codex/marketing-activities-20261008`形成并同步提交`8495e66d`，远程提交号已复核；提交前83项组件和33项商户运行时检查通过。本轮AtlasMind配套改动按既有`001-enterprise-agentic-rag`分支交付；凭据、数据、编译产物和测试证据沿用忽略规则留在本地。没有新增真实模型调用、浏览器验收、镜像构建或现有服务重启，完整页面操作与生产部署验证仍待验收。

### 2026-10-12 商户使用手册与引用定位

同日引用交互更新：易富路商户点击客服引用改为链接旁的文档浮层，不再跳转新标签页，浮层与使用手册共享正文/高亮组件；打开才请求原同版全文接口，关闭、换引用/账号或停用拒绝迟到内容。原文定位仅滚动浮层窗格。Atlas接口、知识权限和模型未变。易富路统一入口末次20项真实HTTP及54项组件检查通过，4个前端模块HTTP200编译并源码热更新，无重启；浮层位置、点击和视觉效果待用户验收。下述新标签页描述为此前历史。

同日最新增量（替代下述初版分块阅读）：商户手册支持`view=document`读取同一活动版本的完整正文；Markdown从不可变原对象恢复标题、列表等结构，复用现有MarkdownIt/BeautifulSoup，校验其规范化文本与入库段落一致后输出安全节点树。非Markdown或结构不匹配时回退安全文本，不承诺PDF/Word版式。旧chunk视图接口保持兼容。完整读取有500块、120KB正文与250KB返回上限，范围不完整则拒绝；没有模型调用或文档副本。

新客服回答在原最终模型调用中生成answer及原文摘录；Python和PHP分别验证唯一、完整段落摘录，PHP由签名来源计算paragraph_start/end和quote_digest。阅读时复核chunk摘要、版本、选中范围与摘录摘要，仅选中段落黄色高亮；旧回答未记录选段时显示灰色“参考范围”。没有增加模型调用或扩大客服权限。真实上架问题run623通过，引用第4–6段而非原整块1–28，真实认证HTTP成功打开同版完整Markdown及precise范围，3次商户模型调用、36秒。证据：易富路`.local-backups/manual-precise-knowledge-20261012.jsonl`。联调失败run622保留，原因是新增缓冲路径遇到流回调为None，已补传输回归并修正，不把失败记作通过。

最新定向验证：手册结构/参数及真实PostgreSQL16项、安全/HQ41项、商户Agent33项、PHP业务回归72项、真实手册HTTP20项、手册/客服/备注组件48项通过。会员口径run624也通过，两条引用分别定位统计规则21–25段、后台手册31–33段，均通过完整Markdown与范围HTTP核验，3次调用/43秒；证据为易富路`.local-backups/manual-precise-metrics-20261012.jsonl`。主工程/插件文件一致，SFC编译与实际Vite模块HTTP200通过。源码挂载，只重载客服listener和商户Agent，无镜像构建、凭据更改、真实咨询修改或代码提交；视觉、点击与滚动仍待用户验收。以下记录保留初版历史证据。

同日后续纠正：前次仅验证了易富路后端菜单，未覆盖商户专用侧栏固定配置；用户反馈后通过实际组件执行复现入口遗漏，已在“服务”子目录补齐。新增侧栏回归先失败后通过，手册相关6项通过，实际开发模块已含入口。文档读取接口及引用高亮合同保持，用户仍需验收页面效果。

受限客服服务新增 `/v1/knowledge/manual/list`、`/manual/read`，只接受 `merchant-manual` 专用用途，要求服务器签发的正整数商户/账号及 run_id=0；该用途不能检索、校验或调用总部问答。阅读复用现有固定客服 scope 和活动版本/分块，目录按标题搜索分页，正文按实际分块分页；不调用模型或复制上传资料。文档、版本、片段各层执行范围过滤，引用版本与摘要不匹配或文档撤下时拒绝读取，正文只作文本展示。

易富路“服务 → 使用手册”及商户客服引用链接已接通。点击引用在新标签页打开准确版本、定位并高亮引用片段，保留原咨询标签页；同一文档的不同引用分别定位，阅读后可用“定位引用”返回。引用新增chunk_id/digest，旧返回字段兼容；原始客服结果中已有这些标识的历史消息无需迁移即可生成链接。仅开放商户公开知识，不开放总部内部资料。

验证：受限接口安全/HQ单元41项、真实PostgreSQL事务回滚8项、易富路真实认证HTTP16项、手册/客服/备注组件46项、原客服Agent事务回归64项通过；涉及PHP语法、Vue脚本/模板及实际5183模块HTTP200检查通过。末次统一入口证据为易富路`.local-backups/manual-workspace-20261012.log`，含旧版本明确提示断言；初次HTTP明细为`.local-backups/merchant-manual-http-20261012.json`。仅创建并清理合成账号，不写真实咨询、不调用模型。宿主旧Python预发布环境启动pytest崩溃，改用已有容器运行通过。源码挂载，沿用统一入口只重载客服知识listener，未构建镜像、未修改凭据。UI点击、滚动和视觉效果待用户人工验收。

### 2026-10-12 商户经营助手共享公开客服知识

用户授权修复两个商户入口并共享公开规则知识。受限客服listener新增接受`merchant-assistant`用途，固定scope030；原`merchant-auto`、`hq-draft`及独立总部scope020保持。易富路适配器校验merchant_ai权限、完整运行owner、V2协议和auth_revision，禁止跨商户/跨product_mode借用任务；检索要求活动运行，历史来源仍执行活动版本/digest复核。无管理路由或总部内部资料扩权。

服务安全/HQ单元35项通过；真实受限接口以新用途校验3项：公开文档02可用，内部文档07/08拒绝。易富路业务回归64项、执行器30项通过，覆盖初始化续租、恢复后的有界执行窗口、非法plan、无引用固定接待消息、明确问候/帮助不依赖模型JSON及知识投影不修改原签名来源。商户助手真实认证HTTP/模型/结果/事件回放4项通过（run559—562），涵盖问候、商品首次上架、会员统计口径、近7天经营查询；后两类分别实际调用knowledge_search与business_report。数据查询使用合成商户，未操作真实商户记录；UI与质量泛化未验收。证据：易富路`.local-backups/assistant-repair-accepted-20261012.jsonl`，本机`.data/exports/merchant-assistant-scope-check-20261012.json`。

沿用既有运行入口重载客服listener与商户Agent，未构建镜像、未改凭据；本次过程中真实助手测试曾暴露无检索答复、资料超预算及最终发布超时，修正后末次上述4项通过，失败记录保留。调用外部知识的简单助手任务与客服使用分类后最多60秒窗口，仍受接收起120秒和已有根截止时间限制，模型/工具/Token上限不变。

联系总部末次run582—585的4道真实HTTP问题均通过，含0模型调用的固定问候、两道规则检索和有引用的费用边界说明；额外显式转人工及总部领取检查通过。来源与自动发布结果见易富路`.local-backups/service-repair-accepted-v3-20261012.jsonl`。未改真实用户原咨询的人工状态。语义质量仍需评审：不得将样本中泛化的合同核验措辞视为新增合同查询工具或人工业务承诺。

最终决策提示调整后，商户助手另行重放“商品首次上架需要总部审核吗？”通过（run586）：实际调用knowledge_search、返回活动来源，一次执行46秒；证据为易富路`.local-backups/assistant-policy-final-20261012.jsonl`。

### 2026-10-12 易富路知识资料包本机导入

按用户授权，将易富路`docs/product/knowledge-base/`的8份Markdown正文经现有上传接口导入：01—06为客服scope尾号030、PUBLIC，07—08为普通scope尾号020、INTERNAL。来源键为`yifulu-knowledge-pack/YFL-KB-001`至`008`；原有FAQ、个人简历及撤销记录保留。全部8个任务达到SEARCHABLE，各有一个活动版本、2个活动分块，共16个分块；只读核对文档/版本/分块范围及信息分级一致。BGE-M3预热后使用现有worker完成入库，没有重启或构建镜像。

真实服务检查20项通过：商户商品首次上架及新增买家口径两问命中新资料并通过引用校验；总部两问分别引用总部手册和知识维护手册并生成符合资料的答案；两个服务对全部8份资料各抽一块做16项引用校验，同范围接受、跨范围拒绝。有限样本不代表完整问答质量或UI验收，未在本轮换版/撤销资料。证据为本机`.data/exports/knowledge-pack-import-20261012.json`与`knowledge-pack-verification-20261012.json`；资料包README同步记录范围与结果。

导入时尚未修复的问候发布门槛及plan类型问题，现已在同日后续商户回复修复中处理，见上节和易富路专项状态；导入检查本身仍不算业务聊天验收。

### 2026-10-12 商户自动客服恢复与客服知识同源

用户授权按优先级恢复商户“联系总部”智能回复、接入客服知识并完善人工交接。客服 listener 现同时接受 `hq-draft` 与 `merchant-auto`，共用固定 scope 尾号 030；总部普通知识仍为独立 scope 020、服务及密钥。PHP 校验任务、提供者账号、商户及事项版本，检索和来源复核复用现有服务；不开放管理路由，不把普通简历加入商户客服知识。

实际复现容器请求千问时 TLS 连接失败：Docker Desktop 手动代理指向已停止的 `127.0.0.1:7890`。已备份设置并热切换至系统代理，模型凭据和证书校验保留，未重启 Docker/电脑。另一故障是检索存储依赖停止，listener 存活不能证明可检索；统一启动入口现补齐依赖启动等待、本机 Ollama 预热及 `-ReloadKnowledgeService`。向量冷启动约 4.5 秒超出客服单路预算，预热后约 344ms；空证据且检索分支失败明确返回 503，避免误报没有资料。

易富路自动回复失败按当前事项版本幂等转人工并提示安全错误类别，入队失败保留商户原消息；人工领取、交接或新消息继续阻止迟到 AI 发布。恢复智能接待须明确操作且 Worker/模型就绪。自动回复与人工建议共用模型传输和客服来源，外部知识启用时不因失败静默回退旧知识；客服设置入口指向 AtlasMind，停止显示无效的旧本地编辑表。

本轮真实网关验证 run500/501 两项通过：商品上架审核问题发布带 AtlasMind 活动文档引用的回复；无依据费用承诺在两次检索后达到处理上限，转人工、没有向商户发布模型澄清正文或伪造引用。合成账号/咨询/令牌精确清理，模型运行与消耗账本保留；易富路证据 `.local-backups/support-auto-atlas-http-debug-20261012.jsonl`。恢复网络后的原本地知识 run481/482 也通过，属于接入前基线。

服务安全/HQ 单元 34 项、隔离真实存储/接口/模型适配器 46 项通过（两组包含重复用例，不累加为去重总数）；后者覆盖换版、撤下、摘要与跨范围复核，临时数据库已删除。易富路客服状态/隔离回归45项、组件逻辑34项、Python运行时26项通过，相关PHP/PowerShell语法和Vue脚本/模板编译通过。仅重载商户Agent和客服listener、恢复停止依赖，普通PHP/Vue源码挂载与HMR生效，未建镜像、未提交代码。未执行浏览器UI、全项目回归、生产容量或广泛模型质量验收；调试中run498/499曾出现PHP bridge拒绝，最终两项成功不证明所有间歇故障已定位或长期稳定性。

### 2026-10-11 易富路总部普通知识问答接入（最新）

用户确认总部“AI助手 → AI对话”接入普通上传文档。新增独立 `hq-knowledge-service`，固定普通 scope 尾号 020，仅提供 `/v1/knowledge/answer` 和引用复核；客服服务仍为尾号 030。两者使用独立密钥、issuer/audience/sub，短期令牌由 PHP 根据当前总部身份和任务签发；没有宿主机端口或管理路由。普通文档不会因本次接入进入商户客服范围。

知识问题由 AtlasMind 分类、检索并按 `grounded-identity-v2` 生成回答；业务问题继续原总部工具及账号模型。明确编号查询、帮助和绑定业务对象的会话沿用原路径。来源包含 document/version/chunk/digest、标题和定位；生成后、发布前、SSE读取及历史展示均复核有效性。服务异常明确失败，不回退为无依据回答。知识路径先完成模型生成，再经原 HQ SSE 分块发布正文，不是上游模型 token 流。

实际通过易富路认证 chat 路由以合成总部账号两次重放“介绍陈文帝的简历”（运行 218、219），均 succeeded、source=hq_atlasmind，只引用现有简历 PDF 的活动版本，答案采用现代求职者身份。账号无易富路模型配置也能完成；真实 SSE 正文与持久答案一致、有 knowledge_search 和完成事件，历史保留相同引用。末次 26 项真实模型/HTTP/凭据隔离/失效来源屏蔽/服务失败关闭/回放检查全部通过；另 10 项无模型 HTTP 回归通过。合成用户、令牌、会话、任务和事件已清理；不打印或记录简历正文。证据为易富路本机 `.local-backups/hq-knowledge-live-check.json`。

AtlasMind HQ 单元及服务安全测试 31 项、隔离临时 PostgreSQL 的存储/接口/模型适配器回归 45 项通过；临时数据库已删除，两组含重复安全用例，不作去重总数。相关 Ruff 通过。易富路组件逻辑 17 项、Vue脚本/模板编译、相关 PHP/PowerShell语法检查通过；实际5183管理端模块HTTP200，包含引用标题/定位及知识服务错误提示，两份插件源码一致。未进行浏览器UI、全量项目、容量或泛化质量验收。

已执行 `scripts/Start-YifuluMvp.ps1 -EnableHqKnowledge`：首次创建总部知识服务、仅重载总部问答Worker，源码挂载生效，没有镜像构建或电脑重启。原总部任务217的业务模型仍被供应商拒绝鉴权，业务问答需用户在模型设置更新有效密钥；本次没有替换该账号密钥。

### 2026-10-11 实时连接部署复核（最新）

前次 SSE 源码与接口测试通过后，实际开发前端仍提供旧的 `/api/agent-runs/{id}/events` JavaScript，导致用户页面继续连接 404。主机和容器挂载源码均已更新，不能用源码检查替代实际发布资源验证。本次仅重新加载现有前端容器；重新获取认证 `/chat` 及其脚本，确认 EventSource 使用 `/api/platform/agent-runs/{id}/events`。尚未定位开发服务器未失效旧资源的具体监听机制，不据此修改打包器。

通过实际前端 HTTP 入口重新提问“介绍一下陈文帝的简历”，运行 `0a8f0680-aeaa-462f-8079-7df3a92d5fe9` 为 COMPLETED，SSE 200、有回答增量和完成事件、一个简历引用。摘要见本机 `.data/atlasmind-sse-deployment-check.json`；相关组件连接生命周期两项回归通过。已打开的旧页面需要刷新一次以取得新脚本；本轮未操作浏览器，也未验证真实浏览器断网恢复。

配套易富路确认总部 chat 任务 214 一直 queued，缺少总部执行进程，且共享 SSE 进程因 `Workerman\Http\Client` 缺失反复退出。已通过易富路统一脚本补齐锁依赖、重新加载事件进程、启动仅总部查询的 Worker。PHP 开发服务器以 root 写共享日志，原 www-data Worker 随后因日志写权限无法领取任务；总部查询 Worker 改用独立运行卷，不调整业务日志目录、审核/执行开关或分析进程。原超期任务变为 timed_out，新合成任务 216 正常完成。10 项真实 HTTP/授权/回放检查、14 项事件转发回归、21 项相关客户端逻辑检查通过；合成账号与任务已清理。易富路验证不含真实模型或浏览器 UI，运行说明及详细证据见其既有 operations 文档。

### 2026-10-11 实时连接与 Embedding 冷启动修复

复现运行 `69565dcf-5d0d-467b-a94e-0fec396dce4f` 连续三次检索无证据：向量/图策略约 2500ms 时取消，关键词策略候选为零。原简历 PDF 有 2300 字的活动、可搜索 Chunk 和 1024 维向量；BGE-M3 冷启动实测 4192ms，超过单策略 2500ms 预算，热态容器请求为 285～300ms。此次没有重传或重建简历索引。已按用户确认配置 Windows 用户级 `OLLAMA_KEEP_ALIVE=-1` 并重启 Ollama、预热模型；后续 OpenAI-compatible Embedding 请求后仍验证为常驻，约占 1.7GB 显存。重启恢复入口为 `scripts/Warm-LocalEmbedding.ps1`，详见 Windows 恢复手册。

实时连接复现为页面 `/api/agent-runs/{id}/events` 返回 404，现有认证代理 `/api/platform/agent-runs/{id}/events` 返回 200。问答页和运行详情已接到统一代理；QUEUED → RUNNING 快照不重建 EventSource，终态清除连接错误并关闭连接。实际 HTTP 验证未登录 401、不存在运行 404；`Last-Event-ID` 与 `after` 均只回放游标后的事件。检索失败且无可用证据时改为 FAILED、既有公开错误码 TOOL_FAILED、可重试提示；成功的空结果仍说明证据不足，已有有效证据不会因部分策略失败而丢失。权限、公共 Schema 和检索预算保留。

对前次重名验证的更正：`grounded-identity-v1` 实际回答仍夹带历史人物解释和条件式澄清，原来的少量禁用词检查不充分。已加强来源身份规则与问题/文档边界为 `grounded-identity-v2`，扩展完整合成履历、混杂来源以及禁用词断言。通过前端认证入口连续重放两次原问题，运行 `e49d40b4-a167-48b8-8d07-97f955226562`、`76828d81-93be-4756-b992-9fa6b070e6fc` 均 COMPLETED，SSE 有回答增量和终态，直接介绍求职者、只引用原简历 PDF，未引入历史身份或要求先澄清。

验证：前端相关组件/事件/请求边界测试 10 项通过，TypeScript 与相关 ESLint 通过；后端针对性回归 82 项通过、12 项按需模型测试跳过，包含隔离临时 PostgreSQL 的检索失败持久化/SSE 终态测试，数据库已清理；12 项真实模型身份评测另行运行全部通过。日志见本机 `.data/chat-recovery-regression.log`、`.data/answer-identity-v2-live.log`，问答摘要见 `.data/chat-recovery-api-check-1.json` 和 `-2.json`。新增 Agent/持久化代码与测试 Ruff 通过；本机 Ruff 对模型适配器仍报告既有正则的 5 项 RUF001，对 real_mvp.py 未改动的 allowlist 校验报告 2 项 UP038，未宣称全量 lint 通过。本轮未验证真实浏览器断网恢复、全量回归、生产构建或泛化质量；合成评测仍属于调试回归集。隔离测试的默认 localhost OTel 导出失败日志不影响上述测试结果，不代表该隔离容器已验证遥测连通。

### 2026-10-11 回答阶段重名歧义修复（此前验证，结论已更正）

实际复现确认：上传的陈文帝求职简历已解析、索引并进入回答证据，旧运行 `62f71575-e00d-4e03-a815-32e11ec4f6d4` 仍把姓名解释为历史人物。按 RAG 规格 FR-011/FR-012、research 第 10/12 节与 plan 的证据约束，在现有模型适配器的 JSON/流式回答中统一应用 `grounded-identity-v1`：未限定姓名优先采用授权来源中的身份；显式指定其他身份但证据不足时说明不足；来源中有多个可能身份时澄清，不合并履历；来源指令仍作为不可信数据处理。公共接口、权限和检索流程未因此调整。

当时通过真实 `/v1/agent-runs` 重放“介绍一下陈文帝的简历”，运行 `00e58bf5-0c9b-45f3-a358-3fb487151843` 为 COMPLETED，包含简历教育背景和 AI 开发经历，并引用上传 PDF；后续复核发现仍有历史人物混淆，不能据原来的禁用词检查判定修复完成。旧运行与本机 `.data/answer-identity-api-check.json` 保留为此前验证记录，以本节上方修复复验结论为准。

针对性回归 61 项通过，10 项按需真实模型用例在普通回归中跳过，随后独立运行全部通过。五条合成场景分别覆盖现代简历重名、明确历史身份、多个来源同名、无关证据和来源注入，每条验证 JSON 与流式回答；数据集不包含用户简历原文，评估记录适配器/数据集摘要、模型与 Prompt 版本。日志见本机 `.data/answer-identity-regression.log` 与 `.data/answer-identity-live.log`。测试文件 Ruff 通过，适配器仍有既有中文标点正则的 5 项 RUF001；本轮不是全量回归或独立保留集评测，也不代表已完成 Context Builder、语义事实逐条校验或生产质量门禁。

### 2026-10-11 易富路精简 MVP 实施（最新）

已实现本机“上传商户通用客服知识 → 易富路总部生成建议 → 人工采用发送”。当前已导入易富路实际发布的三条通用 FAQ，开启仅限总部 draft 的试点；自动回复开关与原有自动回复知识来源未改变。普通上传默认进入普通知识范围，只有上传时明确选择“商户通用客服知识”才进入独立服务范围；本机分别使用尾号 020 / 030 的 scope。普通资料不进入客服候选集，过滤先于重排和回答模型。上传新版本与撤下入口已接通；换版继承原文档范围，不复制管理员的全部授权范围。

新增独立 `knowledge-service`，仅提供签名服务认证的检索与引用复核，不装配管理路由、不发布宿主机端口。它单独连接现有易富路内部网络；原管理 API、数据库等未加入业务网络。HS256 短期 JWT 校验 issuer/audience/expiry/用途，调用方 merchant/run 由 PHP 生成；浏览器与模型不能选择凭据、地址、范围或 provider。每次检索最多 2 次生成、3 次 Embedding、5 条各 2000 字结果，6 秒流水线 / 6.5 秒接口期限、2 个并发槽；记录实际尝试调用数、Embedding 字符量、耗时和关联 ID，不记录密钥或知识原文。

易富路保留业务只读工具、商户过滤、额度、Source 签名、事项版本及人工接管机制。外部知识仅由服务端 draft 任务启用，搜索异常不会静默使用旧知识。展示、采用发送和历史消息均复核外部 document/version/chunk/digest；非回答结果不把检索候选伪装成引用。管理入口位于现有 AI助手客服设置内，跳转同一本机知识工作台。

实际验证：真实模型 `atlasmind.smoke` 返回 passed，包含 PostgreSQL 分块、MinIO 原文、Neo4j 投影、重启后检索、引用、撤销过滤及审计关联。15 个版本化代表问题全部通过来源有效性检查，最终复跑单题检索与回答合计 2～3.37 秒；这是小语料功能验收，不是容量基准。真实易富路 Agent 合成商户回归通过知识建议、人工采用发送、订单只读、无依据保留人工处理（run 466～468）；夹具清理、模型调用账本保留。试点第二轮检索未包含普通资料。

自动化：隔离 PostgreSQL 临时数据库的 MVP 针对性回归 33 项通过；易富路 233 项数据库检查、33 项组件逻辑测试、25 项 Python Agent 测试通过；AtlasMind 前端类型检查通过。最终全量后端回归 154 项通过、14 项跳过（10 项按需真实模型身份评测、4 项按需真实存储测试），日志 `.data/backend-mvp-regression.log`；实际存储与模型验收结果单独记录，不能将跳过视为通过。新增服务相关代码 Ruff 通过，模型适配器仍有既有中文标点正则的 5 项 RUF001，未宣称全量 lint 通过。UI 未操作浏览器、未登录或截图，由用户验收。

真实回归定位并修正两个问题：旧导入晚完成可覆盖新版，现于索引事务开始锁定文档并拒绝已撤销/过期任务；DeepSeek 默认思考模式耗尽 1800 token 导致空正文，新增可选 `CHAT_THINKING_ENABLED`，本机设 false，其他端点默认行为保留。SQLAlchemy 明确声明 asyncio extra，并最小更新 lock；本轮普通源码通过挂载及必要进程重启生效，没有重建应用镜像。部署、回退与验收入口见 [接入方案](YIFULU_INTEGRATION_PLAN.md#9-三阶段实施与验收记录)。以下同日记录为此前时点事实。

### 2026-10-11 BGE-M3 本机配置验证

Windows Ollama 已提供 `bge-m3:latest`（模型 digest `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`）。本机 `.env` 的独立 Embedding 端点设为 `http://host.docker.internal:11434/v1`，模型名 `bge-m3`；保留已有 Chat 配置。沿用当前 Compose 文件组合，仅重新创建 `atlasmind-local` 的 API、ingestion worker 和 knowledge-service。

宿主机 OpenAI-compatible Embedding 请求返回两条 1024 维向量；上述三个容器分别通过项目 `OpenAICompatibleClient.embed()` 实际请求及向量数量/维度断言，配置缺失能力列表均为空。API、knowledge-service 健康检查正常，worker 已运行；Ollama `ps` 显示 BGE-M3 使用 100% GPU，加载占用约 1.7GB。此次未执行 Chat 推理、真实文档导入/图投影/问答/引用全链路或性能评测，不能据此宣称完整 RAG 烟雾通过。下方首次核查中的模型未配置结论为此前时点记录。

### 2026-10-11 本机核查增量

在 Windows `D:\word\dianshang\AtlasMind` 核查并启动独立 `atlasmind-local` Compose 项目，使用 3001 避让易富路已占用的 3000，发布端口仅绑定 127.0.0.1。易富路仅只读分析，未更新其代码、容器、运行凭据或数据。

本次标准 Linux 本地派生后端镜像已执行 31 项针对性测试并通过，范围为 SQL 白名单/参数化/模型参数越权拒绝、缺模型失败处理、事件存储、授权上下文、知识权限、运行记录授权、图路径授权和 Prompt 注入边界；不代表真实多商户 API 已通过。前端容器 `pnpm typecheck` 通过、关键依赖可解析，`/login` HTTP 200。独立 PostgreSQL 迁移至 `0015`、pgvector/pg_trgm/uuid-ossp 扩展存在；Neo4j `RETURN 1` 成功。UI 完全留给用户验收，未操作浏览器。

最终 7 服务均已启动；API、前端、PostgreSQL、MinIO 为 healthy，worker/OTel 正常运行且无重启，MinIO 与 Neo4j 管理入口 HTTP 200。MinIO 固定版本官方源码编译成功并构建本地镜像，非 upstream分发镜像。API health 为 persistent，文档/运行真实列表为空，RAG/Graph策略读取成功；OpenAPI 20 个 path，数据源/SQL/审批/评测管理路由不存在。CHAT/EMBEDDING 均未配置，真实问答请求返回 503/MODEL_CAPABILITY_NOT_CONFIGURED，伪造 scope 请求字段返回422；没有真实模型烟雾通过结论。

首次标准后端镜像因未锁版本 `pip install .` 获取 SQLAlchemy 2.1、未安装 greenlet，Linux 测试导入失败；本地派生镜像补装锁文件已有 `greenlet==3.5.5` 后上述测试通过。Windows 旧 uv 获取 CPython 3.14.0a6，pytest 启动进程崩溃，无通过结论。原定 MinIO upstream 镜像返回授权错误、官方历史二进制410，固定 RELEASE 官方源码构建情况及最终容器/模型验证见 [易富路接入方案执行记录](YIFULU_INTEGRATION_PLAN.md#8-本机执行记录)。本节后的历史“通过”不视为本机复验通过。

源码复核确认：真实 API 只有固定 local identity，OIDC 未装配；导入任务读取/重试尚未接受 scope/对象授权；SQL Dataset 默认未注入，数据源管理仍缺失；受控 SQL 使用 AtlasMind PostgreSQL session，不能直接查询易富路 MySQL；纯检索/外部引用复核、草稿发布、CAS 编辑冲突及数据源管理 API 是接入所需增量。RAG GET/PUT 策略 API 已在真实 app 中存在，README 的部分占位概述不能替代实际入口。审批/评测独立路由未装配到真实 app，capabilities 返回 false。

完整源码证据、推荐架构、两个入口共用同一管理服务、身份/审计/知识迁移/业务 API 与 SQL 方案、阶段验收和回退见 [YIFULU_INTEGRATION_PLAN.md](YIFULU_INTEGRATION_PLAN.md)。本次尚未实施任何跨系统集成。

同日按用户要求将建议范围精简为本机通用知识与总部回复建议 MVP，后续优先级见 NEXT_STEPS；仅方案发生变化，应用能力、已执行测试和运行结论未因此增加。

### 既有 MVP 基线（历史验证）

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
8. Advanced RAG 的 OpenAPI 生成类型尚未刷新；2026-10-11 当前工作区前端 TypeScript 检查通过，组件测试、全量 Vitest、ESLint 和生产构建本次未执行。历史真实问答已验证外层仅一次 `knowledge_search`，但内部 Graph Strategy 选择准确率和带 graphPaths 的新 Workflow 仍需版本化数据集复验。
9. SSE 事件持久化、回放、前端消费、详细 Retrieval Activity 和终态竞态收尾已进入代码并完成针对性验证，但全量前端、容器、断线恢复和真实浏览器验收按用户要求留待后续自行执行。
10. 当前 `BM25` Strategy 的名称与实际 PostgreSQL FTS 实现不完全一致，且全文搜索向量缺少专用索引；真实 BM25 引擎、中文分词质量及规模性能尚未实现和验收。
11. 当前 Rerank 是 DeepSeek listwise LLM 排序，不是 Cross-Encoder；`bge-reranker` 的模型选择、服务方式、批处理、超时降级、资源规格和质量收益尚未实现和验收。
12. 当前 Evidence Pool 能跨 Tool 累积证据，但没有类型化 Context Builder；Graph Path 与来源 metadata 在 Compose 前被丢弃，Prompt 又把全部来源描述为“original document sources”，与 Structured Evidence 的真实类型不一致。
13. 多源 Tool 调用依赖外层 Agent 逐步重新规划，只支持串行调用；没有确定性、预算受控的跨源 DAG，也没有 SQL/Graph 输出到后续检索输入的 typed binding，不能宣称 `SQL → Hybrid` 或 `Graph → Hybrid` 已实现。
14. 结构化引用目前只能追溯到注册 Dataset、版本和 metric，缺少行级业务键、查询快照/参数摘要及结果生成时间等细粒度 provenance；默认 Runtime 未配置 Dataset，业务 SQL 链路仍不可用。
