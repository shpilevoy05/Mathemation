#requires -Version 5.1
<#
.SYNOPSIS
    Проверки целостности системы навыков. FAIL блокирует merge и релиз.
.PARAMETER SkipInstallChecks
    Пропустить проверки установленных каталогов.
#>
[CmdletBinding()]
param([switch]$SkipInstallChecks)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $Root '.venv\Scripts\python.exe'
if (Test-Path $venv) { $python = $venv }
else {
    $command = Get-Command python -ErrorAction SilentlyContinue
    if (-not $command) { throw 'python не найден: нужен Python 3.10+ в PATH или .venv' }
    $python = $command.Source
}

$arguments = @(Join-Path $PSScriptRoot 'lib\skills_ci.py')
if ($SkipInstallChecks) { $arguments += '--skip-install-checks' }

& $python $arguments
exit $LASTEXITCODE