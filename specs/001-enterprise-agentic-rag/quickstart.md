# Quickstart Validation Guide: 企业级 Agentic RAG 知识平台

> Real-data MVP update: the supported local runtime uses `ATLASMIND_AUTH_MODE=local` only for
> development identity. Uploads, chunks, vectors, graph relations, answers, and citations are
> persistent. Configure the dedicated `ATLASMIND_CHAT_BASE_URL`/`ATLASMIND_CHAT_API_KEY` and
> `ATLASMIND_EMBEDDING_BASE_URL`/`ATLASMIND_EMBEDDING_API_KEY` pairs plus both model names before using
> model-dependent operations. The legacy shared `ATLASMIND_MODEL_BASE_URL`/`ATLASMIND_MODEL_API_KEY`
> pair remains supported. Missing model capabilities do not block platform startup; affected operations
> return `503 MODEL_CAPABILITY_NOT_CONFIGURED` and the ingestion worker remains idle. There is no demo-data
> fallback. The repository `README.md` contains the current
> executable commands.

## Purpose

本指南定义实现完成后的端到端验收路径，不代表当前最小脚手架已经具备这些命令或功能。实现任务
必须使下列场景可重复运行，并以实际测试输出判断通过与否。

相关设计：

- [Implementation Plan](plan.md)
- [Data Model](data-model.md)
- [OpenAPI Contract](contracts/openapi.yaml)
- [Capability Contract](contracts/capability-contract.md)
- [Event Contract](contracts/event-contract.md)

## Prerequisites

- Python 3.14 与项目依赖管理工具。
- PostgreSQL + pgvector、MinIO 和用于 Phase 3 的 Neo4j。
- 可供测试的企业 OIDC/OAuth2 issuer，或仅用于自动化测试的签名身份 fixture。
- 经批准的模型、Embedding 和 Reranker 测试端点；自动化安全测试使用确定性 fake adapter。
- 已批准或专门用于测试的记录保留与脱敏策略。
- Docker/Compose 或等价的本地服务编排能力。

首次实现必须先验证 Python 3.14 关键依赖兼容性：

```bash
uv sync --all-groups
uv run python -c "import fastapi, langgraph, sqlalchemy"
uv run pytest tests/contract/test_runtime_compatibility.py -q
```

任一关键依赖安装、导入或最小启动失败都阻止后续实现，不得通过忽略依赖错误继续。

## Local Environment

计划中的本地依赖启动命令：

```bash
docker compose up -d postgres minio neo4j
uv run alembic upgrade head
```

测试环境配置示例只列出字段名，不提交真实秘密：

