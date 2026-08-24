Enterprise Agentic RAG Platform Specification
1. 项目目标
实现一个面向企业内部使用的 Agentic RAG 知识管理平台。
系统支持员工通过自然语言访问企业知识，并能够根据问题类型动态选择不同知识来源，包括：
- 非结构化文档知识；
- 企业结构化业务数据；
- 知识图谱关系数据；
- 外部业务系统能力。
项目目标不是实现简单 ChatPDF，而是构建具备企业级能力的 AI Knowledge Agent。
重点体现：
- Enterprise RAG Pipeline；
- Agent Workflow；
- Advanced RAG；
- GraphRAG；
- Permission Control；
- Evaluation；
- Observability。
2. 核心架构原则
系统采用：
Agent 决策层 + Retrieval/Tool 执行层
架构。
Agent 负责：
- 理解用户任务；
- 判断是否需要检索；
- 选择数据源；
- 规划复杂任务；
- 调用工具。
Tool 和 Retrieval Service 负责：
- 数据查询；
- 文档检索；
- 权限校验；
- 向量搜索；
- 图检索；
- 业务系统调用。
LLM 不直接执行数据库操作、权限判断和底层检索逻辑。
3. Agent 能力要求
使用 Agent Framework 实现任务编排。
Agent 应支持：
简单知识查询
例如：
“公司的退款流程是什么？”
直接调用 Knowledge Retrieval。
多步骤分析任务
例如：
“为什么今年退款失败率提高？”
需要：
- 查询业务数据；
- 检索相关技术文档；
- 查询系统变更记录；
- 综合分析。
动态工具选择
Agent 可以根据任务选择：
- Knowledge Search Tool；
- Graph Search Tool；
- SQL Query Tool；
- External API Tool。
4. RAG 系统要求
实现企业级 Retrieval Pipeline。
基础能力：
- Document Ingestion；
- Chunking；
- Metadata Management；
- Embedding；
- Vector Retrieval；
- Hybrid Search；
- Rerank；
- Citation。
Retrieval Pipeline 应支持扩展 Advanced RAG 策略，包括：
- Query Rewrite；
- Self Query；
- HyDE；
- Context Compression。
这些能力设计为可插拔模块，而不是全部固定执行。
系统应该允许根据 Retrieval Policy 决定是否启用。
5. GraphRAG 能力
系统需要支持 Graph-based Retrieval。
要求：
- 从企业文档中抽取 Entity；
- 构建 Entity Relation Graph；
- 支持基于关系的检索；
- 支持 Multi-hop Question。
GraphRAG 需要设计为独立 Retrieval Backend。
推荐：
LightRAG 作为 GraphRAG Framework。
Neo4j 作为图数据存储。
同时保持接口抽象，未来可以替换其他 GraphRAG 实现。
6. Knowledge Ingestion
实现企业知识导入流程。
支持：
- 文件上传；
- 文档解析；
- Chunk 切分；
- Metadata Extraction；
- Embedding；
- Vector Index；
- Graph Index。
Metadata 支持来源：
- 用户输入；
- 文件信息；
- 企业业务字段；
- Rule Extraction；
- LLM Extraction。
7. 数据存储设计
根据数据类型选择不同存储：
关系型数据库：
保存：
- 用户；
- 权限；
- 文档信息；
- Metadata；
- Audit Log。
Vector Database：
保存：
- Chunk Embedding；
- Vector Metadata。
Graph Database：
保存：
- Entity；
- Relation。
Object Storage：
保存：
- 原始文件。
8. 企业安全能力
必须支持：
Authentication
用户身份认证。
Authorization
知识访问权限控制。
权限控制需要贯穿：
User → Role → Knowledge Scope → Retrieval Filter。
Agent 不应该绕过权限系统访问知识。
9. 可观测与评估
系统需要记录：
- 用户 Query；
- Agent Decision；
- Tool Call；
- Retrieval Result；
- Token Usage；
- Latency；
- Final Answer。
支持评估：
- Retrieval Quality；
- Context Relevance；
- Answer Faithfulness；
- Citation Accuracy。
10. 推荐技术方向
推荐技术栈：
Backend:
- Python FastAPI
Agent:
- LangGraph
Vector:
- Qdrant / pgvector
Graph:
- LightRAG + Neo4j
Database:
- PostgreSQL
Storage:
- MinIO
Evaluation:
- DeepEval
Observability:
- LangSmith / OpenTelemetry
11. 开发原则
采用渐进式开发：
Phase 1：
完成企业级基础 RAG。
Phase 2：
增加 Agent Workflow 和 Tool Calling。
Phase 3：
增加 GraphRAG。
Phase 4：
增加 Advanced RAG 策略和 Evaluation。