param(
    [string]$Model = 'bge-m3',
    [switch]$ConfigureResident
)
$ErrorActionPreference = 'Stop'
$endpoint = 'http://127.0.0.1:11434'

if ($ConfigureResident) {
    $command = Get-Command ollama -CommandType Application -ErrorAction SilentlyContinue
    $executable = if ($command) { $command.Source } else { Join-Path $env:LOCALAPPDATA 'Programs/Ollama/ollama.exe' }
    if (!(Test-Path -LiteralPath $executable)) { throw 'Install the local Ollama application first.' }
    $installation = Split-Path -Parent ([IO.Path]::GetFullPath($executable))
    $app = Join-Path $installation 'ollama app.exe'
    # Applies to models loaded by this user's Ollama server. Restart before prewarming.
    [Environment]::SetEnvironmentVariable('OLLAMA_KEEP_ALIVE', '-1', 'User')
    $env:OLLAMA_KEEP_ALIVE = '-1'
    $processes = Get-CimInstance Win32_Process | Where-Object {
        $_.ExecutablePath -and
        ([IO.Path]::GetFullPath($_.ExecutablePath) -eq [IO.Path]::GetFullPath($executable) -or
         [IO.Path]::GetFullPath($_.ExecutablePath) -eq [IO.Path]::GetFullPath($app))
    }
    # Stop the tray supervisor first so it cannot respawn a server with the old environment.
    foreach ($process in ($processes | Sort-Object { $_.Name -ne 'ollama app.exe' })) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $app) {
        Start-Process -FilePath $app -WindowStyle Hidden
    } else {
        Start-Process -FilePath $executable -ArgumentList 'serve' -WindowStyle Hidden
    }
    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    do {
        try {
            $null = Invoke-RestMethod "$endpoint/api/version" -TimeoutSec 2
            $ready = $true
        } catch { $ready = $false; Start-Sleep -Milliseconds 500 }
    } until ($ready -or [DateTime]::UtcNow -gt $deadline)
    if (!$ready) { throw 'The local Ollama server did not become ready.' }
}

$body = @{ model = $Model; input = 'embedding readiness'; keep_alive = -1 } | ConvertTo-Json -Compress
$watch = [Diagnostics.Stopwatch]::StartNew()
$response = Invoke-RestMethod "$endpoint/api/embed" -Method Post -ContentType application/json -Body $body -TimeoutSec 60
$watch.Stop()
if (!$response.embeddings -or $response.embeddings.Count -ne 1 -or !$response.embeddings[0].Count) {
    throw 'Embedding warmup returned no usable vector.'
}
Write-Host ("Embedding ready: {0}, {1} dimensions, {2} ms. Resident configuration: {3}." -f
    $Model, $response.embeddings[0].Count, $watch.ElapsedMilliseconds,
    [Environment]::GetEnvironmentVariable('OLLAMA_KEEP_ALIVE', 'User'))
