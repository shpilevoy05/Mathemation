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

Write-Host "Applying database migrations..."
& $Python manage.py migrate

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Starting Django development server..."
Write-Host "Application: http://127.0.0.1:8000/"
Write-Host "Admin:       http://127.0.0.1:8000/admin/"

& $Python manage.py runserver
