param(
    [string]$YifuluRoot = 'D:\word\dianshang\yifulu-yifulu2.0.1',
    [switch]$EnableTrial,
    [switch]$EnableHqKnowledge,
    [switch]$ReloadKnowledgeService
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$encoding = [Text.UTF8Encoding]::new($false)
$atlasEnv = Join-Path $root '.env'
$phpEnv = Join-Path $YifuluRoot '后端/.env'
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
