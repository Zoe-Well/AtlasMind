# Isolated PostgreSQL database: never let a test worker claim a user's ingestion job.
param()
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$database='atlasmind_test_'+[guid]::NewGuid().ToString('N').Substring(0,12)
if($database -notmatch '^atlasmind_test_[a-f0-9]{12}$'){throw 'Invalid temporary database name'}
$compose=@('-p','atlasmind-local','-f','compose.yaml','-f','compose.override.yaml','-f','.data/compose.local.yaml','-f','compose.yifulu.yaml')
Push-Location $root
$created=$false
try {
    if(!(Test-Path -LiteralPath (Join-Path $root '.data/testdeps/pytest'))){
        & docker compose @compose run --rm --no-deps -v "${root}:/workspace" api python -m pip install --target /workspace/.data/testdeps pytest==9.1.1 pytest-asyncio==1.4.0
        if($LASTEXITCODE -ne 0){throw 'Could not prepare container test dependencies'}
    }
    & docker compose @compose exec -T postgres psql -U atlasmind -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE $database"
    if($LASTEXITCODE -ne 0){throw 'Could not create the isolated test database'}
    $created=$true
    & docker compose @compose run --rm --no-deps -v "${root}:/workspace" -w /workspace `
        -e "ATLASMIND_DATABASE_URL=postgresql+asyncpg://atlasmind:atlasmind-local-only@postgres:5432/$database" `
        -e "ATLASMIND_MANUAL_TEST_DB=postgresql+asyncpg://atlasmind:atlasmind-local-only@postgres:5432/$database" `
        -e ATLASMIND_OBJECT_STORE_BUCKET=atlasmind-mvp-tests `
        -e ATLASMIND_RUN_REAL_MVP=1 -e PYTHONPATH=/workspace/.data/testdeps:/app/src `
        -e PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 -e PYTHONDONTWRITEBYTECODE=1 `
        api sh -c 'alembic upgrade head && python -m pytest -p pytest_asyncio.plugin -p no:cacheprovider tests/integration/test_service_manual.py tests/integration/test_service_knowledge_lifecycle.py tests/security/test_service_knowledge_api.py tests/contract/test_real_mvp_api.py tests/unit/test_openai_compatible.py -q --tb=short'
    if($LASTEXITCODE -ne 0){throw 'MVP regression failed'}
} finally {
    if($created){
        & docker compose @compose exec -T postgres psql -U atlasmind -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE $database WITH (FORCE)"
    }
    Pop-Location
}
