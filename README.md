# AtlasMind

AtlasMind 是一个面向企业内部知识场景的 Agentic RAG 平台。它把文档导入、混合检索、GraphRAG、受控工具执行、人工审批、质量评估和审计治理放在同一套可追溯边界中。

平台的核心原则是：回答必须有授权证据，Agent 只能规划受控能力，高风险操作必须经过人工确认。

## 当前能力

- 企业知识问答：四种任务模式、异步 AgentRun、SSE 进度和只读证据面板。
- 数据接入：TXT、Markdown、HTML、PDF、DOCX 上传，版本、元数据与导入任务治理。
- 混合检索：PostgreSQL 关键词检索、pgvector 向量检索、融合、重排和证据验证。
- 知识图谱：Neo4j GraphRAG 投影、授权关系检索、冲突发现和受控实体合并。
- 受控执行：Capability Registry、预算、审批暂停与恢复、审计记录。
- 质量门禁：版本化评估数据集、引用准确性、安全隔离和发布门禁。
- 企业前端：Next.js App Router、服务端会话，以及问答、接入、图谱、RAG、运行、审批、评估和权限页面。

部分列表和策略管理接口仍处于产品占位状态。界面会明确显示“接口待接入”，不会回退到运行时演示数据。

## 系统结构

~~~mermaid
flowchart LR
    U[企业用户] --> F[Next.js 前端]
    F -->|服务端会话 / BFF| A[FastAPI API]
    A --> P[(PostgreSQL + pgvector)]
    A --> M[(MinIO)]
    A --> N[(Neo4j)]
    A --> O[OpenAI 兼容模型]
    A --> Q[持久任务与 Outbox]
    Q --> W[Ingestion / Agent Worker]
    W --> P
    W --> M
    W --> N
~~~

浏览器不会直连 PostgreSQL、MinIO 或 Neo4j，也不会提交 principal、role 或 scope。授权事实始终由服务端会话和当前策略决定。

## 技术栈

| 层级 | 技术 |
|---|---|
| API 与领域 | Python 3.14、FastAPI、Pydantic、SQLAlchemy、Alembic |
| Agent 与检索 | LangGraph、pgvector、Neo4j GraphRAG |
| 存储 | PostgreSQL、MinIO/S3、Neo4j |
| 前端 | Next.js 16、React 19、TypeScript strict、Tailwind CSS、Radix UI |
| 前端状态 | TanStack Query、React Hook Form、Zod、Zustand |
| 观测与质量 | OpenTelemetry、DeepEval、pytest、Vitest、Playwright |

## 环境要求

- Docker Desktop 或兼容的 Docker Compose
- Python 3.14
- Node.js 22+
- pnpm 10
- 一个生成模型和一个 Embedding 模型的 OpenAI 兼容接口

## 快速开始

复制本地配置：

~~~bash
cp .env.example .env
~~~

推荐使用 DeepSeek 生成和本地 Ollama Embedding：

~~~dotenv
ATLASMIND_CHAT_BASE_URL=https://api.deepseek.com
ATLASMIND_CHAT_API_KEY=你的_DeepSeek_API_Key
ATLASMIND_CHAT_MODEL=deepseek-chat

ATLASMIND_EMBEDDING_BASE_URL=http://host.docker.internal:8001/v1
ATLASMIND_EMBEDDING_API_KEY=ollama-local
ATLASMIND_EMBEDDING_MODEL=bge-m3
~~~

使用 Ollama 时，先执行：

~~~bash
ollama pull bge-m3
~~~

启动完整环境：

~~~bash
docker compose up -d --build
~~~

| 服务 | 地址 |
|---|---|
| AtlasMind 工作台 | http://localhost:3000 |
| API 健康检查 | http://localhost:8000/health/live |
| MinIO 控制台 | http://localhost:9001 |
| Neo4j Browser | http://localhost:7474 |

本地环境默认使用 <code>local</code> 身份模式。它只省略企业 OIDC 登录，文档、索引、图谱、答案和引用仍使用真实持久数据。生产环境会拒绝启用 local 身份。

