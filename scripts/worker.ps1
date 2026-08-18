$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Virtual environment not found: $Python"
}

if (-not (Test-Path "manage.py")) {
    throw "manage.py not found in project root: $Root"
}

Write-Host "Starting Celery worker with beat..."
Write-Host "Redis must be running and reachable through REDIS_URL."
Write-Host "Using --pool=solo for Windows compatibility."

& $Python -m celery -A config worker -B --loglevel=info --pool=solo
