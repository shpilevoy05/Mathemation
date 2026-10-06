#requires -Version 5.1
<#
.SYNOPSIS
    Валидация скиллов репозитория (структура, метаданные, ссылки).
.PARAMETER Path
    Каталоги скиллов. По умолчанию — все собственные скиллы.
.PARAMETER Strict
    Считать warning ошибкой.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)][string[]]$Path,
    [switch]$Strict
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $Root '.venv\Scripts\python.exe'
if (Test-Path $venv) { $python = $venv }
else {
    $command = Get-Command python -ErrorAction SilentlyContinue
    if (-not $command) { throw 'python не найден: нужен Python 3.10+ в PATH или .venv' }
    $python = $command.Source
}

$arguments = @(Join-Path $PSScriptRoot 'lib\validate_skill.py')
if ($Path -and $Path.Count -gt 0) { $arguments += $Path } else { $arguments += '--all' }
if ($Strict) { $arguments += '--strict' }

& $python $arguments
exit $LASTEXITCODE