# AtlasMind Windows 重启恢复手册

最后更新：2026-10-12。

## 2026-10-12：客服来源恢复与定向重载

客服外部知识现同时服务商户自动回复和总部人工建议，固定scope030；总部普通知识仍独立scope020。日常客服listener源码更新或其存储依赖停止时，使用现有入口，保留开关与密钥：

```powershell
pwsh -File scripts/Start-YifuluMvp.ps1 -ReloadKnowledgeService
```

该参数与两个Enable参数互斥：启动并等待PostgreSQL/MinIO/Neo4j/OTel依赖，若配置为本机Ollama则调用已有预热脚本，随后仅重新创建客服listener、不建镜像。两个Enable入口也补齐依赖等待及预热；`-EnableTrial` 现控制auto/draft共同客服来源，省略则关闭外部来源，原全局自动回复开关不变。listener的live健康检查只能证明进程存活，真实search及引用复核才证明检索可用。

本次模型TLS失败已实际定位到Docker Desktop手动代理指向已停止的7890。设置已备份于本机 `.local-backups/docker-model-proxy-20261012/`，热切换系统代理后真实模型恢复，不需重启Docker或电脑；原模型密钥和证书校验保留。后续出现同类故障先核查当前代理地址及服务，不默认重置代理、换密钥或关闭TLS校验。若需恢复原设置先确认原代理服务可达，不盲目恢复失效配置。

易富路常驻商户Agent改动在确认无在途任务后用 `scripts/Update-MerchantMvp.ps1 -RestartAgent` 定向重载；PHP/Vue继续源码挂载/HMR。本轮真实网关有依据/无依据两项通过，页面由用户刷新一次手动验收，间歇bridge错误仍按安全类别和代码位置排查。

## 2026-10-11：易富路同机独立开发环境

当前新克隆目录为 `D:\word\dianshang\AtlasMind`。3000 已由易富路使用，本机配置改用 **3001**；所有 AtlasMind 发布端口仅绑定 127.0.0.1，独立 Compose 项目为 `atlasmind-local`。本节后的 WSL/G 盘说明是原开发机的历史恢复记录，不适用于当前机器。

在 AtlasMind 目录使用既有 Compose 统一恢复：

```powershell
Set-Location D:\word\dianshang\AtlasMind
pwsh -NoProfile -File scripts/Warm-LocalEmbedding.ps1
docker compose -p atlasmind-local -f compose.yaml -f compose.override.yaml -f .data/compose.local.yaml -f compose.yifulu.yaml up -d --no-build
docker compose -p atlasmind-local -f compose.yaml -f compose.override.yaml -f .data/compose.local.yaml -f compose.yifulu.yaml ps
```

