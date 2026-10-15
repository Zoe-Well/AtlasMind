param(
    [string]$YifuluRoot = 'D:\word\dianshang\yifulu-yifulu2.0.1',
    [switch]$EnableTrial,
    [switch]$EnableHqKnowledge,
    [switch]$ReloadKnowledgeService,
    [switch]$ReloadParsingRuntime,
    [switch]$UpdateRetrievalRuntime,
    [switch]$BuildBackendImage,
    [string[]]$RetrievalScopes = @('00000000-0000-4000-8000-000000000020','00000000-0000-4000-8000-000000000030')
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$encoding = [Text.UTF8Encoding]::new($false)
$atlasEnv = Join-Path $root '.env'
$phpEnv = Join-Path $YifuluRoot '后端/.env'
if ($BuildBackendImage -and !$UpdateRetrievalRuntime) { throw 'BuildBackendImage requires UpdateRetrievalRuntime.' }
if ($ReloadParsingRuntime -or $UpdateRetrievalRuntime) {
    if ($EnableHqKnowledge -or $EnableTrial -or $ReloadKnowledgeService) {
        throw 'Reload parsing separately from enabling profiles or other reload modes.'
    }
    $compose = @('-p','atlasmind-local','-f','compose.yaml','-f','compose.override.yaml','-f','.data/compose.local.yaml','-f','compose.yifulu.yaml')
    Push-Location $root
    try {
        $running = @(& docker compose @compose ps --status running --services)
        if ($LASTEXITCODE -ne 0) { throw 'Could not inspect the existing runtime.' }
        if ('api' -notin $running -or 'ingestion-worker' -notin $running) {
            throw 'Start the existing API and ingestion worker before using this reload mode.'
        }
        $targets = @('api','ingestion-worker','knowledge-service','hq-knowledge-service' | Where-Object { $_ -in $running })
        $expectedSource = [IO.Path]::GetFullPath((Join-Path $root 'src')).TrimEnd('\','/')
        foreach ($service in $targets) {
            $containerId = & docker compose @compose ps -q $service
            if ($LASTEXITCODE -ne 0 -or !$containerId) { throw "Could not inspect $service" }
            $details = (& docker inspect $containerId | ConvertFrom-Json)[0]
            if ($LASTEXITCODE -ne 0) { throw "Could not inspect mounts for $service" }
            $mount = @($details.Mounts | Where-Object { $_.Destination -eq '/app/src' })
            if ($mount.Count -ne 1 -or [IO.Path]::GetFullPath($mount[0].Source).TrimEnd('\','/') -ne $expectedSource) {
                throw "$service does not mount the current workspace src directory."
            }
        }
        $pending = & docker compose @compose exec -T postgres psql -U atlasmind -d atlasmind -At -v ON_ERROR_STOP=1 -c "SELECT (SELECT count(*) FROM ingestion_jobs WHERE state::text IN ('QUEUED','RUNNING')) + (SELECT count(*) FROM agent_runs WHERE state::text IN ('QUEUED','RUNNING'));"
        if ($LASTEXITCODE -ne 0 -or ($pending -join '').Trim() -ne '0') {
            throw 'Pending ingestion or answer jobs exist, or their state could not be verified. Retry when idle.'
        }
        if ($UpdateRetrievalRuntime) {
            $scopeArgs = @()
            foreach ($scope in $RetrievalScopes) {
                $validatedScope = [guid]::Parse($scope).ToString()
                $scopeArgs += @('--scope', $validatedScope)
            }
            if (!$scopeArgs.Count) { throw 'At least one explicit retrieval scope is required.' }
            if ($BuildBackendImage) {
                # Explicit dependency change only. All four services reuse this backend image.
                & docker compose @compose build api
                if ($LASTEXITCODE -ne 0) { throw 'Backend dependency image build failed; existing services retained.' }
            }
            $pending = & docker compose @compose exec -T postgres psql -U atlasmind -d atlasmind -At -v ON_ERROR_STOP=1 -c "SELECT (SELECT count(*) FROM ingestion_jobs WHERE state::text IN ('QUEUED','RUNNING')) + (SELECT count(*) FROM agent_runs WHERE state::text IN ('QUEUED','RUNNING'));"
            if ($LASTEXITCODE -ne 0 -or ($pending -join '').Trim() -ne '0') {
                throw 'New jobs arrived during preparation; retry maintenance when idle.'
            }
            & docker compose @compose stop --timeout 45 @targets
            if ($LASTEXITCODE -ne 0) { throw 'Could not stop retrieval services for maintenance.' }
            $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
            $backupDir = Join-Path $root '.data/backups'
            [IO.Directory]::CreateDirectory($backupDir) | Out-Null
            $dumpPath = "/tmp/retrieval-$stamp.dump"
            & docker compose @compose exec -T postgres pg_dump -U atlasmind -d atlasmind -Fc -f $dumpPath
            if ($LASTEXITCODE -ne 0) { throw 'Backup failed; services remain stopped.' }
            & docker compose @compose cp "postgres:$dumpPath" (Join-Path $backupDir "retrieval-$stamp.dump")
            if ($LASTEXITCODE -ne 0) { throw 'Could not retain database backup.' }
            & docker compose @compose run --rm --no-deps api alembic upgrade head
            if ($LASTEXITCODE -ne 0) { throw 'Migration failed; services remain stopped for inspection.' }
            & docker compose @compose run --rm --no-deps api python -m atlasmind.ingestion.reindex @scopeArgs
            if ($LASTEXITCODE -ne 0) { throw 'Projection rebuild failed; retain backup and retry after resolving the error.' }
            & docker compose @compose up -d --no-build --no-deps --force-recreate --wait --wait-timeout 90 @targets
            if ($LASTEXITCODE -ne 0) { throw 'Updated retrieval services failed their health checks.' }
        } else {
            & docker compose @compose restart --timeout 45 @targets
            if ($LASTEXITCODE -ne 0) { throw 'Parsing runtime restart failed.' }
        }
    } finally { Pop-Location }
    if ($UpdateRetrievalRuntime) {
        Write-Host 'Retrieval runtime updated with database backup and scoped projection rebuild. Canonical text and citations retained.'
    } else {
        Write-Host 'Reloaded mounted parser and manual-reader code; no image build or document reindex performed.'
    }
    return
}
function Start-KnowledgeDependencies {
    Push-Location $root
    try{
        & docker compose -p atlasmind-local -f compose.yaml -f compose.override.yaml -f .data/compose.local.yaml -f compose.yifulu.yaml up -d --no-build --no-deps --wait --wait-timeout 60 postgres minio neo4j otel-collector
        if($LASTEXITCODE -ne 0){throw 'Knowledge storage dependencies failed to start.'}
        if(Test-Path -LiteralPath $atlasEnv){
            $configuredText=[IO.File]::ReadAllText($atlasEnv)
            $embeddingUrl=[regex]::Match($configuredText,'(?m)^ATLASMIND_EMBEDDING_BASE_URL=(.+)\r?$').Groups[1].Value.Trim()
            $embeddingModel=[regex]::Match($configuredText,'(?m)^ATLASMIND_EMBEDDING_MODEL=(.+)\r?$').Groups[1].Value.Trim()
            if($embeddingUrl -match '^http://(?:host\.docker\.internal|localhost|127\.0\.0\.1):11434(?:/v1)?/?$' -and $embeddingModel){
                & (Join-Path $PSScriptRoot 'Warm-LocalEmbedding.ps1') -Model $embeddingModel
            }
        }
    }finally{Pop-Location}
}
if($ReloadKnowledgeService){
    if($EnableHqKnowledge -or $EnableTrial){throw 'Reload the existing knowledge listener separately from enabling profiles.'}
    Start-KnowledgeDependencies
    Push-Location $root
    try{
        & docker compose -p atlasmind-local -f compose.yaml -f compose.override.yaml -f .data/compose.local.yaml -f compose.yifulu.yaml up -d --no-build --no-deps --force-recreate knowledge-service
        if($LASTEXITCODE -ne 0){throw 'Customer-service knowledge listener reload failed.'}
    }finally{Pop-Location}
    Write-Host 'Existing customer-service listener reloaded; management, ingestion and HQ services unchanged.'
    return
}
if($EnableHqKnowledge) {
    if(!(Test-Path -LiteralPath $atlasEnv) -or !(Test-Path -LiteralPath $phpEnv)){throw 'Existing local configuration is required.'}
    $hqAtlasText=[IO.File]::ReadAllText($atlasEnv)
    $hqMatch=[regex]::Match($hqAtlasText,'(?m)^ATLASMIND_HQ_SERVICE_JWT_SECRET=(.+)\r?$')
    if($hqMatch.Success){$hqSecret=$hqMatch.Groups[1].Value.Trim()}else{
        $hqBytes=New-Object byte[] 48;[Security.Cryptography.RandomNumberGenerator]::Fill($hqBytes)
        $hqSecret=[Convert]::ToBase64String($hqBytes)
        [IO.File]::AppendAllText($atlasEnv,"`nATLASMIND_HQ_SERVICE_JWT_SECRET=$hqSecret`n",$encoding)
    }
    if($hqSecret.Length -lt 32){throw 'HQ service key is too short.'}
    $hqPhpText=[IO.File]::ReadAllText($phpEnv)
    $hqBlock="[ATLASMIND_HQ]`nENABLED=true`nSERVICE_URL=http://hq-knowledge-service:8001`nJWT_SECRET=$hqSecret`n"
    if([regex]::IsMatch($hqPhpText,'(?mi)^\[ATLASMIND_HQ\]')){
        $hqPhpText=[regex]::Replace($hqPhpText,'(?mis)^\[ATLASMIND_HQ\]\s*.*?(?=^\[|\z)',[System.Text.RegularExpressions.MatchEvaluator]{param($m)$hqBlock+"`n"})
    }else{$hqPhpText+="`n$hqBlock"}
    [IO.File]::WriteAllText($phpEnv,$hqPhpText,$encoding)
    Start-KnowledgeDependencies
    Push-Location $root
    try{
        & docker compose -p atlasmind-local -f compose.yaml -f compose.override.yaml -f .data/compose.local.yaml -f compose.yifulu.yaml up -d --no-build --no-deps hq-knowledge-service
        if($LASTEXITCODE -ne 0){throw 'HQ knowledge service startup failed.'}
    }finally{Pop-Location}
    & (Join-Path $YifuluRoot 'scripts/Update-AiAdministration.ps1') -StartChatRuntime -ReloadChatWorker
    if($LASTEXITCODE -ne 0){throw 'HQ chat worker reload failed.'}
    Write-Host 'HQ ordinary knowledge enabled; customer-service scope and model credentials unchanged.'
    return
}
if (!(Test-Path -LiteralPath $atlasEnv) -or !(Test-Path -LiteralPath (Join-Path $YifuluRoot '后端/composer.json'))) { throw 'Configure AtlasMind .env and select the existing Yifulu workspace first.' }
$lines = [IO.File]::ReadAllText($atlasEnv)
$match = [regex]::Match($lines, '(?m)^ATLASMIND_SERVICE_JWT_SECRET=(.+)\r?$')
if ($match.Success) { $secret = $match.Groups[1].Value.Trim() }
else {
    $bytes = New-Object byte[] 48
    [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    $secret = [Convert]::ToBase64String($bytes)
    [IO.File]::AppendAllText($atlasEnv, "`nATLASMIND_SERVICE_JWT_SECRET=$secret`n", $encoding)
}
if ($secret.Length -lt 32) { throw 'Service JWT key is too short.' }
$phpText = if (Test-Path -LiteralPath $phpEnv) { [IO.File]::ReadAllText($phpEnv) } else { '' }
$block = "[ATLASMIND]`nENABLED=" + $EnableTrial.IsPresent.ToString().ToLowerInvariant() + "`nSERVICE_URL=http://knowledge-service:8001`nJWT_SECRET=$secret`nMANAGEMENT_URL=http://localhost:3001/login`n"
if ([regex]::IsMatch($phpText, '(?mi)^\[ATLASMIND\]')) {
    $phpText = [regex]::Replace($phpText, '(?mis)^\[ATLASMIND\]\s*.*?(?=^\[|\z)', [System.Text.RegularExpressions.MatchEvaluator]{param($m) $block + "`n"})
} else { $phpText += "`n$block" }
[IO.File]::WriteAllText($phpEnv, $phpText, $encoding)
Start-KnowledgeDependencies
Push-Location $root
try {
    & docker compose -p atlasmind-local -f compose.yaml -f compose.override.yaml -f .data/compose.local.yaml -f compose.yifulu.yaml up -d --no-build --no-deps api ingestion-worker knowledge-service
    if ($LASTEXITCODE -ne 0) { throw 'AtlasMind service update failed.' }
} finally { Pop-Location }
Write-Host ('Restricted listener updated; customer-service knowledge enabled: ' + $EnableTrial.IsPresent + '. Existing merchant encryption key and automatic-reply setting were not changed.')
