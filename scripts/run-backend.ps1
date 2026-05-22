param(
    [string]$AppDir = "backend",
    [int]$Port = 8000
)

Set-Location $AppDir
if (-not $env:PLEXUS_INIT_DB) {
    $env:PLEXUS_INIT_DB = "true"
}

python -m uvicorn app.main:app --reload --port $Port