```text
ATLASMIND_ENV=test
ATLASMIND_DATABASE_URL=postgresql+...
ATLASMIND_OBJECT_STORE_ENDPOINT=http://localhost:9000
ATLASMIND_NEO4J_URI=bolt://localhost:7687
ATLASMIND_OIDC_ISSUER=https://test-issuer.example
ATLASMIND_MODEL_BASE_URL=https://approved-model-endpoint.example
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

启动 API 和 worker：

```bash
uv run uvicorn atlasmind.api.app:app --host 127.0.0.1 --port 8000
uv run python -m atlasmind.workers.ingestion
uv run python -m atlasmind.workers.agent
uv run python -m atlasmind.workers.evaluation
```

## Seed Fixtures

端到端 fixture 必须至少包含：

- `employee-a`：可访问 `scope-public` 与 `scope-refund`。
- `employee-b`：只可访问 `scope-public`。
- `knowledge-admin`：可管理测试知识，但不能自动批准高风险业务动作。
- `tool-approver`：可批准指定 side-effect capability。
- 一份公开退款流程、一份受限退款失败分析、一份系统变更记录。
- 一份含直接/间接提示注入文本的恶意文档。
- 一组结构化退款指标和一个只读查询 capability。
- 一个会产生外部状态变化的 fake capability，可记录但不会影响真实系统。
- 一组有已知实体关系路径的 GraphRAG 文档。
- 一组明确无答案、来源冲突、工具失败和超时样本。

禁止在 fixture 中使用真实员工凭据、生产秘密或未脱敏企业数据。

## Scenario 1 — Authorized Answer and Citation

1. 以 `knowledge-admin` 上传公开退款流程，记录返回的 document、version 和 ingestion job。
2. 轮询 ingestion job，直至 `SEARCHABLE`；确认 source locator、版本和 scope 已保存。
3. 以 `employee-a` 提交“公司的退款流程是什么？”并读取 run 结果。
4. 打开每个 citation，检查它能定位到实际支持 claim 的授权来源位置。

Expected outcomes:

- 问答在 10 秒目标内完成，或明确返回当前环境的性能诊断。
- 答案只陈述来源支持的内容；citation 与 claim 一一关联。
- Agent run、retrieval span 和 Audit Event 具有同一 correlation ID。

推荐自动化入口：

```bash
uv run pytest tests/integration/test_authorized_answer.py -q
uv run pytest tests/contract/test_citation_contract.py -q
```

## Scenario 2 — Zero Permission Leakage

1. 将失败分析文档限定为 `scope-refund`。
2. 以 `employee-a` 查询其中唯一 marker，确认能够引用授权来源。
3. 以 `employee-b` 提交相同问题，并检查候选、prompt fixture、答案、citation、error、trace 和
   evaluation artifact。
4. 在运行中撤销 `employee-a` 的 scope，再读取尚未完成的结果和旧 citation。

Expected outcomes:

- `employee-b` 的所有输出面均不出现受限 marker，泄露次数为 0。
- 撤权后旧缓存和旧 Evidence Envelope 不再使用；输出重新综合或 fail closed。
- 不可见资源与不存在资源使用不泄露存在性的公共错误。

```bash
uv run pytest tests/security/test_permission_matrix.py -q
uv run pytest tests/security/test_revocation_race.py -q
uv run pytest tests/security/test_trace_and_eval_isolation.py -q
```

任何 forbidden marker 泄露都阻止发布。

## Scenario 3 — Ingestion Failure, Retry, Version, and Revocation

1. 分别上传正常、空、加密、超限和重复文件。
2. 验证失败文件不会出现 active version 或可检索 projection，并能显示受控失败阶段和 reason code。
3. 修正一个失败文件并重试；重复提交同一 idempotency key 不得创建重复任务。
4. 上传替代版本；新 generation 完成前旧版本继续有效，切换后 citation 指向新版本。
5. 撤销文档；规范状态立即隐藏，投影异步清理期间仍不可检索。

Expected outcomes:

- 支持文件在 10 分钟目标内变为 SEARCHABLE。
- 失败、重试和 generation 切换均可追踪且幂等。
- reconciliation 能发现并修复故意制造的孤立或缺失投影。

```bash
uv run pytest tests/integration/test_ingestion_lifecycle.py -q
uv run pytest tests/integration/test_projection_reconciliation.py -q
```

## Scenario 4 — Multi-Source Analysis and Degradation

1. 以 `employee-a` 提交“为什么今年退款失败率提高？”。
2. 允许系统使用注册的退款指标、技术文档和变更记录。
3. 验证 Agent 只选择必要 capability，并区分事实、推断和缺口。
4. 使一个来源超时，再次运行。

Expected outcomes:

- 正常运行在 60 秒内产出可核验综合结论。
- 单个来源失败时只返回其余已验证事实，并明确缺失来源及影响。
- 失败输出不进入 Evidence Record 或被陈述为事实。
- 最大步骤、工具次数、token 和时间预算均受执行层限制。

```bash
uv run pytest tests/integration/test_multi_source_analysis.py -q
uv run pytest tests/integration/test_agent_budget_and_degradation.py -q
```

## Scenario 5 — Tool Approval Cannot Be Bypassed

1. 让 Agent 规划一个只读工具和一个 side-effect fake capability。
2. 对 side-effect 调用分别测试无审批、过期、重放、换参和跨用户 Approval Grant。
3. 使用 `tool-approver` 对一组明确参数批准一次，再执行两次。
4. 在工具输出中加入提示注入文本，要求调用未注册能力和泄露其他 scope。

Expected outcomes:

- 只读调用在当前授权与预算内执行。
- 所有无效 Grant 均被拒绝并产生 Audit Event。
- 有效 Grant 只能按绑定参数消费一次；未批准外部状态变化为 0。
- 工具输出中的指令不能改变 allowlist、AuthContext 或审批状态。

```bash
uv run pytest tests/security/test_tool_approval.py -q
uv run pytest tests/security/test_prompt_injection_boundaries.py -q
```

## Scenario 6 — GraphRAG Provenance and Path Authorization

1. 导入含已知多跳关系的文档并完成 graph generation。
2. 以有权用户查询关系路径，检查每个节点、边和 Relation Evidence。
3. 撤销路径中一个来源 scope，再以无权用户查询相同路径。
4. 测试实体重名、别名冲突、无路径和相互冲突关系。

Expected outcomes:

- 授权路径返回关系链和原始来源。
- 任一路径组成部分未授权时不得先遍历后隐藏；答案、计数和错误都不泄露路径存在性。
- 无来源或冲突关系不作为确定结论。

```bash
uv run pytest tests/integration/test_graph_provenance.py -q
uv run pytest tests/security/test_graph_path_authorization.py -q
```

## Scenario 7 — Observability, Audit, and Sensitive Data

1. 执行成功、拒绝、失败、超时、审批和知识变更流程。
2. 使用授权运营人员按 correlation ID 查看运行摘要。
3. 使用普通员工读取其他用户的 run、trace、audit 和 evaluation 记录。
4. 在 query、文档和工具参数中放入测试 secret marker。

Expected outcomes:

- 至少 99% 交互可关联问题、关键决定、来源/工具活动、耗时和最终状态。
- 普通员工无法访问他人受控记录。
- 普通 log、trace、event 和 evaluation artifact 中原始 secret marker 泄露为 0。
- telemetry 采样不会丢失强制 Audit Event。

```bash
uv run pytest tests/integration/test_correlation_chain.py -q
uv run pytest tests/security/test_sensitive_telemetry.py -q
uv run pytest tests/security/test_audit_access.py -q
```

## Scenario 8 — RAG Evaluation Gates

运行批准的数据集：

```bash
uv run python -m atlasmind.evaluation run --dataset golden@1
uv run python -m atlasmind.evaluation run --dataset authorization-matrix@1
uv run python -m atlasmind.evaluation run --dataset injection-regression@1
uv run python -m atlasmind.evaluation run --dataset graph-multihop@1
```

Expected minimum gates:

- 基础问题正确或正确拒答且 10 秒内完成：至少 90%。
- 未授权内容泄露：0。
- 多源任务正确完成或准确降级：至少 85%。
- 图路径一致：至少 85%；虚构关系低于 2%。
- claim citation 可定位且实际支持：至少 95%。
- 失败和冲突限制说明合格：至少 95%。

每次运行必须记录代码、dataset、knowledge snapshot、index generation、retrieval policy、model、
prompt 和 evaluator 版本。任何安全失败直接阻止发布，不得由平均质量分抵消。

## Full Planned Validation

前端演示流程验证：

```bash
docker compose up -d --build frontend
docker run --rm --network host \
  -v "$PWD/frontend:/work" -w /work \
  mcr.microsoft.com/playwright:v1.62.1-noble \
  sh -lc 'corepack pnpm test:e2e'
```

```bash
uv run ruff check .
uv run mypy src
uv run pytest tests/unit tests/contract -q
uv run pytest tests/integration tests/security -q
uv run pytest tests/evaluation -q
```

只有实际执行的命令及其结果可以报告为通过。本计划阶段不声称上述实现测试已经存在或通过。