本机 `.env` 和 `.data/compose.local.yaml` 是 Git 忽略的本机配置，需保留。前端源码挂载本目录 `frontend`，`frontend-node-modules` 为独立依赖卷；无须普通源码更新就构建镜像。API 使用本次本地应用镜像，不把“重启”误写成“重新构建”。本机曾为缺失镜像进行首次应用/开发前端构建，后端本地派生镜像补装 `greenlet==3.5.5`；MinIO 固定 upstream源码构建方式和最终验证边界见 [接入方案执行记录](YIFULU_INTEGRATION_PLAN.md#8-本机执行记录)。不要使用不明 MinIO 镜像，也不要把本地派生镜像假称官方分发镜像。

本机入口：

2026-10-11 实际复核发现：容器内挂载源码已改，但 Next 开发进程仍提供旧事件地址的 JavaScript。遇到这种情况，仅重新加载前端，无须重启 Windows、数据库、Ollama 或重建镜像：

```powershell
docker compose -p atlasmind-local -f compose.yaml -f compose.override.yaml -f .data/compose.local.yaml -f compose.yifulu.yaml restart frontend
```

已打开的页面刷新一次取得新脚本。验证应同时查看实际页面下载的 EventSource 地址 `/api/platform/agent-runs/{id}/events` 和事件响应 200；仅检查挂载文件、容器 Up 或源码测试不足以确认部署已生效。本次已完成实际脚本及新问题的 HTTP/SSE 验证，具体文件监听原因和浏览器断网恢复仍未验证。

| 服务 | 地址 |
|---|---|
| 开发工作台 | <http://localhost:3001/login> |
| API | <http://localhost:8000/health/live> |
| MinIO Console | <http://localhost:9001> |
| Neo4j Browser | <http://localhost:7474> |

生成模型和 Embedding 由用户在本机 `.env` 配置，不在聊天发送明文密钥，不取用易富路加密模型配置。填写完整配置后，用同一入口更新受影响的 API/worker 环境，不重新构建镜像：

```powershell
docker compose -p atlasmind-local -f compose.yaml -f compose.override.yaml -f .data/compose.local.yaml -f compose.yifulu.yaml up -d --no-build api ingestion-worker
docker compose -p atlasmind-local -f compose.yaml -f compose.override.yaml -f .data/compose.local.yaml -f compose.yifulu.yaml exec -T api python -m atlasmind.smoke
```

确认没有正在执行的导入或问答任务再更新 API/worker 环境。只有 smoke 返回 `status=passed` 才视为本次真实知识/问答/引用/撤销链路通过。缺模型时基础服务可用、worker空闲，但导入和问答明确失败；HTTP健康或历史通过记录不能代替真实模型验收。UI 由用户手动验收。

停止时也使用相同 Compose 参数的 `stop`，只停止 AtlasMind；保留数据与依赖卷，不执行 `down -v`，不停止/修改易富路容器。

## 当前客服 MVP 增量更新与回退（2026-10-11）

总部普通知识单独启用：在 AtlasMind 目录执行 `pwsh -File scripts/Start-YifuluMvp.ps1 -EnableHqKnowledge`。该入口创建/复用独立私有服务密钥，同步易富路 `[ATLASMIND_HQ]`，启动无主机端口的 `hq-knowledge-service` 并通过易富路统一入口仅重载总部查询Worker；先确认没有总部在途任务。无需电脑重启或镜像构建，不改变客服试点和模型凭据。该服务使用可选 `hq-knowledge` profile，整机恢复时运行此入口补启；普通 `up` 不自动启用此profile。

后续仅更新总部Worker挂载代码时，在易富路目录执行 `scripts/Update-AiAdministration.ps1 -StartChatRuntime -ReloadChatWorker`。若停用普通问答，将易富路私有配置 `[ATLASMIND_HQ] ENABLED=false` 并使用同一入口重载；已保存外部引用将不可继续展示，业务路径继续原处理。客服停止/回退仍独立使用下述入口。

完整恢复使用上方四份 Compose 文件，保留 `.env` 中独立服务密钥。`knowledge-service` 不映射主机端口，易富路容器通过现有内部网络访问它。普通资料和商户通用资料分别管理；上传时只有选择“商户通用客服知识”才会用于客服建议。

配置或源码更新后可运行 `pwsh -File scripts/Start-YifuluMvp.ps1 -EnableTrial`；省略 EnableTrial 关闭外部知识试点，原自动回复设置不变。关闭后旧外部来源无法采用，需人工核实。该脚本仅增量更新 API/worker/service；首次依赖安装或整机恢复仍使用完整 Compose 启动。普通改动不重建镜像。

本机 DeepSeek 使用 `ATLASMIND_CHAT_THINKING_ENABLED=false`，避免小输出预算被默认思考模式耗尽；Embedding 仍使用现有 Ollama BGE-M3。`scripts/Test-YifuluMvp.ps1` 在隔离临时数据库执行自动回归。真实模型与代表问题证据见接入方案第 9 节，页面由用户验收。
## BGE-M3 常驻与预热（2026-10-11）

本机已配置 Windows 用户环境变量 `OLLAMA_KEEP_ALIVE=-1`，Ollama 后续加载的模型默认保持驻留。当前只加载 BGE-M3，约占 1.7GB 显存。首次配置或更改后，应确认没有正在导入/问答的任务，再执行以下入口；该开关会重启安装的 Ollama 应用与其服务，不重启业务容器：

```powershell
pwsh -NoProfile -File scripts/Warm-LocalEmbedding.ps1 -ConfigureResident
```

电脑/Ollama 重启后，使用上方恢复步骤中的普通 `Warm-LocalEmbedding.ps1` 先加载模型，再开始问答。脚本只有 Embedding 返回非空向量才报告 ready，失败则明确报错；普通预热不重启 Ollama，也不写入知识库。冷启动实测约 4.2 秒，热态约 0.3 秒；现有单策略 2.5 秒和总检索 8 秒预算未放宽。

如需恢复 Ollama 默认卸载策略，将用户环境变量移除并退出/重新打开 Ollama；后续首次请求仍需预热：

```powershell
[Environment]::SetEnvironmentVariable('OLLAMA_KEEP_ALIVE', $null, 'User')
```

问答与运行详情的实时事件通过 `/api/platform/agent-runs/{id}/events` 认证代理读取。遇到模型/策略超时且没有可用证据时，当前运行会显示可重试的检索失败，不应据此重新上传原 PDF。

## 原开发机历史记录（2026-08-25）

本文记录当前本地开发环境在 Windows 重启后的服务恢复顺序、命令和验证出口。命令按当前实际路径编写：

- AtlasMind：`/home/zoe/projects/AtlasMind`（Ubuntu WSL）
- 本地 Embedding：`G:\local-embedding`
- Embedding API：`http://host.docker.internal:8001/v1`

最后核对日期：2026-08-25。

## 1. 哪些服务需要手动启动

| 服务 | 当前启动方式 | Windows 重启后的处理 |
|---|---|---|
| Docker Desktop | Windows 登录启动项已配置 | 通常自动启动；若未启动则手动打开，并等待 Docker Engine 就绪 |
| Ubuntu WSL | 按需启动 | 无需单独常驻；后续 `wsl.exe -d Ubuntu` 命令会自动启动 |
| 本地 BGE-M3 Embedding | Windows Python 进程，未配置计划任务或启动项 | **必须手动启动** |
| PostgreSQL | Docker Compose；当前容器重启策略为 `no` | **必须执行一次 `docker compose up -d`** |
| MinIO | Docker Compose；当前容器重启策略为 `no` | 同上 |
| Neo4j | Docker Compose；当前容器重启策略为 `no` | 同上 |
| OpenTelemetry Collector | Docker Compose；当前容器重启策略为 `no` | 同上 |
| AtlasMind API | Docker Compose；`unless-stopped` | 通常随 Docker 恢复，但仍统一执行 `docker compose up -d` |
| ingestion worker | Docker Compose；`unless-stopped` | 同上 |
| AtlasMind frontend | Docker Compose；`unless-stopped` | 同上 |
| DeepSeek | 外部云 API | 无需启动；需要网络可用且 `.env` 中的配置有效 |

`com.docker.service` 当前为 Manual/Stopped 是 Docker Desktop WSL2 后端的正常状态，不应单独把它当作 AtlasMind 服务启动。

## 2. 推荐恢复顺序

以下命令均在 Windows PowerShell 中执行。

### 第一步：确认 Docker Desktop 已就绪

如果 Docker Desktop 没有自动打开：

```powershell
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
```

等待 Docker Engine 可用：

```powershell
do {
    Start-Sleep -Seconds 3
    docker info *> $null
} until ($LASTEXITCODE -eq 0)

Write-Host "Docker Desktop 已就绪"
```

### 第二步：启动本地 Embedding 服务

推荐使用后台方式启动，并保留日志：

```powershell
$embeddingRoot = "G:\local-embedding"
$logRoot = Join-Path $embeddingRoot "logs"

New-Item -ItemType Directory -Force -Path $logRoot | Out-Null

$env:EMBEDDING_HOST = "0.0.0.0"
$env:EMBEDDING_PORT = "8001"

$embeddingProcess = Start-Process `
    -FilePath (Join-Path $embeddingRoot ".venv\Scripts\python.exe") `
    -ArgumentList "main.py" `
    -WorkingDirectory $embeddingRoot `
    -RedirectStandardOutput (Join-Path $logRoot "service.stdout.log") `
    -RedirectStandardError (Join-Path $logRoot "service.stderr.log") `
    -WindowStyle Hidden `
    -PassThru

Write-Host "Embedding 启动进程：$($embeddingProcess.Id)"
```

必须使用 `0.0.0.0`，否则 Docker 中的 API 和 worker 无法通过 `host.docker.internal:8001` 访问该服务。该接口当前没有身份认证，只适合本地可信开发网络；不要把 8001 端口映射到公网。

等待模型加载并检查健康状态：

```powershell
do {
    Start-Sleep -Seconds 2
    try {
        $embeddingHealth = Invoke-RestMethod `
            -Uri "http://127.0.0.1:8001/health" `
            -TimeoutSec 3
    } catch {
        $embeddingHealth = $null
    }
} until ($embeddingHealth.status -eq "ok")

$embeddingHealth
```

当前预期结果：模型为 `BAAI/bge-m3`，向量维度为 `1024`。设备可能显示 `cpu`，这不影响功能验证，但会影响推理速度。

### 第三步：启动完整 AtlasMind Compose 栈

```powershell
wsl.exe -d Ubuntu -- bash -lc `
    "cd /home/zoe/projects/AtlasMind && docker compose up -d"
```

这里不要省略 `docker compose up -d`。仅启动 Docker Desktop 不足以保证 PostgreSQL、MinIO、Neo4j 和 OTel Collector 自动恢复，因为它们当前的容器重启策略是 `no`。

查看容器状态：

```powershell
wsl.exe -d Ubuntu -- bash -lc `
    "cd /home/zoe/projects/AtlasMind && docker compose ps"
```

预期至少包含：

- `frontend`
- `api`
- `ingestion-worker`
- `postgres`
- `minio`
- `neo4j`
- `otel-collector`

## 3. 恢复后的验证

### 基础健康检查

```powershell
Invoke-RestMethod "http://127.0.0.1:8001/health"
Invoke-RestMethod "http://127.0.0.1:8000/health/live"
Invoke-WebRequest "http://127.0.0.1:3000/login" -UseBasicParsing
```

访问入口：

- AtlasMind：<http://localhost:3000>
- API 健康检查：<http://localhost:8000/health/live>
- MinIO Console：<http://localhost:9001>
- Neo4j Browser：<http://localhost:7474>

### 完整真实知识链路

基础健康检查通过后运行：

```powershell
wsl.exe -d Ubuntu -- bash -lc `
    "cd /home/zoe/projects/AtlasMind && docker compose exec -T api python -m atlasmind.smoke"
```

只有 JSON 输出中的 `status` 为 `passed`，才表示以下链路本次全部可用：

- 本地 Embedding 和 DeepSeek；
- PostgreSQL 分块、向量、运行、trace 与审计；
- MinIO 原文件；
- Neo4j 图谱投影；
- 真实问答、授权引用、运行时重建检索和撤销过滤。

## 4. 常用诊断与停止命令

### 查看 Embedding 日志

```powershell
Get-Content "G:\local-embedding\logs\service.stderr.log" -Tail 100
Get-Content "G:\local-embedding\logs\service.stdout.log" -Tail 100
```

### 检查 8001 监听进程

```powershell
$embeddingConnection = Get-NetTCPConnection `
    -LocalPort 8001 `
    -State Listen `
    -ErrorAction SilentlyContinue

$embeddingConnection
Get-Process -Id $embeddingConnection.OwningProcess -ErrorAction SilentlyContinue
```

### 停止 Embedding 服务

先使用上一条命令核对进程确实是本地 Embedding Python 服务，再执行：

```powershell
Stop-Process -Id $embeddingConnection.OwningProcess
```

### 重启 AtlasMind Compose 栈

```powershell
wsl.exe -d Ubuntu -- bash -lc `
    "cd /home/zoe/projects/AtlasMind && docker compose restart"
```

如果基础设施容器没有创建或已停止，使用：

```powershell
wsl.exe -d Ubuntu -- bash -lc `
    "cd /home/zoe/projects/AtlasMind && docker compose up -d"
```

### WSL 或 Docker 连接异常

先退出 Docker Desktop，然后执行：

```powershell
wsl.exe --shutdown
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
```

等待 Docker Engine 就绪后，再重新执行 Embedding 健康检查和 `docker compose up -d`。

## 5. 当前不需要启动的进程

- DeepSeek 是外部 API，不存在本地 DeepSeek 服务进程。
- Headroom 代理不是 AtlasMind 当前真实问答链路的必需依赖。
- 浏览器不需要预先启动；访问 `http://localhost:3000` 即可。
- 不需要单独手动启动 PostgreSQL、MinIO、Neo4j、OTel、API、worker 或 frontend；统一由 Compose 管理。