## 前端页面

| 路由 | 模块 |
|---|---|
| <code>/chat</code> | 智能问答和右侧只读证据 |
| <code>/knowledge</code> | 文档上传、SQL 占位、元数据和导入任务 |
| <code>/graph</code> | 图谱探索、冲突治理和实体合并 |
| <code>/rag</code> | RAG 策略结构与接口占位 |
| <code>/runs</code> | Agent 运行中心 |
| <code>/approvals</code> | 高风险能力审批 |
| <code>/evaluations</code> | 质量评估和发布门禁 |
| <code>/governance</code> | 权限与审计结构 |
| <code>/system-states</code> | 失败和降级状态参考 |

静态产品原型位于 [design/prototype-v2](design/prototype-v2)。

## 本地开发

后端：

~~~bash
uv sync --all-extras --all-groups
uv run alembic upgrade head
uv run uvicorn atlasmind.api.app:create_app --factory --host 127.0.0.1 --port 8000
~~~

前端：

~~~bash
cd frontend
pnpm install
pnpm dev
~~~

## 测试与质量检查

首次运行先安装后端和前端依赖，然后使用统一质量门禁：

~~~bash
uv sync --all-extras --all-groups --locked
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend exec playwright install chromium
scripts/quality_gate.sh all
~~~

也可以只运行指定门禁：

~~~bash
scripts/quality_gate.sh backend
scripts/quality_gate.sh frontend
scripts/quality_gate.sh e2e
~~~

GitHub Actions 使用相同入口分别执行完整后端、前端和关键 Playwright 流程。页面截图是独立的可选任务，不属于必需质量门禁。

真实存储端到端测试需要先启动 PostgreSQL、MinIO 和 Neo4j，并设置 <code>ATLASMIND_RUN_REAL_MVP=1</code>。

已启动完整 Compose 环境并配置模型端点后，可执行一键真实知识库烟雾测试：

~~~bash
docker compose exec -T api python -m atlasmind.smoke
~~~

命令输出机器可读 JSON，并验证原文件、分块与向量、图谱投影、真实问答与引用、AgentRun/trace/审计关联、运行时重建检索和撤销过滤。只有输出中的 <code>status</code> 为 <code>passed</code> 才表示本次真实链路通过。

## Playwright 与自动截图

首次使用时安装 Chromium：

~~~bash
cd frontend
pnpm exec playwright install chromium
~~~

生成全部主要桌面页面截图：

~~~bash
pnpm screenshot:ui
~~~

截图会写入 <code>design/screenshots/latest/</code>。该目录被 Git 忽略，适合反复生成和对比，不会污染提交。

自动截图流程会：

1. 启动本地 Next.js 开发服务；
2. 使用专用 local 测试会话登录；
3. 以 1600×1000 视口打开九个主要模块；
4. 等待页面标题可见后保存全页 PNG。

## MVP 边界

当前版本尚未包含本地文件夹持续同步、SharePoint/Confluence 连接器、员工目录同步、完整 RAG 策略管理接口、完整列表 API、Microsoft GraphRAG 社区摘要/Global Search，以及生产级 OIDC 装配。

企业数据保留与脱敏政策、外部观测数据政策和生产身份集成完成前，不应把 local MVP 作为生产环境发布。

详细规格、数据模型、API 契约和任务位于 [specs/001-enterprise-agentic-rag](specs/001-enterprise-agentic-rag)。实际运行和测试结果优先于任务勾选或设计文档中的完成描述。

## 项目进度

- [项目实现状态](docs/PROJECT_STATUS.md)：当前已经实现、验证和仍受限制的能力。
- [下一步建议](docs/NEXT_STEPS.md)：按优先级排列的后续工作与验收出口。
- [Windows 重启恢复手册](docs/WINDOWS_RESTART_RUNBOOK.md)：重启后需要恢复的服务、启动顺序、命令和验证出口。

代码变更影响能力、接口、部署、测试结论或优先级时，应按照 `AGENTS.md` 同步维护这两份文档。
