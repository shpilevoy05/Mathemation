$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Virtual environment not found: $Python"
}

& $Python manage.py makemigrations --check --dry-run
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python manage.py check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python manage.py test
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (Test-Path "package.json") {
    npm run lint
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    npm run build
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "All checks passed."
