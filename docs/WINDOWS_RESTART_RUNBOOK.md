# AtlasMind Windows 重启恢复手册

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
