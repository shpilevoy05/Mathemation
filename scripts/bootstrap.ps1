@'
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv")) {
    Write-Host "Creating Python virtual environment..."
    py -3.12 -m venv .venv

    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Python executable not found: $Python"
}

Write-Host "Upgrading pip..."
& $Python -m pip install --upgrade pip

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if (Test-Path "requirements.txt") {
    Write-Host "Installing Python dependencies..."
    & $Python -m pip install -r requirements.txt

    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
else {
    Write-Warning "requirements.txt was not found."
}

if ((Test-Path ".env.example") -and (-not (Test-Path ".env"))) {
    Write-Host "Creating local .env from .env.example..."
    Copy-Item ".env.example" ".env"
}

if (-not (Test-Path "manage.py")) {
    throw "manage.py not found. Restore the project from the Git bundle first."
}

Write-Host "Applying database migrations..."
& $Python manage.py migrate

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Running Django system check..."
& $Python manage.py check

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Local environment is ready."
'@ | Set-Content -Encoding utf8 .\scripts\bootstrap.ps1